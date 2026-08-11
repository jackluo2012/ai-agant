"""权限内嵌数据对象的核心数据模型。"""

from __future__ import annotations
import uuid
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Operation(Enum):
    """操作类型枚举"""
    ACCEPT = "ACCEPT"  # 接受
    DENY = "DENY"      # 拒绝
    PENDING = "PENDING"  # 待定


class PrivilegeType(Enum):
    """权限类型枚举"""
    # 自身权限
    READ = "READ"      # 读取
    WRITE = "WRITE"    # 写入
    # 子权限
    SELECT = "SELECT"  # 查询
    INSERT = "INSERT"  # 插入
    DELETE = "DELETE"  # 删除
    UPDATE = "UPDATE"  # 更新
    MANAGE = "MANAGE"  # 管理
    APPROVE = "APPROVE"  # 批准


class RelationshipAction(Enum):
    """关系动作枚举（删除时）"""
    CASCADE = "CASCADE"      # 级联删除
    RESTRICT = "RESTRICT"    # 限制
    NULLIFY = "NULLIFY"      # 置空


@dataclass
class PermissionRule:
    """过滤链中的单个权限规则"""
    operation: Operation              # 操作类型
    privilege: PrivilegeType           # 权限类型
    condition: dict[str, Any] = field(default_factory=dict)  # 匹配条件
    valid_from: Optional[float] = None  # 生效起始时间
    valid_until: Optional[float] = None  # 生效结束时间

    def matches(self, accessor: AccessContext, privilege: PrivilegeType, now: float) -> bool:
        """
        检查规则是否匹配

        Args:
            accessor: 访问上下文
            privilege: 权限类型
            now: 当前时间戳

        Returns:
            是否匹配
        """
        if self.privilege != privilege:
            return False
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_until and now > self.valid_until:
            return False
        return self._evaluate_condition(accessor)

    def _evaluate_condition(self, accessor: AccessContext) -> bool:
        """
        评估条件是否匹配

        Args:
            accessor: 访问上下文

        Returns:
            是否匹配
        """
        if not self.condition:
            return True
        for key, value in self.condition.items():
            if key == "role":
                if accessor.role != value:
                    return False
            elif key == "roles":
                if accessor.role not in value:
                    return False
            elif key == "is_owner":
                if value and not accessor.is_owner:
                    return False
            elif key == "org_id":
                if accessor.org_id != value:
                    return False
            elif key == "user_id":
                if accessor.user_id != value:
                    return False
            elif key == "group":
                if value not in accessor.groups:
                    return False
        return True


@dataclass
class AccessContext:
    """访问者的身份和属性"""
    user_id: str                           # 用户 ID
    role: str = "anonymous"                 # 角色
    org_id: Optional[str] = None            # 组织 ID
    groups: list[str] = field(default_factory=list)  # 用户组列表
    is_owner: bool = False                  # 是否是所有者
    attributes: dict[str, Any] = field(default_factory=dict)  # 其他属性


@dataclass
class Relationship:
    """对象类型之间声明的关系"""
    name: str                               # 关系名称
    target_type: str                        # 目标类型
    on_delete: RelationshipAction = RelationshipAction.RESTRICT  # 删除时的动作
    required: bool = False                  # 是否必需


@dataclass
class ReactionDeclaration:
    """在成功写入后触发的声明反应"""
    event: str  # 事件，如 "after_update:status", "after_create", "after_delete"
    handler: str  # 处理器函数名称


@dataclass
class ObjectType:
    """对象类型的模式定义"""
    name: str                              # 类型名称
    fields: dict[str, str]                 # 字段名 -> 类型字符串
    permission_rules: list[PermissionRule] = field(default_factory=list)  # 权限规则列表
    validators: list = field(default_factory=list)  # 可调用验证器列表
    reactions: list[ReactionDeclaration] = field(default_factory=list)  # 反应声明列表
    relationships: list[Relationship] = field(default_factory=list)  # 关系列表
    default_policy: Operation = Operation.DENY  # 默认策略
    parent_type: Optional[str] = None      # 管理层级中的父类型名称


@dataclass
class DataObject:
    """权限内嵌数据对象实例"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))  # 对象 ID
    type_name: str = ""                   # 类型名称
    content: dict[str, Any] = field(default_factory=dict)  # 内容数据
    owner_id: str = ""                    # 所有者 ID
    org_id: str = ""                      # 组织 ID
    parent_id: Optional[str] = None        # 父对象 ID（管理层级）
    permission_rules: Optional[list[PermissionRule]] = None  # 权限规则（None 表示从类型继承）
    created_at: float = field(default_factory=time.time)  # 创建时间
    updated_at: float = field(default_factory=time.time)  # 更新时间
    references: dict[str, str] = field(default_factory=dict)  # 引用名 -> 目标对象 ID
