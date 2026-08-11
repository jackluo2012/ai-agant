"""模型返回的 apply_edits 参数缺字段/为 null 时，customize 应干净处理而非崩溃。"""
import os
import sys
import json
import types

import pytest

# 添加项目根目录到路径
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

import agent


def _fake_client(arguments):
    """创建假的 LLM 客户端用于测试。

    Args:
        arguments: 工具调用的参数字符串

    Returns:
        模拟的客户端对象
    """
    fn = types.SimpleNamespace(name="apply_edits", arguments=arguments)
    tc = types.SimpleNamespace(id="c1", type="function", function=fn)
    msg = types.SimpleNamespace(tool_calls=[tc], content=None)
    resp = types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])
    completions = types.SimpleNamespace(create=lambda **kw: resp)
    return types.SimpleNamespace(chat=types.SimpleNamespace(completions=completions))


@pytest.fixture
def frontend_dir(tmp_path):
    """创建临时前端目录用于测试。

    Args:
        tmp_path: pytest 提供的临时路径

    Returns:
        临时目录路径
    """
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "App.jsx").write_text("// app", encoding="utf-8")
    (tmp_path / "src" / "theme.css").write_text("/* css */", encoding="utf-8")
    return tmp_path


def test_files_null_normalized_to_empty(frontend_dir):
    """测试 files 为显式 null 时应归一化为空列表。"""
    args = agent.customize(
        _fake_client(json.dumps({"summary": "s", "files": None})),
        "model", frontend_dir, "把按钮改成蓝色")
    assert args["files"] == []


def test_file_entry_missing_path_rejected_cleanly(frontend_dir):
    """测试文件项缺 path 时应清晰的白名单拒绝（RuntimeError），而非 KeyError。"""
    with pytest.raises(RuntimeError, match="白名单"):
        agent.customize(
            _fake_client(json.dumps({"summary": "s", "files": [{"content": "x"}]})),
            "model", frontend_dir, "把按钮改成蓝色")


def test_normal_edits_pass(frontend_dir):
    """测试合法参数不受影响。"""
    files = [{"path": "src/theme.css", "content": "body { color: red; }"}]
    args = agent.customize(
        _fake_client(json.dumps({"summary": "s", "files": files})),
        "model", frontend_dir, "把文字改成红色")
    assert args["files"] == files
