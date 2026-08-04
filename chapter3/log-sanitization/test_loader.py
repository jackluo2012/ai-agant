"""
评测用例加载器
===============
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any

# 添加项目根目录到路径
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from config import EVAL_FRAMEWORK_PATH


class TestCaseLoader:
    """从 user-memory-evaluation 评测框架加载测试用例"""

    def __init__(self):
        self.eval_framework_path = EVAL_FRAMEWORK_PATH
        if not self.eval_framework_path.exists():
            raise ValueError(f"评测框架未找到: {self.eval_framework_path}")

    def get_all_test_cases(self) -> List[Dict[str, Any]]:
        """获取所有可用的测试用例"""
        script = """
import sys
import json
from pathlib import Path
import io

# 抑制 rich 控制台输出
import rich.console
rich.console.Console = lambda *args, **kwargs: type('FakeConsole', (), {
    'print': lambda self, *a, **k: None,
    '__getattr__': lambda self, name: lambda *a, **k: None
})()

# 重定向输出
old_stdout = sys.stdout
sys.stdout = io.StringIO()

try:
    from framework import UserMemoryEvaluationFramework

    framework = UserMemoryEvaluationFramework()
    test_cases = []

    for tc in framework.list_test_cases():
        test_cases.append({
            'test_id': tc.test_id,
            'category': tc.category,
            'title': tc.title,
            'description': tc.description,
            'num_conversations': len(tc.conversation_histories),
            'user_question': tc.user_question
        })

    # 恢复 stdout 以输出 JSON
    sys.stdout = old_stdout
    print(json.dumps(test_cases, ensure_ascii=False))

except Exception as e:
    sys.stdout = old_stdout
    print(json.dumps([]))
"""

        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=self.eval_framework_path,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print(f"获取测试用例出错: {result.stderr}")
            return []

        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            print(f"解析测试用例 JSON 失败")
            return []

    def get_layer3_test_cases(self) -> List[Dict[str, Any]]:
        """仅获取 Layer 3 测试用例（最复杂）"""
        all_cases = self.get_all_test_cases()
        return [tc for tc in all_cases if tc['category'] == 'layer3']

    def get_test_case_conversations(self, test_id: str) -> List[Dict[str, Any]]:
        """获取特定测试用例的详细对话历史"""
        script = f"""
import sys
import json
from pathlib import Path
import io

# 重定向 stdout 以抑制框架的打印输出
old_stdout = sys.stdout
sys.stdout = io.StringIO()

try:
    from framework import UserMemoryEvaluationFramework

    framework = UserMemoryEvaluationFramework()
    tc = framework.get_test_case("{test_id}")

    # 恢复 stdout 以输出我们的 JSON
    sys.stdout = old_stdout

    if not tc:
        print(json.dumps([], ensure_ascii=False))
    else:
        conversations = []
        for conv in tc.conversation_histories:
            conv_data = {{
                'conversation_id': conv.conversation_id,
                'timestamp': conv.timestamp,
                'messages': []
            }}

            for msg in conv.messages:
                msg_data = {{
                    'role': msg.role.value,
                    'content': msg.content
                }}
                # 添加元数据（如果存在）
                if hasattr(msg, 'metadata'):
                    msg_data['metadata'] = msg.metadata
                conv_data['messages'].append(msg_data)

            conversations.append(conv_data)

        print(json.dumps(conversations, ensure_ascii=False))

except Exception as e:
    import traceback
    sys.stdout = old_stdout
    sys.stderr.write(traceback.format_exc())
    print(json.dumps([], ensure_ascii=False))
"""

        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=self.eval_framework_path,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print(f"获取对话历史出错: {result.stderr}")
            return []

        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as e:
            print(f"解析对话历史 JSON 失败: {e}")
            if result.stdout:
                print(f"stdout (前 500 字符): {result.stdout[:500]}")
            if result.stderr:
                print(f"stderr (前 500 字符): {result.stderr[:500]}")
            return []

    def format_conversation_text(self, conversation: Dict[str, Any]) -> str:
        """将对话格式化为可读文本"""
        lines = []
        lines.append(f"对话 ID: {conversation['conversation_id']}")
        lines.append(f"时间戳: {conversation['timestamp']}")
        lines.append("-" * 50)

        for msg in conversation['messages']:
            role = msg['role'].upper()
            content = msg['content']
            lines.append(f"{role}: {content}")
            lines.append("")  # 消息之间空一行

        return "\n".join(lines)
