from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import quote

from bs4 import BeautifulSoup, Tag

from .config import TTL_COURSE, WEB_BASE, WEB_LANG
from .http import get


@dataclass(slots=True)
class CourseInfo:
    aims: str | None = None
    assessment: str | None = None
    requirements: str | None = None
    exam_topics: str | None = None
    literature: str | None = None
    registration_note: str | None = None
    registration_windows: list[str] = field(default_factory=list)
    registration_url: str | None = None
    exam_dates: list[tuple[str, str | None]] = field(default_factory=list)
    moodle_urls: list[str] = field(default_factory=list)


def _block_text(el: Tag | None) -> str | None:
    if el is None:
        return None
    html = re.sub(r"<(p|br|div|li)\b[^>]*>", "\n", str(el), flags=re.IGNORECASE)
    html = re.sub(r"</(p|div|li|ul|ol|h[1-6])>", "\n", html, flags=re.IGNORECASE)
    raw = BeautifulSoup(html, "lxml").get_text()
    lines = [re.sub(r"\s+", " ", line).strip() for line in raw.split("\n")]
    text = "\n\n".join(line for line in lines if line).strip()
    return text or None


async def get_course_info(lv: str, semester: str) -> CourseInfo:
    url = f"{WEB_BASE}/{WEB_LANG}/course.html?lv={quote(lv)}&semester={quote(semester)}"
    soup = BeautifulSoup(await get(url, TTL_COURSE, "html"), "lxml")

    def section(css_class: str) -> str | None:
        return _block_text(soup.select_one(f"div.{css_class}.text"))

    exam_dates: list[tuple[str, str | None]] = []
    for li in soup.select("ul.usse-id-exams.events li"):
        label = re.sub(r"\s+", " ", li.get_text()).strip()
        if not label:
            continue
        anchor = li.select_one("a")
        href = anchor.get("href") if anchor is not None else None
        link = f"{WEB_BASE}/{WEB_LANG}/{href.lstrip('./')}" if href else None
        exam_dates.append((label, link))

    moodle = []
    for anchor in soup.select('a[href*="moodle.univie.ac.at/course"]'):
        href = anchor.get("href")
        if href and href not in moodle:
            moodle.append(href)

    register_anchor = soup.select_one("div.registrations.doit a")
    return CourseInfo(
        aims=section("comment"),
        assessment=section("performance"),
        requirements=section("preconditions"),
        exam_topics=section("examination"),
        literature=section("literature"),
        registration_note=_block_text(soup.select_one("div.registrations.textinfo")),
        registration_windows=[
            re.sub(r"\s+", " ", li.get_text()).strip()
            for li in soup.select("ul.registrations.list li")
            if re.sub(r"\s+", " ", li.get_text()).strip()
        ],
        registration_url=register_anchor.get("href") if register_anchor is not None else None,
        exam_dates=exam_dates,
        moodle_urls=moodle,
    )
