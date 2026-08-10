"""测试空题目集时准确率汇总不产生除零错误。"""
import os
import json
import sys
from pathlib import Path
from types import SimpleNamespace

# 添加当前目录到路径，以便导入 demo 模块
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

import demo as cfm


class _Resp:
    """模拟 LLM 响应对象"""
    def __init__(self):
        self.choices = [
            SimpleNamespace(
                message=SimpleNamespace(content="FINAL ANSWER: 1", tool_calls=None)
            )
        ]


class _Completions:
    """模拟聊天完成接口"""
    @staticmethod
    def create(**kwargs):
        return _Resp()


class _Chat:
    """模拟聊天接口"""
    completions = _Completions()


class _Client:
    """模拟 LLM 客户端"""
    chat = _Chat()


def test_empty_problems_summary_no_zerodiv(tmp_path, monkeypatch, capsys):
    """测试空题目集时准确率汇总不产生除零错误"""
    path = tmp_path / "empty.json"
    path.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(cfm, "build_client_and_model", lambda model_override=None: (_Client(), "fake"))
    rc = cfm.main(["--problems", str(path), "--mode", "cot"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "0/0" in out
    assert "N/A" in out


def test_nonempty_summary_still_shows_percent(tmp_path, monkeypatch, capsys):
    """测试非空题目集仍能正确显示百分比"""
    path = tmp_path / "one.json"
    path.write_text(
        json.dumps([{"id": "1", "topic": "t", "question": "1+1?", "answer": 1}]),
        encoding="utf-8",
    )
    monkeypatch.setattr(cfm, "build_client_and_model", lambda model_override=None: (_Client(), "fake"))
    rc = cfm.main(["--problems", str(path), "--mode", "cot"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "1/1" in out
    assert "%" in out
