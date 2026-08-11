"""测试 ffprobe 输出为 N/A（无时长元数据）时，ffprobe_duration 应给出清晰报错。"""
import pytest

import demo


def test_ffprobe_duration_na(monkeypatch):
    """测试 ffprobe 返回 N/A 时的错误处理"""
    monkeypatch.setattr(demo, "run", lambda *a, **k: "N/A\n")
    with pytest.raises(RuntimeError, match="时长"):
        demo.ffprobe_duration("no_duration.bin")


def test_ffprobe_duration_empty(monkeypatch):
    """测试 ffprobe 返回空字符串时的错误处理"""
    monkeypatch.setattr(demo, "run", lambda *a, **k: "")
    with pytest.raises(RuntimeError, match="时长"):
        demo.ffprobe_duration("empty.bin")


def test_ffprobe_duration_normal(monkeypatch):
    """测试正常情况下的时长读取"""
    monkeypatch.setattr(demo, "run", lambda *a, **k: "12.345\n")
    assert demo.ffprobe_duration("a.mp4") == 12.345
