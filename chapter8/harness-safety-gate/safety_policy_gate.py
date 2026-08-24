"""
安全策略门禁模块。

根据安全规则检查工具调用参数（路径遍历、危险的 bash 命令、资源限制）。
对高风险操作强制执行确认门禁，并在安全违规时触发自动状态回滚。
"""

import hashlib
import hmac
import os
import re
import secrets
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union


@dataclass
class SafetyGateDecision:
    """表示工具调用的安全评估决策。"""
    allowed: bool
    requires_confirmation: bool = False
    triggered_rollback: bool = False
    violation_type: Optional[str] = None
    reason: Optional[str] = None
    risk_score: float = 0.0
    confirmation_token: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """将决策转换为字典表示。"""
        return {
            "allowed": self.allowed,
            "requires_confirmation": self.requires_confirmation,
            "triggered_rollback": self.triggered_rollback,
            "violation_type": self.violation_type,
            "reason": self.reason,
            "risk_score": self.risk_score,
            "confirmation_token": self.confirmation_token,
            "details": self.details,
        }


class SafetyPolicyGate:
    """用于工具调用安全检查和确认的 Harness 安全策略门禁。"""

    # 检测路径遍历尝试的模式（应用于所有路径）
    PATH_TRAVERSAL_PATTERNS = [
        re.compile(r'\.\.[/\\]'),                           # ../ 或 ..\
        re.compile(r'%2e%2e', re.IGNORECASE),               # URL 编码的 ..
        re.compile(r'\x00|%00'),                            # 空字节
    ]

    # 敏感目录的模式（仅应用于绝对路径/家目录相对路径
    # 及其 realpath 解析）。注意：这是纵深防御，不是白名单沙箱。
    # 指向黑名单之外敏感文件的符号链接（如 /home/<user>/.ssh）
    # 可能绕过检测。对不受信任的路径访问请使用适当的沙箱。
    # （这样合法的相对路径在 CWD 解析后不会被误报）
    SENSITIVE_DIR_PATTERNS = [
        re.compile(r'^/(etc|var/log|sys|proc|boot|dev|root)(?:/|$)', re.IGNORECASE), # 敏感 Linux 目录
        re.compile(r'~/(?:\.ssh|\.aws|\.gnupg|\.bashrc|\.zshrc)', re.IGNORECASE), # 敏感用户配置
        re.compile(r'^[a-zA-Z]:\\(Windows|System32|Program Files)', re.IGNORECASE), # 敏感 Windows 目录
    ]

    # 检测危险 bash/shell 命令的模式。
    # 注意：基于正则的检测是纵深防御，不是完整的沙箱。
    # 复杂的 shell 扩展（如变量替换、base64 管道）
    # 可能绕过这些模式。安全门禁应与适当的
    # 沙箱结合使用，用于不受信任的代码执行。
    DANGEROUS_COMMAND_PATTERNS = [
        (re.compile(r'\brm\s+.*(-[a-zA-Z]*(?:r[a-zA-Z]*f|f[a-zA-Z]*r)|-f\s+-r|-r\s+-f|--recursive)', re.IGNORECASE), "递归文件删除命令"),
        (re.compile(r'\bmkfs\b|\bdd\s+if=|\b>\s*/dev/sd[a-z]', re.IGNORECASE), "磁盘格式化/原始写入命令"),
        (re.compile(r'\b(shutdown|reboot|poweroff|init\s+[06])\b', re.IGNORECASE), "系统生命周期控制命令"),
        (re.compile(r'\bchmod\s+(-R\s+)?777\b|\bchown\s+(-R\s+)?root\b', re.IGNORECASE), "危险权限修改"),
        (re.compile(r'\b(curl|wget)\s+.*\|\s*(ba)?sh\b', re.IGNORECASE), "通过管道到 shell 的远程代码执行"),
        (re.compile(r':\(\)\s*\{\s*:\|:&\s*\};:', re.IGNORECASE), "Fork bomb 命令"),
        (re.compile(r'\b(pkill\s+-9|killall\s+-9)\b', re.IGNORECASE), "无选择进程杀死命令"),
    ]

    # 破坏性 SQL 查询的模式
    DESTRUCTIVE_SQL_DROP = re.compile(r'\b(DROP\s+TABLE|DROP\s+DATABASE|TRUNCATE)\b', re.IGNORECASE)
    DESTRUCTIVE_SQL_DELETE = re.compile(r'\bDELETE\b', re.IGNORECASE)
    SQL_WHERE_CLAUSE = re.compile(r'\bWHERE\b', re.IGNORECASE)

    def __init__(
        self,
        max_timeout: float = 600.0,
        max_tokens: int = 100000,
        max_file_bytes: int = 50 * 1024 * 1024,
        max_memory_mb: int = 8192,
        max_threads: int = 16,
        secret_key: Optional[Union[str, bytes]] = None,
        token_ttl: float = 300.0,
    ):
        """Initialize SafetyPolicyGate with configurable resource limits and secret key."""
        self.max_timeout = max_timeout
        self.max_tokens = max_tokens
        self.max_file_bytes = max_file_bytes
        self.max_memory_mb = max_memory_mb
        self.max_threads = max_threads
        if secret_key is None:
            env_key = os.environ.get("SAFETY_GATE_SECRET_KEY")
            if env_key:
                self.secret_key = env_key
            else:
                # Generate a random per-instance secret instead of a hardcoded default
                self.secret_key = secrets.token_bytes(32)
        else:
            self.secret_key = secret_key
        # Active pending confirmation tokens: token -> (fingerprint, expiry timestamp)
        self._pending_confirmations: Dict[str, Tuple[str, float]] = {}
        # TTL (seconds) for unused confirmation tokens
        self._token_ttl: float = token_ttl
        # Registered rollback handlers
        self._rollback_handlers: List[Callable[[], None]] = []
        # State snapshot history
        self._snapshots: List[Dict[str, Any]] = []

    def register_rollback_handler(self, handler: Callable[[], None]) -> None:
        """注册在状态回滚触发时执行的回调函数。"""
        self._rollback_handlers.append(handler)

    def create_snapshot(self, state: Dict[str, Any]) -> int:
        """创建状态快照并返回快照索引。"""
        self._snapshots.append(state.copy())
        return len(self._snapshots) - 1

    def trigger_rollback(self) -> bool:
        """通过调用所有注册的回滚处理程序触发自动状态回滚。"""
        success = True
        for handler in self._rollback_handlers:
            try:
                handler()
            except Exception:
                success = False
        return success

    def _clean_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """从参数中剥离控制字段（confirm_token, user_confirmed）。"""
        if not isinstance(params, dict):
            return {}
        return {k: v for k, v in params.items() if k not in ("confirm_token", "user_confirmed")}

    def _fingerprint(self, tool_name: str, params: Dict[str, Any]) -> str:
        """为工具调用及其参数生成规范的 SHA256 指纹。"""
        import json
        clean_p = self._clean_params(params)
        canonical = json.dumps({"tool": tool_name.lower(), "params": clean_p}, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _cleanup_expired_tokens(self) -> None:
        """移除已过期的待确认令牌。"""
        now = time.time()
        for token in [t for t, (_, exp) in self._pending_confirmations.items() if exp <= now]:
            del self._pending_confirmations[token]

    def issue_confirmation(self, tool_name: str, params: Dict[str, Any]) -> str:
        """生成绑定到工具名和参数的一次性非确定性确认令牌。"""
        self._cleanup_expired_tokens()
        fp = self._fingerprint(tool_name, params)
        token = secrets.token_hex(16)
        self._pending_confirmations[token] = (fp, time.time() + self._token_ttl)
        return token

    def verify_confirmation(self, token: str, tool_name: str, params: Dict[str, Any]) -> bool:
        """验证并消费一次性确认令牌。"""
        self._cleanup_expired_tokens()
        if not token or token not in self._pending_confirmations:
            return False
        expected_fp, _expiry = self._pending_confirmations[token]
        actual_fp = self._fingerprint(tool_name, params)
        if not hmac.compare_digest(expected_fp, actual_fp):
            # 指纹不匹配：保留令牌完整，以便调用者可以使用正确的参数重试，
            # 而不是被错误的尝试消费掉。
            return False
        del self._pending_confirmations[token]
        return True

    def _extract_string_values(self, obj: Any) -> List[str]:
        """从嵌套数据结构中递归提取所有字符串值。"""
        strings = []
        if isinstance(obj, str):
            strings.append(obj)
        elif isinstance(obj, dict):
            for v in obj.values():
                strings.extend(self._extract_string_values(v))
        elif isinstance(obj, (list, tuple, set)):
            for item in obj:
                strings.extend(self._extract_string_values(item))
        return strings

    def inspect_path_traversal(self, params: Dict[str, Any]) -> Optional[str]:
        """检查参数中是否存在路径遍历漏洞。"""
        if not isinstance(params, dict):
            return None

        path_keys = {"path", "filepath", "file_path", "file", "filename", "dir", "directory",
                     "dest", "source", "target", "output", "input", "folder", "src", "dst", "location", "uri"}

        path_strings = []
        for k, v in params.items():
            if k.lower() in path_keys or "path" in k.lower() or "file" in k.lower() or "dir" in k.lower():
                path_strings.extend(self._extract_string_values(v))

        if not path_strings:
            for k, v in params.items():
                if k.lower() not in {"content", "text", "message", "body", "data", "prompt", "code", "script"}:
                    path_strings.extend(self._extract_string_values(v))

        for s in path_strings:
            # 处理双重 URL 解码
            unquoted1 = urllib.parse.unquote(s)
            unquoted2 = urllib.parse.unquote(unquoted1)

            candidates = [s, unquoted1, unquoted2]
            for cand in candidates:
                # 遍历模式应用于每个路径
                for pattern in self.PATH_TRAVERSAL_PATTERNS:
                    if pattern.search(cand):
                        return f"Path traversal attack detected in parameter value: '{s}'"

                # Check sensitive-directory patterns on the path itself (if absolute
                # or home-relative) and on its realpath resolution (catches relative
                # paths that resolve into sensitive directories).
                if os.path.isabs(cand) or cand.startswith("~"):
                    for pattern in self.SENSITIVE_DIR_PATTERNS:
                        if pattern.search(cand):
                            return f"Path traversal attack detected in parameter value: '{s}'"
                try:
                    real_p = os.path.realpath(cand)
                    for pattern in self.SENSITIVE_DIR_PATTERNS:
                        if pattern.search(real_p):
                            return f"参数值中检测到路径遍历攻击：'{s}'"
                except Exception:
                    pass

        return None

    def inspect_dangerous_commands(self, tool_name: str, params: Dict[str, Any]) -> Optional[str]:
        """检查参数中是否存在危险的 bash/shell 命令模式。"""
        if not isinstance(params, dict):
            return None
        tool_name_lower = tool_name.lower()
        # 检查命令字符串参数
        cmd_keys = {"command", "cmd", "script", "bash", "shell", "exec", "args", "input", "code"}
        cmd_strings = []
        for k, v in params.items():
            if k.lower() in cmd_keys or "command" in k.lower() or "shell" in k.lower() or "script" in k.lower() or "exec" in k.lower():
                cmd_strings.extend(self._extract_string_values(v))
        if tool_name_lower in ("run_shell", "bash", "execute_command", "shell", "sh", "terminal", "run", "exec", "system"):
            cmd_strings.extend(self._extract_string_values(params))

        for cmd_str in cmd_strings:
            for pattern, reason in self.DANGEROUS_COMMAND_PATTERNS:
                if pattern.search(cmd_str):
                    return f"{reason}：'{cmd_str}'"

        return None

    def inspect_resource_limits(self, params: Dict[str, Any]) -> Optional[str]:
        """根据预定义的资源限制边界检查参数。"""
        if not isinstance(params, dict):
            return None

        # 检查超时限制
        timeout = params.get("timeout")
        if isinstance(timeout, (int, float)) and timeout > self.max_timeout:
            return f"超时 {timeout}s 超过最大限制 {self.max_timeout}s"

        # 检查最大令牌限制
        tokens = params.get("max_tokens") or params.get("tokens")
        if isinstance(tokens, (int, float)) and tokens > self.max_tokens:
            return f"请求的令牌数 {tokens} 超过最大限制 {self.max_tokens}"

        # 检查文件大小限制
        file_bytes = params.get("file_size") or params.get("bytes")
        if isinstance(file_bytes, (int, float)) and file_bytes > self.max_file_bytes:
            return f"请求的文件大小 {file_bytes} 字节超过最大限制 {self.max_file_bytes} 字节"

        # 检查内存限制
        memory_mb = params.get("memory_mb") or params.get("memory")
        if isinstance(memory_mb, (int, float)) and memory_mb > self.max_memory_mb:
            return f"请求的内存 {memory_mb}MB 超过最大限制 {self.max_memory_mb}MB"

        # 检查线程/进程限制
        threads = params.get("threads") or params.get("processes")
        if isinstance(threads, (int, float)) and threads > self.max_threads:
            return f"请求的线程数 {threads} 超过最大限制 {self.max_threads}"

        return None

    def is_high_risk_operation(self, tool_name: str, params: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """确定工具调用是否为需要明确确认的高风险操作。"""
        if not isinstance(params, dict):
            params = {}
        tool_name_lower = tool_name.lower()
        # 删除工具
        if tool_name_lower in ("delete_file", "remove_directory", "rmdir", "unlink", "wipe_cache", "system_reset"):
            return True, f"操作 '{tool_name}' 具有破坏性，需要用户确认"

        # Git 强制推送
        if tool_name_lower in ("git_push", "git") and params.get("force"):
            return True, "强制推送将覆盖远程仓库历史"

        # 破坏性 SQL 查询
        if tool_name_lower in ("sql_query", "db_execute", "execute_sql"):
            raw_query = str(params.get("query", "") or params.get("sql", ""))
            # 移除块注释（/* ... */）然后移除单行注释（-- ...）
            clean_query = re.sub(r'/\*.*?\*/', '', raw_query, flags=re.DOTALL)
            clean_query = re.sub(r'--.*$', '', clean_query, flags=re.MULTILINE)
            statements = [s.strip() for s in clean_query.split(";") if s.strip()]
            for stmt in statements:
                if self.DESTRUCTIVE_SQL_DROP.search(stmt):
                    return True, "DROP/TRUNCATE 查询将销毁数据库表或架构"
                if self.DESTRUCTIVE_SQL_DELETE.search(stmt) and not self.SQL_WHERE_CLAUSE.search(stmt):
                    return True, "无 WHERE 子句的 DELETE 查询将清空表中的所有记录"

        return False, None

    def validate_tool_call(
        self,
        tool_name: str,
        params: Optional[Dict[str, Any]] = None,
        confirm_token: Optional[str] = None,
        user_confirmed: bool = False,
    ) -> SafetyGateDecision:
        """根据安全规则和确认策略检查并验证工具调用。"""
        params = params if params is not None else {}

        # 1. 检查路径遍历（严重违规）
        pt_violation = self.inspect_path_traversal(params)
        if pt_violation:
            rollback_ok = self.trigger_rollback()
            return SafetyGateDecision(
                allowed=False,
                requires_confirmation=False,
                triggered_rollback=True,
                violation_type="rollback_failed" if not rollback_ok else "path_traversal",
                reason=pt_violation,
                risk_score=1.0,
                details={"tool_name": tool_name, "params": params, "rollback_success": rollback_ok},
            )

        # 2. 检查危险 Bash 命令（严重违规）
        cmd_violation = self.inspect_dangerous_commands(tool_name, params)
        if cmd_violation:
            rollback_ok = self.trigger_rollback()
            return SafetyGateDecision(
                allowed=False,
                requires_confirmation=False,
                triggered_rollback=True,
                violation_type="rollback_failed" if not rollback_ok else "dangerous_bash_command",
                reason=cmd_violation,
                risk_score=1.0,
                details={"tool_name": tool_name, "params": params, "rollback_success": rollback_ok},
            )
        # 3. 检查资源限制
        res_violation = self.inspect_resource_limits(params)
        if res_violation:
            return SafetyGateDecision(
                allowed=False,
                requires_confirmation=False,
                triggered_rollback=False,
                violation_type="resource_limit_exceeded",
                reason=res_violation,
                risk_score=0.8,
                details={"tool_name": tool_name, "params": params},
            )

        # 4. 检查高风险操作确认
        is_high_risk, risk_reason = self.is_high_risk_operation(tool_name, params)
        if is_high_risk:
            token_to_check = confirm_token or params.get("confirm_token")
            # 验证用户是否明确确认或提供了有效的确认令牌
            if user_confirmed:
                return SafetyGateDecision(
                    allowed=True,
                    requires_confirmation=False,
                    triggered_rollback=False,
                    reason="用户明确确认了高风险操作",
                    risk_score=0.5,
                    details={"tool_name": tool_name, "params": params, "confirmed": True},
                )
            elif token_to_check and self.verify_confirmation(str(token_to_check), tool_name, params):
                return SafetyGateDecision(
                    allowed=True,
                    requires_confirmation=False,
                    triggered_rollback=False,
                    reason="使用有效令牌确认了高风险操作",
                    risk_score=0.5,
                    details={"tool_name": tool_name, "params": params, "confirmed": True},
                )
            else:
                # 需要确认门禁
                new_token = self.issue_confirmation(tool_name, params)
                return SafetyGateDecision(
                    allowed=False,
                    requires_confirmation=True,
                    triggered_rollback=False,
                    violation_type="unconfirmed_high_risk_operation",
                    reason=risk_reason,
                    risk_score=0.7,
                    confirmation_token=new_token,
                    details={"tool_name": tool_name, "params": params},
                )

        # 5. 低风险操作：允许
        return SafetyGateDecision(
            allowed=True,
            requires_confirmation=False,
            triggered_rollback=False,
            reason="工具调用验证成功",
            risk_score=0.1,
            details={"tool_name": tool_name, "params": params},
        )


# 用于入口点调用的全局默认门禁实例
_DEFAULT_GATE = SafetyPolicyGate()


def validate_tool_call(
    tool_name: str,
    params: Optional[Dict[str, Any]] = None,
    gate: Optional[SafetyPolicyGate] = None,
    confirm_token: Optional[str] = None,
    user_confirmed: bool = False,
) -> SafetyGateDecision:
    """模块级入口点，用于根据安全策略规则验证工具调用。"""
    target_gate = gate or _DEFAULT_GATE
    return target_gate.validate_tool_call(
        tool_name=tool_name,
        params=params,
        confirm_token=confirm_token,
        user_confirmed=user_confirmed,
    )
