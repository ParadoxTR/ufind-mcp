from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import quote

from bs4 import BeautifulSoup, Tag

from .config import TTL_VVZ_COURSES, TTL_VVZ_INDEX, WEB_BASE, WEB_LANG
from .http import get

CONFIDENT_SCORE = 4

_WS = re.compile(r"\s+")
_PATH = re.compile(r"[?&]path=(\d+)")
_LEVEL = re.compile(r"level(\d)")
_COURSE_HREF = re.compile(r"[?&]lv=(\d+)")
_SEM_HREF = re.compile(r"[?&]semester=(\d{4}[WS])")


@dataclass(slots=True)
class VvzNode:
    path: str
    name: str
    kind: Literal["department", "programme"]
    department: str | None = None
    department_path: str | None = None
    url: str = ""


@dataclass(slots=True)
class VvzIndex:
    semester: str
    departments: list[VvzNode] = field(default_factory=list)
    programmes: list[VvzNode] = field(default_factory=list)


@dataclass(slots=True)
class VvzTime:
    day: str | None = None
    start: str | None = None
    end: str | None = None
    occurrences: int | None = None


@dataclass(slots=True)
class VvzGroup:
    name: str | None = None
    lecturers: list[str] = field(default_factory=list)
    times: list[VvzTime] = field(default_factory=list)


@dataclass(slots=True)
class VvzCourse:
    lv: str
    semester: str
    title: str
    subtitle: str | None = None
    type: str | None = None
    type_desc: str | None = None
    ects: str | None = None
    labels: list[tuple[str, str | None]] = field(default_factory=list)
    module_trail: list[str] = field(default_factory=list)
    groups: list[VvzGroup] = field(default_factory=list)
    url: str = ""


@dataclass(slots=True)
class VvzListing:
    path: str
    name: str
    semester: str
    semester_mismatch: str | None = None
    description: str | None = None
    last_changed: str | None = None
    courses: list[VvzCourse] = field(default_factory=list)
    module_count: int = 0
    child_paths: list[tuple[str, str]] = field(default_factory=list)


def _clean(value: str | None) -> str:
    return _WS.sub(" ", value or "").strip()


def _rich_text(el: Tag | None) -> str:
    if el is None:
        return ""
    html = re.sub(r"<br\s*/?>", " | ", str(el), flags=re.IGNORECASE)
    text = _clean(BeautifulSoup(html, "lxml").get_text())
    return re.sub(r"(\s*\|\s*)+", " | ", text).strip(" |")


def _path_of(href: str | None) -> str | None:
    if not href:
        return None
    match = _PATH.search(href)
    return match.group(1) if match else None


def _web_url(query: str) -> str:
    return f"{WEB_BASE}/{WEB_LANG}/{query}"


def _soup(body: str) -> BeautifulSoup:
    return BeautifulSoup(body, "lxml")


def _page_title(soup: BeautifulSoup, path: str) -> str:
    scoped = soup.select("div.usse-id-vvz h1")
    if scoped:
        title = _clean(scoped[-1].get_text())
        if title:
            return title
    for heading in reversed(soup.select("h1")):
        if "hidden" in (heading.get("class") or []):
            continue
        title = _clean(heading.get_text())
        if title:
            return title
    return f"path {path}"


async def get_index(semester: str) -> VvzIndex:
    body = await get(_web_url(f"vvz.html?semester={quote(semester)}"), TTL_VVZ_INDEX, "html")
    soup = _soup(body)
    containers = soup.select("div.usse-id-vvz") or [soup]
    index = VvzIndex(semester=semester)
    current: VvzNode | None = None

    for container in containers:
        for anchor in container.select("h2 > a.name, ul li > a.link"):
            path = _path_of(anchor.get("href"))
            name = _clean(anchor.get_text())
            if not path or not name:
                continue
            if "name" in (anchor.get("class") or []):
                current = VvzNode(
                    path=path,
                    name=name,
                    kind="department",
                    url=_web_url(f"vvz_sub.html?path={path}"),
                )
                index.departments.append(current)
            else:
                index.programmes.append(
                    VvzNode(
                        path=path,
                        name=name,
                        kind="programme",
                        department=current.name if current else None,
                        department_path=current.path if current else None,
                        url=_web_url(f"vvz_sub.html?path={path}"),
                    )
                )
    return index


_DIACRITICS = str.maketrans(
    {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "é": "e", "è": "e", "á": "a", "í": "i", "ó": "o", "ú": "u", "ç": "c"}
)


def _normalise(value: str) -> str:
    lowered = value.lower().translate(_DIACRITICS)
    return re.sub(r"[^a-z0-9]+", " ", lowered).strip()


def rank_nodes(nodes: list[VvzNode], needle: str) -> list[tuple[VvzNode, int]]:
    tokens = [t for t in _normalise(needle).split(" ") if t]
    if not tokens:
        return []
    scored: list[tuple[VvzNode, int]] = []
    for node in nodes:
        hay = _normalise(node.name)
        score = 0
        for token in tokens:
            if hay == token:
                score += 6
            elif re.search(rf"\b{re.escape(token)}\b", hay):
                score += 3
            elif token in hay:
                score += 1
        if score == 0:
            continue
        if hay.startswith(tokens[0]):
            score += 2
        score += max(0, 3 - len(hay) // 40)
        if re.search(r"auslaufend|discontinued", hay):
            score -= 2
        scored.append((node, score))
    scored.sort(key=lambda pair: (-pair[1], len(pair[0].name)))
    return scored


@dataclass(slots=True)
class Resolution:
    kind: Literal["resolved", "ambiguous", "notfound"]
    node: VvzNode | None = None
    alternatives: list[VvzNode] = field(default_factory=list)
    candidates: list[VvzNode] = field(default_factory=list)
    weak: bool = False


async def resolve_node(semester: str, ref: str) -> Resolution:
    index = await get_index(semester)
    trimmed = ref.strip()
    everything = index.departments + index.programmes

    if trimmed.isdigit():
        for node in everything:
            if node.path == trimmed:
                return Resolution(kind="resolved", node=node)
        return Resolution(
            kind="resolved",
            node=VvzNode(
                path=trimmed,
                name=f"path {trimmed}",
                kind="programme",
                url=_web_url(f"vvz_sub.html?path={trimmed}"),
            ),
        )

    ranked = rank_nodes(everything, trimmed)
    if not ranked:
        return Resolution(kind="notfound")
    best_node, best_score = ranked[0]
    weak = best_score < CONFIDENT_SCORE
    tie = len(ranked) > 1 and ranked[1][1] >= best_score
    if weak or tie:
        return Resolution(kind="ambiguous", candidates=[n for n, _ in ranked[:8]], weak=weak)
    return Resolution(kind="resolved", node=best_node, alternatives=[n for n, _ in ranked[1:8]])


def _parse_course_row(li: Tag, trail: list[str]) -> VvzCourse | None:
    what = li.select_one("a.what")
    if what is None:
        return None
    href = what.get("href") or ""
    lv_match = _COURSE_HREF.search(href)
    if not lv_match:
        return None
    lv = lv_match.group(1)
    sem_match = _SEM_HREF.search(href)
    semester = sem_match.group(1) if sem_match else ""

    groups: list[VvzGroup] = []
    for line in li.select("div.line2"):
        lecturers = [_clean(p.get_text()) for p in line.select("span.person.name")]
        lecturers = [name for name in lecturers if name]
        times: list[VvzTime] = []
        when = line.select_one("span.when")
        if when is not None:
            for slot in when.find_all("span", recursive=False):
                day = _clean(slot.select_one("span.wd").get_text()) if slot.select_one("span.wd") else None
                start = _clean(slot.select_one("span.from").get_text()) if slot.select_one("span.from") else None
                end = _clean(slot.select_one("span.to").get_text()) if slot.select_one("span.to") else None
                mult_el = slot.select_one("span.multiplier.text")
                occurrences = None
                if mult_el is not None:
                    try:
                        occurrences = int(_clean(mult_el.get_text()))
                    except ValueError:
                        occurrences = None
                if day or start:
                    times.append(VvzTime(day=day, start=start, end=end, occurrences=occurrences))
        name_el = line.select_one("span.group.name")
        name = _clean(name_el.get_text()) if name_el is not None else None
        if name or lecturers or times:
            groups.append(VvzGroup(name=name or None, lecturers=lecturers, times=times))

    type_el = li.select_one("abbr.type")
    ects_el = li.select_one("span.ects.text")
    subtitle_el = li.select_one("span.subwhat.text")
    labels: list[tuple[str, str | None]] = []
    for label in li.select("span.ufind-label span.content"):
        code = _clean(label.get_text())
        if code:
            labels.append((code, label.get("title")))

    return VvzCourse(
        lv=lv,
        semester=semester,
        title=_clean(what.get_text()),
        subtitle=_clean(subtitle_el.get_text()) if subtitle_el is not None else None,
        type=_clean(type_el.get_text()) if type_el is not None else None,
        type_desc=type_el.get("title") if type_el is not None else None,
        ects=_clean(ects_el.get_text()) if ects_el is not None else None,
        labels=labels,
        module_trail=[t for t in trail if t],
        groups=groups,
        url=_web_url(f"course.html?lv={lv}&semester={semester}"),
    )


async def get_node_courses(
    path: str,
    details: bool = True,
    expected_semester: str | None = None,
) -> VvzListing:
    url = _web_url(f"vvz_sub.html?path={quote(path)}" + ("&details=true" if details else ""))
    soup = _soup(await get(url, TTL_VVZ_COURSES, "html"))

    trail: list[str] = []
    courses: list[VvzCourse] = []
    module_count = 0

    for el in soup.select("h2.list, h3.list, h4.list, h5.list, li.list.course"):
        if el.name == "li":
            row = _parse_course_row(el, trail)
            if row is not None:
                courses.append(row)
            continue
        classes = " ".join(el.get("class") or [])
        level_match = _LEVEL.search(classes)
        level = int(level_match.group(1)) if level_match else 1
        link = el.select_one("a.link")
        name = _clean(link.get_text() if link is not None else el.get_text())
        del trail[level - 1 :]
        while len(trail) < level - 1:
            trail.append("")
        trail.append(name)
        module_count += 1

    seen: set[str] = set()
    child_paths: list[tuple[str, str]] = []
    for anchor in soup.select("ul li a.link, h2.list a.link, h3.list a.link, h4.list a.link"):
        child = _path_of(anchor.get("href"))
        if not child or child == path or child in seen:
            continue
        seen.add(child)
        child_paths.append((child, _clean(anchor.get_text())))

    semester = next((c.semester for c in courses if c.semester), "")
    mismatch = None
    if expected_semester and semester and semester != expected_semester:
        mismatch = (
            f"This VVZ path belongs to {semester}, not {expected_semester}. Path ids are "
            f"semester-specific. Look the programme up again for {expected_semester}."
        )

    return VvzListing(
        path=path,
        name=_page_title(soup, path),
        semester=semester or expected_semester or "",
        semester_mismatch=mismatch,
        description=_rich_text(soup.select_one("div.usse-id-vvz div.comment.text")) or None,
        last_changed=_clean(soup.select_one("div.version span.time").get_text())
        if soup.select_one("div.version span.time")
        else None,
        courses=courses,
        module_count=module_count,
        child_paths=child_paths,
    )


async def get_node_modules(path: str) -> tuple[str, list[tuple[str, str, int]]]:
    soup = _soup(await get(_web_url(f"vvz_sub.html?path={quote(path)}"), TTL_VVZ_COURSES, "html"))
    modules: list[tuple[str, str, int]] = []
    for el in soup.select("h2.list, h3.list, h4.list, h5.list"):
        link = el.select_one("a.link")
        name = _clean(link.get_text() if link is not None else el.get_text())
        if not name:
            continue
        classes = " ".join(el.get("class") or [])
        level_match = _LEVEL.search(classes)
        level = int(level_match.group(1)) if level_match else 1
        child = _path_of(link.get("href")) if link is not None else None
        modules.append((name, child or "", level))
    return _page_title(soup, path), modules
