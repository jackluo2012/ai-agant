"""实现三层操作管道的对象存储。

这是权限内嵌数据对象原型的核心。
它作为 PostgreSQL 上方的中间件，拦截每个操作并运行完整的管道：
权限检查、验证器、对象存储机制和反应。
"""

from __future__ import annotations
import json
import time
import logging
import threading
from collections import defaultdict
from dataclasses import asdict
from typing import Any, Callable, Optional
from queue import Queue

import psycopg2
import psycopg2.extras

from .models import (
    AccessContext, DataObject, ObjectType, Operation, PermissionRule,
    PrivilegeType, Relationship, RelationshipAction, ReactionDeclaration,
)

logger = logging.getLogger(__name__)


class PermissionDeniedError(Exception):
    """当操作被权限规则拒绝时抛出"""
    pass


class ValidationError(Exception):
    """当验证器拒绝提议的更改时抛出"""
    pass


class ReferentialIntegrityError(Exception):
    """当引用完整性将被破坏时抛出"""
    pass


class ObjectStore:
    """
    具有三层管道的权限内嵌数据对象存储。

    第一层：权限检查 + 只读验证器（同步，控制操作）
    第二层：对象存储机制（同步，内置，不可扩展）
    第三层：反应（异步，队列，产生新操作）
    """

    def __init__(self, dsn: str, max_reaction_depth: int = 3):
        """
        初始化对象存储

        Args:
            dsn: 数据库连接字符串
            max_reaction_depth: 最大反应深度
        """
        self.dsn = dsn
        self.max_reaction_depth = max_reaction_depth
        self.types: dict[str, ObjectType] = {}
        self.reaction_handlers: dict[str, Callable] = {}
        self._reaction_queue: Queue = Queue()
        self._reaction_thread: Optional[threading.Thread] = None
        self._reaction_log: list[dict] = []
        self._running = False
        self._setup_db()

    def _get_conn(self):
        """获取数据库连接"""
        return psycopg2.connect(self.dsn)

    def _setup_db(self):
        """设置数据库表结构"""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS objects (
                        id TEXT PRIMARY KEY,
                        type_name TEXT NOT NULL,
                        content JSONB NOT NULL DEFAULT '{}',
                        owner_id TEXT NOT NULL,
                        org_id TEXT NOT NULL DEFAULT '',
                        parent_id TEXT,
                        permission_rules JSONB,
                        created_at DOUBLE PRECISION NOT NULL,
                        updated_at DOUBLE PRECISION NOT NULL,
                        refs JSONB NOT NULL DEFAULT '{}'
                    );
                    CREATE INDEX IF NOT EXISTS idx_objects_type ON objects(type_name);
                    CREATE INDEX IF NOT EXISTS idx_objects_parent ON objects(parent_id);
                    CREATE INDEX IF NOT EXISTS idx_objects_org ON objects(org_id);
                    CREATE INDEX IF NOT EXISTS idx_objects_owner ON objects(owner_id);

                    CREATE TABLE IF NOT EXISTS reaction_log (
                        id SERIAL PRIMARY KEY,
                        timestamp DOUBLE PRECISION NOT NULL,
                        event TEXT NOT NULL,
                        source_object_id TEXT NOT NULL,
                        handler TEXT NOT NULL,
                        success BOOLEAN NOT NULL,
                        error TEXT,
                        depth INTEGER NOT NULL DEFAULT 0
                    );
                """)
            conn.commit()

    def register_type(self, obj_type: ObjectType):
        """
        注册对象类型

        Args:
            obj_type: 对象类型定义
        """
        self.types[obj_type.name] = obj_type

    def register_reaction_handler(self, name: str, handler: Callable):
        """
        注册反应处理器

        Args:
            name: 处理器名称
            handler: 处理器函数
        """
        self.reaction_handlers[name] = handler

    def start_reactions(self):
        """启动异步反应处理"""
        self._running = True
        self._reaction_thread = threading.Thread(target=self._process_reactions, daemon=True)
        self._reaction_thread.start()

    def stop_reactions(self):
        """停止异步反应处理"""
        self._running = False
        if self._reaction_thread:
            self._reaction_queue.put(None)  # 哨兵值
            self._reaction_thread.join(timeout=5)

    def drain_reactions(self, timeout: float = 5.0):
        """
        等待所有队列中的反应完成

        Args:
            timeout: 超时时间
        """
        self._reaction_queue.join()

    # ── 读取路径 ──────────────────────────────────────────────

    def get(self, object_id: str, accessor: AccessContext) -> Optional[DataObject]:
        """
        读取单个对象。仅权限检查（无验证器/反应）

        Args:
            object_id: 对象 ID
            accessor: 访问上下文

        Returns:
            数据对象，不存在返回 None
        """
        obj = self._load_object(object_id)
        if obj is None:
            return None
        self._check_permission(obj, accessor, PrivilegeType.READ)
        return obj

    def select(self, parent_id: str, accessor: AccessContext,
               type_name: Optional[str] = None,
               filters: Optional[dict] = None) -> list[DataObject]:
        """
        列出子对象。对父对象进行 SELECT 权限检查

        Args:
            parent_id: 父对象 ID
            accessor: 访问上下文
            type_name: 类型过滤器
            filters: 内容过滤器

        Returns:
            数据对象列表
        """
        parent = self._load_object(parent_id)
        if parent is None:
            return []
        self._check_permission(parent, accessor, PrivilegeType.SELECT)

        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                query = "SELECT * FROM objects WHERE parent_id = %s"
                params: list[Any] = [parent_id]
                if type_name:
                    query += " AND type_name = %s"
                    params.append(type_name)
                cur.execute(query, params)
                rows = cur.fetchall()

        results = []
        for row in rows:
            obj = self._row_to_object(row)
            try:
                self._check_permission(obj, accessor, PrivilegeType.READ)
                if filters:
                    if all(obj.content.get(k) == v for k, v in filters.items()):
                        results.append(obj)
                else:
                    results.append(obj)
            except PermissionDeniedError:
                continue  # 静默过滤不可访问的对象
        return results

    def query(self, accessor: AccessContext, type_name: str,
              filters: Optional[dict] = None, org_id: Optional[str] = None) -> list[DataObject]:
        """
        按类型查询对象。每个结果都进行权限检查

        Args:
            accessor: 访问上下文
            type_name: 类型名称
            filters: 内容过滤器
            org_id: 组织 ID 过滤器

        Returns:
            数据对象列表
        """
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                query = "SELECT * FROM objects WHERE type_name = %s"
                params: list[Any] = [type_name]
                if org_id:
                    query += " AND org_id = %s"
                    params.append(org_id)
                cur.execute(query, params)
                rows = cur.fetchall()

        results = []
        for row in rows:
            obj = self._row_to_object(row)
            try:
                self._check_permission(obj, accessor, PrivilegeType.READ)
                if filters:
                    if all(obj.content.get(k) == v for k, v in filters.items()):
                        results.append(obj)
                else:
                    results.append(obj)
            except PermissionDeniedError:
                continue
        return results

    # ── 写入路径：三层管道 ────────────────────────────────────────

    def create(self, obj: DataObject, accessor: AccessContext,
               _reaction_depth: int = 0) -> DataObject:
        """
        创建新对象。完整管道

        Args:
            obj: 数据对象
            accessor: 访问上下文
            _reaction_depth: 反应深度（内部使用）

        Returns:
            创建的对象
        """
        obj_type = self._get_type(obj.type_name)

        # 第一层：权限检查
        if obj.parent_id:
            parent = self._load_object(obj.parent_id)
            if parent is None:
                raise ReferentialIntegrityError(f"父对象 {obj.parent_id} 不存在")
            self._check_permission(parent, accessor, PrivilegeType.INSERT)
        else:
            # 顶层创建：检查类型级权限规则
            self._check_type_permission(obj_type, accessor, PrivilegeType.INSERT)

        # 设置所有权
        if not obj.owner_id:
            obj.owner_id = accessor.user_id
        if not obj.org_id and accessor.org_id:
            obj.org_id = accessor.org_id

        obj.created_at = time.time()
        obj.updated_at = obj.created_at

        # 第一层：验证器
        for validator in obj_type.validators:
            result = validator(obj, None, accessor, self)
            if result is not True and result is not None:
                raise ValidationError(str(result))

        # 验证引用
        self._validate_references(obj, obj_type)

        # 第二层：对象存储机制
        self._store_object(obj)

        # 第三层：队列反应
        self._queue_reactions(obj, "after_create", _reaction_depth)

        return obj

    def update(self, object_id: str, changes: dict[str, Any],
               accessor: AccessContext, _reaction_depth: int = 0) -> DataObject:
        """
        更新对象。完整管道

        Args:
            object_id: 对象 ID
            changes: 更改内容
            accessor: 访问上下文
            _reaction_depth: 反应深度（内部使用）

        Returns:
            更新后的对象
        """
        obj = self._load_object(object_id)
        if obj is None:
            raise ValueError(f"对象 {object_id} 不存在")
        obj_type = self._get_type(obj.type_name)

        # 第一层：权限检查
        if obj.parent_id:
            parent = self._load_object(obj.parent_id)
            if parent:
                self._check_permission(parent, accessor, PrivilegeType.UPDATE)
        # 同时检查自身 WRITE 权限
        accessor_with_owner = AccessContext(
            user_id=accessor.user_id, role=accessor.role,
            org_id=accessor.org_id, groups=accessor.groups,
            is_owner=(accessor.user_id == obj.owner_id),
            attributes=accessor.attributes,
        )
        self._check_permission(obj, accessor_with_owner, PrivilegeType.WRITE)

        # 构建提议的新状态
        old_content = dict(obj.content)
        proposed = DataObject(
            id=obj.id, type_name=obj.type_name,
            content={**obj.content, **changes},
            owner_id=obj.owner_id, org_id=obj.org_id,
            parent_id=obj.parent_id, permission_rules=obj.permission_rules,
            created_at=obj.created_at, updated_at=time.time(),
            references=dict(obj.references),
        )

        # 第一层：验证器
        for validator in obj_type.validators:
            result = validator(proposed, obj, accessor_with_owner, self)
            if result is not True and result is not None:
                raise ValidationError(str(result))

        # 第二层：提交写入
        obj.content = proposed.content
        obj.updated_at = proposed.updated_at
        self._update_object(obj)

        # 第三层：队列反应
        changed_fields = [k for k in changes if old_content.get(k) != changes[k]]
        self._queue_reactions(obj, "after_update", _reaction_depth, changed_fields=changed_fields)

        return obj

    def delete(self, object_id: str, accessor: AccessContext,
               _reaction_depth: int = 0) -> bool:
        """
        删除对象。完整管道

        Args:
            object_id: 对象 ID
            accessor: 访问上下文
            _reaction_depth: 反应深度（内部使用）

        Returns:
            是否成功
        """
        obj = self._load_object(object_id)
        if obj is None:
            raise ValueError(f"对象 {object_id} 不存在")
        obj_type = self._get_type(obj.type_name)

        # 第一层：权限检查
        if obj.parent_id:
            parent = self._load_object(obj.parent_id)
            if parent:
                self._check_permission(parent, accessor, PrivilegeType.DELETE)
        accessor_with_owner = AccessContext(
            user_id=accessor.user_id, role=accessor.role,
            org_id=accessor.org_id, groups=accessor.groups,
            is_owner=(accessor.user_id == obj.owner_id),
            attributes=accessor.attributes,
        )
        self._check_permission(obj, accessor_with_owner, PrivilegeType.WRITE)

        # 第二层：对象存储机制 — 处理引用完整性
        self._handle_delete_cascades(obj, accessor, _reaction_depth)

        # 检查来自其他对象的 RESTRICT 引用
        self._check_restrict_references(obj)

        # 删除对象
        self._delete_object(object_id)

        # 第三层：队列反应
        self._queue_reactions(obj, "after_delete", _reaction_depth)

        return True

    # ── 第一层：权限评估 ──────────────────────────────────────

    def _check_permission(self, obj: DataObject, accessor: AccessContext,
                          privilege: PrivilegeType):
        """
        评估权限过滤链。首次匹配获胜

        Args:
            obj: 数据对象
            accessor: 访问上下文
            privilege: 权限类型

        Raises:
            PermissionDeniedError: 权限被拒绝
        """
        now = time.time()
        obj_type = self._get_type(obj.type_name)

        # 内置租户隔离：如果对象有 org_id 且访问者有不同的 org_id，
        # 拒绝访问（除非访问者是系统用户）
        if (obj.org_id and accessor.org_id and
                obj.org_id != accessor.org_id and accessor.role != "system"):
            raise PermissionDeniedError(
                f"租户隔离：访问者组织 {accessor.org_id} != 对象组织 {obj.org_id}")

        # 收集规则：类型级规则 + 对象级覆盖
        rules = obj.permission_rules if obj.permission_rules is not None else obj_type.permission_rules

        # 检查层级：沿父链向上
        if obj.parent_id:
            parent_result = self._check_parent_permissions(obj.parent_id, accessor, privilege, now)
            if parent_result is not None:
                if parent_result == Operation.DENY:
                    raise PermissionDeniedError(
                        f"父层级拒绝访问：{privilege.value} 在对象 {obj.id} 上")
                elif parent_result == Operation.ACCEPT:
                    return  # 父对象授权访问

        # 评估自身规则
        for rule in rules:
            # 将子权限映射到自身权限以进行直接访问
            effective_privilege = privilege
            if rule.matches(accessor, effective_privilege, now):
                if rule.operation == Operation.DENY:
                    raise PermissionDeniedError(
                        f"拒绝访问：{privilege.value} 在对象 {obj.id} 上")
                elif rule.operation == Operation.ACCEPT:
                    return
                elif rule.operation == Operation.PENDING:
                    raise PermissionDeniedError(
                        f"访问待批准：{privilege.value} 在对象 {obj.id} 上")

        # 默认策略
        if obj_type.default_policy == Operation.DENY:
            raise PermissionDeniedError(
                f"默认拒绝：{privilege.value} 在对象 {obj.id} 上（类型={obj.type_name}）")

    def _check_type_permission(self, obj_type: ObjectType, accessor: AccessContext,
                               privilege: PrivilegeType):
        """
        检查顶层创建的类型级权限

        Args:
            obj_type: 对象类型
            accessor: 访问上下文
            privilege: 权限类型

        Raises:
            PermissionDeniedError: 权限被拒绝
        """
        now = time.time()
        for rule in obj_type.permission_rules:
            if rule.matches(accessor, privilege, now):
                if rule.operation == Operation.DENY:
                    raise PermissionDeniedError(
                        f"类型级拒绝：{privilege.value} 在类型 {obj_type.name} 上")
                elif rule.operation == Operation.ACCEPT:
                    return
        if obj_type.default_policy == Operation.DENY:
            raise PermissionDeniedError(
                f"默认类型级拒绝：{privilege.value} 在类型 {obj_type.name} 上")

    def _check_parent_permissions(self, parent_id: str, accessor: AccessContext,
                                  privilege: PrivilegeType, now: float) -> Optional[Operation]:
        """
        沿层级向上检查子权限

        Args:
            parent_id: 父对象 ID
            accessor: 访问上下文
            privilege: 权限类型
            now: 当前时间

        Returns:
            操作结果或 None
        """
        parent = self._load_object(parent_id)
        if parent is None:
            return None

        parent_type = self._get_type(parent.type_name)
        rules = parent.permission_rules if parent.permission_rules is not None else parent_type.permission_rules

        # 将自身权限映射到子权限
        child_priv_map = {
            PrivilegeType.READ: PrivilegeType.SELECT,
            PrivilegeType.WRITE: PrivilegeType.UPDATE,
        }
        child_priv = child_priv_map.get(privilege, privilege)

        for rule in rules:
            if rule.matches(accessor, child_priv, now):
                return rule.operation

        # 递归向上
        if parent.parent_id:
            return self._check_parent_permissions(parent.parent_id, accessor, privilege, now)

        return None

    # ── 第二层：对象存储机制 ─────────────────────────────────────

    def _validate_references(self, obj: DataObject, obj_type: ObjectType):
        """
        验证所有声明的引用都指向存在的对象

        Args:
            obj: 数据对象
            obj_type: 对象类型

        Raises:
            ReferentialIntegrityError: 引用完整性错误
        """
        for rel in obj_type.relationships:
            ref_id = obj.references.get(rel.name) or obj.content.get(rel.name + "_id")
            if ref_id:
                target = self._load_object(ref_id)
                if target is None:
                    raise ReferentialIntegrityError(
                        f"关系 {rel.name} 的引用对象 {ref_id} 不存在")
                if target.type_name != rel.target_type:
                    raise ReferentialIntegrityError(
                        f"引用对象 {ref_id} 是类型 {target.type_name}，预期 {rel.target_type}")
            elif rel.required:
                raise ReferentialIntegrityError(
                    f"必需的关系 {rel.name} 未在对象 {obj.id} 上设置")

    def _handle_delete_cascades(self, obj: DataObject, accessor: AccessContext,
                                reaction_depth: int):
        """
        处理子对象的 CASCADE 和 NULLIFY

        Args:
            obj: 数据对象
            accessor: 访问上下文
            reaction_depth: 反应深度
        """
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # 查找子对象
                cur.execute("SELECT * FROM objects WHERE parent_id = %s", (obj.id,))
                children = cur.fetchall()

        for child_row in children:
            child = self._row_to_object(child_row)
            child_type = self.types.get(child.type_name)
            if child_type:
                # 默认：级联删除子对象
                self.delete(child.id, accessor, _reaction_depth=reaction_depth)

        # 处理基于引用的级联
        for type_name, obj_type in self.types.items():
            for rel in obj_type.relationships:
                if rel.target_type == obj.type_name:
                    if rel.on_delete == RelationshipAction.CASCADE:
                        referencing = self._find_referencing_objects(obj.id, type_name, rel.name)
                        for ref_obj in referencing:
                            self.delete(ref_obj.id, accessor, _reaction_depth=reaction_depth)
                    elif rel.on_delete == RelationshipAction.NULLIFY:
                        referencing = self._find_referencing_objects(obj.id, type_name, rel.name)
                        for ref_obj in referencing:
                            ref_obj.content[rel.name + "_id"] = None
                            ref_obj.references.pop(rel.name, None)
                            self._update_object(ref_obj)

    def _check_restrict_references(self, obj: DataObject):
        """
        检查是否有 RESTRICT 引用阻止删除

        Args:
            obj: 数据对象

        Raises:
            ReferentialIntegrityError: 引用完整性错误
        """
        for type_name, obj_type in self.types.items():
            for rel in obj_type.relationships:
                if rel.target_type == obj.type_name and rel.on_delete == RelationshipAction.RESTRICT:
                    referencing = self._find_referencing_objects(obj.id, type_name, rel.name)
                    if referencing:
                        raise ReferentialIntegrityError(
                            f"无法删除 {obj.id}：被 {len(referencing)} 个 "
                            f"{type_name} 对象通过 {rel.name} 引用（RESTRICT）")

    def _find_referencing_objects(self, target_id: str, type_name: str,
                                  rel_name: str) -> list[DataObject]:
        """
        查找通过给定关系引用目标的对象

        Args:
            target_id: 目标对象 ID
            type_name: 类型名称
            rel_name: 关系名称

        Returns:
            引用对象列表
        """
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # 同时检查内容字段和引用
                cur.execute("""
                    SELECT * FROM objects
                    WHERE type_name = %s
                    AND (content->>%s = %s OR refs->>%s = %s)
                """, (type_name, rel_name + "_id", target_id, rel_name, target_id))
                return [self._row_to_object(r) for r in cur.fetchall()]

    # ── 第三层：反应 ──────────────────────────────────────────

    def _queue_reactions(self, obj: DataObject, event: str,
                         depth: int, changed_fields: Optional[list[str]] = None):
        """
        将反应排队进行异步处理

        Args:
            obj: 数据对象
            event: 事件名称
            depth: 反应深度
            changed_fields: 更改的字段列表
        """
        if depth >= self.max_reaction_depth:
            logger.warning(f"达到反应深度限制（{depth}）对于对象 {obj.id}")
            return

        obj_type = self._get_type(obj.type_name)
        for reaction in obj_type.reactions:
            should_fire = False
            if reaction.event == event:
                should_fire = True
            elif event == "after_update" and changed_fields:
                # 检查特定字段的反应，如 "after_update:status"
                if ":" in reaction.event:
                    _, field_name = reaction.event.split(":", 1)
                    if field_name in changed_fields:
                        should_fire = True

            if should_fire:
                self._reaction_queue.put({
                    "event": reaction.event,
                    "handler": reaction.handler,
                    "object_id": obj.id,
                    "object_type": obj.type_name,
                    "object_content": dict(obj.content),
                    "object_owner": obj.owner_id,
                    "object_org": obj.org_id,
                    "depth": depth + 1,
                    "changed_fields": changed_fields or [],
                    "timestamp": time.time(),
                })

    def _process_reactions(self):
        """处理队列反应的后台线程"""
        while self._running:
            item = self._reaction_queue.get()
            if item is None:
                self._reaction_queue.task_done()
                break
            try:
                handler = self.reaction_handlers.get(item["handler"])
                if handler:
                    handler(item, self)
                    self._log_reaction(item, success=True)
                else:
                    self._log_reaction(item, success=False,
                                       error=f"处理器 {item['handler']} 不存在")
            except Exception as e:
                self._log_reaction(item, success=False, error=str(e))
                logger.error(f"反应失败：{item['handler']} 对于对象 {item['object_id']}: {e}")
            finally:
                self._reaction_queue.task_done()

    def process_reactions_sync(self):
        """同步处理所有队列中的反应（用于测试）"""
        while not self._reaction_queue.empty():
            item = self._reaction_queue.get()
            if item is None:
                self._reaction_queue.task_done()
                continue
            try:
                handler = self.reaction_handlers.get(item["handler"])
                if handler:
                    handler(item, self)
                    self._log_reaction(item, success=True)
                else:
                    self._log_reaction(item, success=False,
                                       error=f"处理器 {item['handler']} 不存在")
            except Exception as e:
                self._log_reaction(item, success=False, error=str(e))
            finally:
                self._reaction_queue.task_done()

    def _log_reaction(self, item: dict, success: bool, error: Optional[str] = None):
        """
        记录反应日志

        Args:
            item: 反应项
            success: 是否成功
            error: 错误信息
        """
        entry = {
            "timestamp": time.time(),
            "event": item["event"],
            "source_object_id": item["object_id"],
            "handler": item["handler"],
            "success": success,
            "error": error,
            "depth": item["depth"],
        }
        self._reaction_log.append(entry)
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO reaction_log (timestamp, event, source_object_id, handler, success, error, depth)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (entry["timestamp"], entry["event"], entry["source_object_id"],
                      entry["handler"], entry["success"], entry["error"], entry["depth"]))
            conn.commit()

    def get_reaction_log(self) -> list[dict]:
        """获取反应日志"""
        return list(self._reaction_log)

    # ── 存储层 ──────────────────────────────────────────────────

    def _store_object(self, obj: DataObject):
        """存储对象到数据库"""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                rules_json = None
                if obj.permission_rules is not None:
                    rules_json = json.dumps([{
                        "operation": r.operation.value,
                        "privilege": r.privilege.value,
                        "condition": r.condition,
                        "valid_from": r.valid_from,
                        "valid_until": r.valid_until,
                    } for r in obj.permission_rules])

                cur.execute("""
                    INSERT INTO objects (id, type_name, content, owner_id, org_id,
                                        parent_id, permission_rules, created_at, updated_at, refs)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (obj.id, obj.type_name, json.dumps(obj.content),
                      obj.owner_id, obj.org_id, obj.parent_id,
                      rules_json, obj.created_at, obj.updated_at,
                      json.dumps(obj.references)))
            conn.commit()

    def _update_object(self, obj: DataObject):
        """更新数据库中的对象"""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE objects SET content = %s, updated_at = %s, refs = %s,
                                      parent_id = %s, org_id = %s
                    WHERE id = %s
                """, (json.dumps(obj.content), obj.updated_at,
                      json.dumps(obj.references), obj.parent_id,
                      obj.org_id, obj.id))
            conn.commit()

    def _delete_object(self, object_id: str):
        """从数据库删除对象"""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM objects WHERE id = %s", (object_id,))
            conn.commit()

    def _load_object(self, object_id: str) -> Optional[DataObject]:
        """从数据库加载对象"""
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM objects WHERE id = %s", (object_id,))
                row = cur.fetchone()
                if row is None:
                    return None
                return self._row_to_object(row)

    def _row_to_object(self, row: dict) -> DataObject:
        """将数据库行转换为数据对象"""
        rules = None
        if row.get("permission_rules"):
            raw_rules = row["permission_rules"]
            if isinstance(raw_rules, str):
                raw_rules = json.loads(raw_rules)
            rules = [
                PermissionRule(
                    operation=Operation(r["operation"]),
                    privilege=PrivilegeType(r["privilege"]),
                    condition=r.get("condition", {}),
                    valid_from=r.get("valid_from"),
                    valid_until=r.get("valid_until"),
                )
                for r in raw_rules
            ]

        content = row["content"]
        if isinstance(content, str):
            content = json.loads(content)
        refs = row.get("refs", "{}")
        if isinstance(refs, str):
            refs = json.loads(refs)

        return DataObject(
            id=row["id"],
            type_name=row["type_name"],
            content=content,
            owner_id=row["owner_id"],
            org_id=row["org_id"],
            parent_id=row.get("parent_id"),
            permission_rules=rules,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            references=refs,
        )

    def _get_type(self, type_name: str) -> ObjectType:
        """获取对象类型"""
        if type_name not in self.types:
            raise ValueError(f"未知的对象类型：{type_name}")
        return self.types[type_name]

    # ── 工具函数 ──────────────────────────────────────────────

    def clear_all(self):
        """清除所有数据（用于测试）"""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM objects")
                cur.execute("DELETE FROM reaction_log")
            conn.commit()
        self._reaction_log.clear()

    def count_objects(self, type_name: Optional[str] = None) -> int:
        """统计对象数量"""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                if type_name:
                    cur.execute("SELECT COUNT(*) FROM objects WHERE type_name = %s", (type_name,))
                else:
                    cur.execute("SELECT COUNT(*) FROM objects")
                return cur.fetchone()[0]

    def raw_read(self, object_id: str) -> Optional[DataObject]:
        """无权限检查的读取（用于验证器和内部使用）"""
        return self._load_object(object_id)

    def raw_query(self, type_name: str, filters: Optional[dict] = None,
                  org_id: Optional[str] = None) -> list[DataObject]:
        """无权限检查的查询（用于验证器）"""
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                query = "SELECT * FROM objects WHERE type_name = %s"
                params: list[Any] = [type_name]
                if org_id:
                    query += " AND org_id = %s"
                    params.append(org_id)
                cur.execute(query, params)
                rows = cur.fetchall()
        results = []
        for row in rows:
            obj = self._row_to_object(row)
            if filters:
                if all(obj.content.get(k) == v for k, v in filters.items()):
                    results.append(obj)
            else:
                results.append(obj)
        return results
