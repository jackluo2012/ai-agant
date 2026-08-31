"""实验 10-4 的真实大学网站输入数据。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass(frozen=True)
class Website:
    """一个待搜索的真实网站条目。"""

    name: str      # 站点短名
    college: str   # 所属学院/中心名称
    url: str       # 真实页面 URL


# 默认搜索目标教师
TARGET = "Andrew Ng"

# 以下全部是真实属于斯坦福大学的网页，刻意混用目录页与院系/中心档案页，
# 模拟用户自备网站列表的真实形态。URL 是实验数据而非模拟内容；
# 每个 Worker 都会为这些页面启动独立的 Playwright 浏览器上下文。
DEFAULT_SITES: List[Website] = [
    Website("medicine-profiles", "School of Medicine", "https://med.stanford.edu/profiles/browse"),
    Website("law-faculty", "Stanford Law School", "https://law.stanford.edu/directory/?tax_and_terms=1067"),
    Website("education-faculty", "Graduate School of Education", "https://ed.stanford.edu/faculty"),
    Website("business-faculty", "Graduate School of Business", "https://www.gsb.stanford.edu/faculty-research/faculty"),
    Website("sustainability-faculty", "Doerr School of Sustainability", "https://sustainability.stanford.edu/people/faculty"),
    Website("humanities-faculty", "School of Humanities and Sciences", "https://humsci.stanford.edu/about/leadership-and-administration/deans-office"),
    Website("engineering-faculty", "School of Engineering", "https://engineering.stanford.edu/faculty-research/faculty"),
    Website("computer-science", "School of Engineering / Computer Science", "https://www.cs.stanford.edu/people/faculty"),
    Website("stanford-profiles", "Stanford Profiles", "https://profiles.stanford.edu/andrew-ng"),
    Website("human-ai", "Stanford HAI", "https://hai.stanford.edu/people/andrew-ng"),
]


def load_sites(path: str | None, limit: int | None = None) -> List[Website]:
    """加载网站列表：优先读取用户提供的 JSON，否则使用内置默认列表。

    Args:
        path: 网站 JSON 文件路径（每项含 name/college/url）；None 使用默认
        limit: 最多保留前 N 个站点；None 表示不限制

    Returns:
        Website 列表

    Raises:
        ValueError: 网站列表为空，或存在非 HTTP(S) 的 URL
    """
    if path:
        # 从用户提供的 JSON 文件读取站点配置
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        sites = [Website(**item) for item in raw]
    else:
        sites = list(DEFAULT_SITES)
    # 按需截断站点数量
    if limit is not None:
        sites = sites[:limit]
    # 基本校验：列表非空且全部是合法的 HTTP(S) 地址
    if not sites:
        raise ValueError("网站列表不能为空")
    for site in sites:
        if not site.url.startswith(("http://", "https://")):
            raise ValueError(f"{site.name} 不是 HTTP(S) URL")
    return sites
