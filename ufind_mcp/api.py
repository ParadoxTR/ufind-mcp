from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Generic, Literal, TypeVar
from urllib.parse import quote

from defusedxml.ElementTree import fromstring
from xml.etree.ElementTree import Element

from .config import (
    API_BASE,
    API_PAGE_SIZE,
    OTHER_LANG,
    TTL_COURSE,
    TTL_ENTITY,
    TTL_SEARCH,
    WEB_BASE,
    WEB_LANG,
)
from .http import get

XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"


@dataclass(slots=True)
class Lecturer:
    name: str
    role: Literal["lecturer", "tutor", "other"]
    id: str | None = None
    role_code: str | None = None


@dataclass(slots=True)
class CourseEvent:
    begin: str
    end: str
    preliminary: bool = False
    room: str | None = None
    address: str | None = None
    town: str | None = None


@dataclass(slots=True)
class CourseGroup:
    id: str
    name: str
    registration_id: str | None = None
    max_participants: int | None = None
    livestream: bool = False
    languages: list[str] = field(default_factory=list)
    lecturers: list[Lecturer] = field(default_factory=list)
    events: list[CourseEvent] = field(default_factory=list)
    platforms: list[str] = field(default_factory=list)
    ical_url: str | None = None


@dataclass(slots=True)
class CourseModule:
    path: str
    programme: str
    module: str | None = None
    entry: str | None = None


@dataclass(slots=True)
class Course:
    lv: str
    semester: str
    title: str
    type: str
    title_other: str | None = None
    type_desc: str | None = None
    ects: str | None = None
    sws: str | None = None
    continuous_assessment: bool = False
    codes: str | None = None
    offered_by: str | None = None
    offered_by_id: str | None = None
    modules: list[CourseModule] = field(default_factory=list)
    groups: list[CourseGroup] = field(default_factory=list)
    updated_at: str | None = None
    url: str = ""


@dataclass(slots=True)
class Affiliation:
    unit: str
    unit_id: str | None = None
    roles: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Person:
    id: str
    name: str
    firstname: str
    lastname: str
    title: str | None = None
    username: str | None = None
    active: bool = True
    on_leave: bool | None = None
    note: str | None = None
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    rooms: list[str] = field(default_factory=list)
    affiliations: list[Affiliation] = field(default_factory=list)
    url: str = ""


@dataclass(slots=True)
class Location:
    address: str | None = None
    zip: str | None = None
    town: str | None = None


@dataclass(slots=True)
class Unit:
    id: str
    name: str
    name_other: str | None = None
    level: str | None = None
    path: str | None = None
    website: str | None = None
    locations: list[Location] = field(default_factory=list)
    hierarchy: list[str] = field(default_factory=list)
    url: str = ""


T = TypeVar("T")


@dataclass(slots=True)
class SearchResult(Generic[T]):
    total: int
    items: list[T]
    truncated: bool


def _txt(el: Element | None) -> str:
    if el is None:
        return ""
    return (el.text or "").strip()


def _pick_lang(parent: Element, tag: str, want: str) -> str:
    nodes = parent.findall(tag)
    if not nodes:
        return ""
    for node in nodes:
        if node.get(XML_LANG) == want:
            return _txt(node)
    return _txt(nodes[0])


def _int_or_none(value: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_lecturers(group: Element) -> list[Lecturer]:
    out: list[Lecturer] = []
    for node in group.findall("lecturers/lecturer"):
        code = node.get("type")
        role: Literal["lecturer", "tutor", "other"] = (
            "tutor" if code == "T" else "lecturer" if code == "V" else "other"
        )
        name = " ".join(p for p in (_txt(node.find("firstname")), _txt(node.find("lastname"))) if p)
        out.append(Lecturer(name=name, role=role, id=node.get("id"), role_code=code))
    return out


def _parse_events(group: Element) -> list[CourseEvent]:
    out: list[CourseEvent] = []
    for node in group.findall("wwlong/wwevent"):
        loc = node.find("location")
        town = None
        if loc is not None:
            town = " ".join(p for p in (_txt(loc.find("zip")), _txt(loc.find("town"))) if p) or None
        out.append(
            CourseEvent(
                begin=node.get("begin", ""),
                end=node.get("end", ""),
                preliminary=node.get("vorbesprechung") == "true",
                room=(_txt(loc.find("room")) or None) if loc is not None else None,
                address=(_txt(loc.find("address")) or None) if loc is not None else None,
                town=town,
            )
        )
    return out


def parse_course(node: Element) -> Course:
    lv = node.get("id", "")
    semester = node.get("when", "")

    groups: list[CourseGroup] = []
    for g in node.findall("groups/group"):
        gid = g.get("id", "")
        name = gid.rsplit("-", 1)[-1] if "-" in gid else gid
        groups.append(
            CourseGroup(
                id=gid,
                name=name,
                registration_id=g.get("register"),
                max_participants=_int_or_none(_txt(g.find("maxparticipants"))),
                livestream=_txt(g.find("livestream")).lower() == "true",
                languages=[
                    _pick_lang(lang, "title", WEB_LANG) for lang in g.findall("languages/language")
                ],
                lecturers=_parse_lecturers(g),
                events=_parse_events(g),
                platforms=[_txt(p) for p in g.findall("platform") if _txt(p)],
                ical_url=f"{API_BASE}/courses/{lv}/{semester}/{name}/ww.ics" if name else None,
            )
        )

    type_node = node.find("type")
    chapters = node.find("chapters")
    modules: list[CourseModule] = []
    if chapters is not None:
        for chapter in chapters.findall("chapter"):
            modules.append(
                CourseModule(
                    path=chapter.get("path", ""),
                    programme=_pick_lang(chapter, "category", WEB_LANG),
                    module=_pick_lang(chapter, "subcategory", WEB_LANG) or None,
                    entry=_pick_lang(chapter, "name", WEB_LANG) or None,
                )
            )

    offered_by = node.find("offeredby")
    title = _pick_lang(node, "longname", WEB_LANG)
    other = _pick_lang(node, "longname", OTHER_LANG)
    return Course(
        lv=lv,
        semester=semester,
        title=title,
        title_other=other if other and other != title else None,
        type=_txt(type_node),
        type_desc=type_node.get("desc") if type_node is not None else None,
        ects=_txt(node.find("ects")) or None,
        sws=_txt(node.find("sws")) or None,
        continuous_assessment=_txt(node.find("immanent")).lower() == "true",
        codes=(_txt(chapters.find("codes")) or None) if chapters is not None else None,
        offered_by=_txt(offered_by) or None,
        offered_by_id=offered_by.get("id") if offered_by is not None else None,
        modules=modules,
        groups=groups,
        updated_at=node.get("version"),
        url=f"{WEB_BASE}/{WEB_LANG}/course.html?lv={lv}&semester={semester}",
    )


def parse_person(node: Element) -> Person:
    pid = node.get("id", "")
    firstname = _txt(node.find("firstname"))
    lastname = _txt(node.find("lastname"))
    title = _txt(node.find("title")) or None
    affiliations = [
        Affiliation(
            unit=_pick_lang(unit, "name", WEB_LANG) or _txt(unit.find("name")),
            unit_id=unit.get("id"),
            roles=[_txt(r) for r in unit.findall("role") if _txt(r)],
        )
        for unit in node.findall("affiliations/unit")
    ]
    on_leave_node = node.find("onleave")
    return Person(
        id=pid,
        name=" ".join(p for p in (title or "", firstname, lastname) if p),
        firstname=firstname,
        lastname=lastname,
        title=title,
        username=node.get("username"),
        active=node.get("active") != "false",
        on_leave=None if on_leave_node is None else _txt(on_leave_node).lower() == "true",
        note=_pick_lang(node, "comment", WEB_LANG) or None,
        emails=[_txt(e) for e in node.findall("contact/email") if _txt(e)],
        phones=[_txt(e) for e in node.findall("contact/tel") if _txt(e)],
        rooms=[_txt(e) for e in node.findall("contact/room") if _txt(e)],
        affiliations=affiliations,
        url=f"{WEB_BASE}/{WEB_LANG}/person.html?id={pid}",
    )


def parse_unit(node: Element) -> Unit:
    uid = node.get("id", "")
    name = _pick_lang(node, "name", WEB_LANG) or _txt(node.find("name"))
    other = _pick_lang(node, "name", OTHER_LANG)
    return Unit(
        id=uid,
        name=name,
        name_other=other if other and other != name else None,
        level=node.get("level"),
        path=node.get("path"),
        website=_txt(node.find("url")) or None,
        locations=[
            Location(
                address=_txt(loc.find("address")) or None,
                zip=_txt(loc.find("zip")) or None,
                town=_txt(loc.find("town")) or None,
            )
            for loc in node.findall("locations/location")
        ],
        hierarchy=[
            _pick_lang(level, "title", WEB_LANG)
            for level in node.findall("structure/level")
            if _pick_lang(level, "title", WEB_LANG)
        ],
        url=f"{WEB_BASE}/{WEB_LANG}/unit.html?id={uid}",
    )


async def _search_paged(
    resource: str,
    query: str,
    limit: int,
    element: str,
    parse: Callable[[Element], T],
) -> SearchResult[T]:
    items: list[T] = []
    total = 0
    offset = 0
    while len(items) < limit:
        url = f"{API_BASE}/{resource}?query={quote(query)}" + (f"&from={offset}" if offset else "")
        root = fromstring(await get(url, TTL_SEARCH, "xml"))
        total = _int_or_none(_txt(root.find("results"))) or total
        nodes = root.findall(element)
        if not nodes:
            break
        for node in nodes:
            if len(items) >= limit:
                break
            items.append(parse(node))
        offset += len(nodes)
        if offset >= total:
            break
        if len(nodes) < API_PAGE_SIZE:
            break
    return SearchResult(total=total, items=items, truncated=total > len(items))


async def search_courses(query: str, limit: int = 10) -> SearchResult[Course]:
    return await _search_paged("courses", query, limit, "course", parse_course)


async def search_exams(query: str, limit: int = 10) -> SearchResult[Course]:
    return await _search_paged("exams", query, limit, "course", parse_course)


async def search_staff(query: str, limit: int = 10) -> SearchResult[Person]:
    return await _search_paged("staff", query, limit, "person", parse_person)


async def search_units(query: str, limit: int = 10) -> SearchResult[Unit]:
    return await _search_paged("units", query, limit, "unit", parse_unit)


async def get_course(lv: str, semester: str) -> Course:
    url = f"{API_BASE}/courses/{quote(lv)}/{quote(semester)}"
    node = fromstring(await get(url, TTL_COURSE, "xml"))
    if node.tag != "course":
        raise ValueError(f"No course {lv} in {semester}.")
    return parse_course(node)


_PHOTO = re.compile(r"<photo>.*?</photo>", re.DOTALL)


async def get_staff(person_id: str) -> Person:
    url = f"{API_BASE}/staff/{quote(person_id)}"
    body = _PHOTO.sub("", await get(url, TTL_ENTITY, "xml"))
    node = fromstring(body)
    if node.tag != "person":
        raise ValueError(f"No person with id {person_id}.")
    return parse_person(node)


async def get_unit(unit_id: str) -> Unit:
    url = f"{API_BASE}/units/{quote(unit_id)}"
    node = fromstring(await get(url, TTL_ENTITY, "xml"))
    if node.tag != "unit":
        raise ValueError(f"No organisational unit with id {unit_id}.")
    return parse_unit(node)


async def get_ical(lv: str, semester: str, group: str = "1") -> str:
    url = f"{API_BASE}/courses/{quote(lv)}/{quote(semester)}/{quote(group)}/ww.ics"
    return await get(url, TTL_COURSE, "text")
