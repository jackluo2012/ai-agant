"""测试 apply_edits JSON 格式错误时 customize 应干净处理。"""
import os
import sys
import types

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


def test_malformed_json_degrades_to_empty_files(tmp_path):
    """测试格式错误的 JSON 应降级为空文件列表。"""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "App.jsx").write_text("// app", encoding="utf-8")
    (tmp_path / "src" / "theme.css").write_text("/* css */", encoding="utf-8")
    args = agent.customize(
        _fake_client('{"files": [{"path": "src/theme.css",}],'),  # 尾部有垃圾字符
        "model",
        tmp_path,
        "把按钮改成蓝色",
    )
    assert args["files"] == []


def test_valid_json_still_returns_files(tmp_path):
    """测试有效的 JSON 应正常返回文件列表。"""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "App.jsx").write_text("// app", encoding="utf-8")
    (tmp_path / "src" / "theme.css").write_text("/* css */", encoding="utf-8")
    files = [{"path": "src/theme.css", "content": "body { color: red; }"}]
    import json
    args = agent.customize(
        _fake_client(json.dumps({"summary": "s", "files": files})),
        "model",
        tmp_path,
        "把文字改成红色",
    )
    assert args["files"] == files
