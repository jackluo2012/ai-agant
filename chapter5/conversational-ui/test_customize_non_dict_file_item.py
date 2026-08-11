"""测试 apply_edits files 列表含 null/非 dict 项时 customize 应丢弃而非崩溃。"""
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


def test_non_dict_file_items_dropped(frontend_dir):
    """测试非 dict 类型的文件项应被丢弃。"""
    kept = {"path": "src/theme.css", "content": "body { color: blue; }"}
    args = agent.customize(
        _fake_client(json.dumps({
            "summary": "s",
            "files": [None, kept, "x", 1],
        })),
        "model", frontend_dir, "把按钮改成蓝色")
    assert args["files"] == [kept]


def test_normal_edits_unchanged(frontend_dir):
    """测试合法参数不受影响。"""
    files = [{"path": "src/theme.css", "content": "body { color: red; }"}]
    args = agent.customize(
        _fake_client(json.dumps({"summary": "s", "files": files})),
        "model", frontend_dir, "把文字改成红色")
    assert args["files"] == files
