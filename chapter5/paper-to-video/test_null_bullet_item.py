"""测试幻灯片中包含 null 值的要点时仍能正常渲染 PNG。"""
import demo


def test_render_slide_skips_null_bullet(tmp_path, monkeypatch):
    """测试渲染幻灯片时跳过 null 类型的要点"""
    monkeypatch.setattr(demo, "SLIDES_DIR", tmp_path)
    slide = {
        "title": "示例标题",
        "subtitle": "示例副标题",
        "bullets": ["正常要点", None, "也是正常要点"],
    }
    path = demo.render_slide(slide, 0, 1)
    assert path.exists()
    assert path.stat().st_size > 0
    assert path == tmp_path / "slide_01.png"
