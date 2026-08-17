from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from .api import Course, CourseEvent, CourseGroup, Person, SearchResult, Unit
from .coursepage import CourseInfo
from .semester import semester_label
from .vvz import VvzCourse, VvzIndex, VvzListing, VvzNode

VIENNA = ZoneInfo("Europe/Vienna")
_DAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def _dot(parts: list[str | None]) -> str:
    return " · ".join(p for p in parts if p)


def _trim_num(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"\.0+$", "", value).rstrip(".")


def _local(iso: str) -> datetime | None:
    try:
        return datetime.fromisoformat(iso).astimezone(VIENNA)
    except (TypeError, ValueError):
        return None


def summarise_events(events: list[CourseEvent]) -> list[str]:
    buckets: dict[str, tuple[str, str | None, list[datetime]]] = {}
    for event in events:
        start = _local(event.begin)
        if start is None:
            continue
        end = _local(event.end)
        label = f"{_DAYS[start.weekday()]} {start:%H:%M}-{end:%H:%M}" if end else f"{_DAYS[start.weekday()]} {start:%H:%M}"
        key = f"{label}|{event.room or ''}"
        entry = buckets.setdefault(key, (label, event.room, []))
        entry[2].append(start)

    lines: list[str] = []
    for label, room, dates in buckets.values():
        dates.sort()
        if len(dates) > 1:
            span = f"{len(dates)}× ({dates[0]:%d.%m.%Y} to {dates[-1]:%d.%m.%Y})"
        else:
            span = f"{dates[0]:%d.%m.%Y}"
        lines.append(_dot([label, room, span]))
    return lines


def _lecturer_list(group: CourseGroup) -> str:
    return ", ".join(f"{l.name} (TutorIn)" if l.role == "tutor" else l.name for l in group.lecturers)


def _course_headline(course: Course) -> str:
    ects = _trim_num(course.ects)
    sws = _trim_num(course.sws)
    return _dot(
        [
            f"**{course.lv}** {course.type} {course.title}",
            f"{ects} ECTS" if ects else None,
            f"{sws} SWS" if sws else None,
        ]
    )


def render_course_search(result: SearchResult[Course], query: str) -> str:
    if not result.items:
        return (
            f'No courses found for "{query}".\n\n'
            "Tip: the search is free text over the whole catalogue. A semester code "
            '("logik 2026W"), an LV number ("180013") or a lecturer name '
            '("Schnieder logik") all work inside the query.'
        )
    lines = []
    for course in result.items:
        teachers: list[str] = []
        for group in course.groups:
            for lecturer in group.lecturers:
                if lecturer.role != "tutor" and lecturer.name not in teachers:
                    teachers.append(lecturer.name)
        lines.append(
            _dot(
                [
                    f"- {_course_headline(course)}",
                    course.semester,
                    ", ".join(teachers[:3]) or None,
                    f"{len(course.groups)} groups" if len(course.groups) > 1 else None,
                    course.url,
                ]
            )
        )
    more = " (raise `limit` for more)" if result.truncated else ""
    head = f'**{result.total}** hits for "{query}", showing {len(result.items)}{more}:'
    return "\n".join([head, "", *lines])


def render_course(course: Course, info: CourseInfo | None = None) -> str:
    ects = _trim_num(course.ects)
    sws = _trim_num(course.sws)
    out = [f"# {course.lv} · {course.type} {course.title}"]
    out.append(
        _dot(
            [
                semester_label(course.semester),
                course.title_other,
                course.type_desc,
                f"{ects} ECTS" if ects else None,
                f"{sws} SWS" if sws else None,
                "prüfungsimmanent (continuous assessment)"
                if course.continuous_assessment
                else "not prüfungsimmanent",
            ]
        )
    )
    meta = _dot(
        [
            f"Offered by: {course.offered_by}" if course.offered_by else None,
            course.codes,
            f"data as of {course.updated_at[:10]}" if course.updated_at else None,
        ]
    )
    if meta:
        out.append(meta)
    out.append(f"u:find page: {course.url}")

    for group in course.groups:
        out.append("")
        suffix = "" if len(course.groups) == 1 else f" of {len(course.groups)}"
        out.append(f"## Group {group.name}{suffix}")
        line = _dot(
            [
                f"Language: {', '.join(group.languages)}" if group.languages else None,
                f"{group.max_participants} places" if group.max_participants else "no place limit given",
                "livestream" if group.livestream else None,
            ]
        )
        if line:
            out.append(line)
        teaching = _lecturer_list(group)
        if teaching:
            out.append(f"Teaching: {teaching}")
        summary = summarise_events(group.events)
        if summary:
            out.append(f"Dates ({len(group.events)} in total):")
            out.extend(f"- {s}" for s in summary)
        else:
            out.append("Dates: none published yet.")
        preliminary = next((e for e in group.events if e.preliminary), None)
        if preliminary:
            start = _local(preliminary.begin)
            if start:
                out.append(f"Vorbesprechung: {start:%d.%m.%Y %H:%M}")
        if group.platforms:
            out.append(f"Platform: {', '.join(group.platforms)}")
        if group.ical_url:
            out.append(f"iCal: {group.ical_url}")

    if course.modules:
        out.append("")
        out.append("## Where it counts (Vorlesungsverzeichnis)")
        for module in course.modules:
            trail = " › ".join(p for p in (module.programme, module.module, module.entry) if p)
            out.append(f"- {trail}")

    if info is not None:
        sections = [
            ("Aims, contents and method", info.aims),
            ("Assessment and permitted materials", info.assessment),
            ("Minimum requirements and assessment criteria", info.requirements),
            ("Examination topics", info.exam_topics),
            ("Reading list", info.literature),
        ]
        filled = [(title, body) for title, body in sections if body]
        out.append("")
        out.append("## Information")
        if not filled:
            out.append("_No description published yet for this semester._")
        else:
            for title, body in filled:
                out.append(f"### {title}")
                out.append(body)
        if info.registration_windows or info.registration_url:
            out.append("")
            out.append("## Registration (An/Abmeldung)")
            out.extend(f"- {w}" for w in info.registration_windows)
            if info.registration_note:
                out.append(info.registration_note)
            if info.registration_url:
                out.append(f"Register: {info.registration_url}")
        if info.exam_dates:
            out.append("")
            out.append("## Exam dates")
            for label, link in info.exam_dates:
                out.append(f"- {label}" + (f" ({link})" if link else ""))
        if info.moodle_urls:
            out.append("")
            out.append(f"Moodle: {', '.join(info.moodle_urls)}")

    return "\n".join(out)


def render_departments(index: VvzIndex) -> str:
    out = [
        f"# Departments and study programmes, {semester_label(index.semester)}",
        "",
        f"{len(index.departments)} top-level entries, {len(index.programmes)} programmes below them.",
        "",
    ]
    for department in index.departments:
        count = sum(1 for p in index.programmes if p.department_path == department.path)
        suffix = f", {count} programmes" if count else ""
        out.append(f"- **{department.name}**, path `{department.path}`{suffix}")
    out.append("")
    out.append(
        "Use `get_program_courses` with a name or one of these paths to list every course "
        "of that unit in this semester. Paths change every semester."
    )
    return "\n".join(out)


def render_programmes(index: VvzIndex, nodes: list[VvzNode], filter_note: str) -> str:
    if not nodes:
        return f"No programmes matched {filter_note or 'the filter'} in {semester_label(index.semester)}."
    suffix = f" ({filter_note})" if filter_note else ""
    out = [f"# Programmes, {semester_label(index.semester)}{suffix}", "", f"{len(nodes)} entries:", ""]
    current: str | None = None
    for node in nodes:
        if node.department and node.department != current:
            current = node.department
            out.append(f"**{current}**")
        out.append(f"- {node.name}, path `{node.path}`")
    return "\n".join(out)


def _render_vvz_course(course: VvzCourse) -> str:
    head = _dot(
        [
            re.sub(r"\s+", " ", f"**{course.lv}** {course.type or ''} {course.title}").strip(),
            f"{course.ects} ECTS" if course.ects else None,
            "/".join(code for code, _ in course.labels) or None,
        ]
    )
    lines = [f"- {head}"]
    if course.subtitle:
        lines.append(f"  {course.subtitle}")
    for group in course.groups:
        times = "; ".join(
            _dot(
                [
                    " ".join(
                        p for p in (t.day, f"{t.start}-{t.end or '?'}" if t.start else None) if p
                    ),
                    f"{t.occurrences}×" if t.occurrences else None,
                ]
            )
            for t in group.times
        )
        parts = [
            f"Gr. {group.name}" if group.name else None,
            ", ".join(group.lecturers) or None,
            times or None,
        ]
        rendered = " | ".join(p for p in parts if p)
        if rendered:
            lines.append(f"  - {rendered}")
    return "\n".join(lines)


def render_listing(
    listing: VvzListing,
    limit: int = 400,
    module_filter: str | None = None,
    group_by_module: bool = True,
) -> str:
    out = [f"# {listing.name}"]
    out.append(
        _dot(
            [
                semester_label(listing.semester) if listing.semester else None,
                f"{len(listing.courses)} courses",
                f"{listing.module_count} module headings",
                f"VVZ path `{listing.path}`",
            ]
        )
    )
    if listing.last_changed:
        out.append(f"Last changed: {listing.last_changed}")
    if listing.semester_mismatch:
        out.append("")
        out.append(f"⚠️ {listing.semester_mismatch}")
    if listing.description:
        out.append("")
        clipped = listing.description[:400] + ("…" if len(listing.description) > 400 else "")
        out.append(f"> {clipped}")

    courses = listing.courses
    if module_filter:
        needle = module_filter.lower()
        courses = [c for c in courses if needle in " › ".join(c.module_trail).lower()]
        out.append("")
        out.append(f'Filtered to modules matching "{module_filter}": {len(courses)} courses.')

    shown = courses[:limit]
    unique = len({c.lv for c in shown})
    out.append("")

    if group_by_module:
        trail = None
        for course in shown:
            current = " › ".join(course.module_trail)
            if current != trail:
                trail = current
                out.append("")
                out.append(f"## {current or '(no module)'}")
            out.append(_render_vvz_course(course))
    else:
        out.extend(_render_vvz_course(c) for c in shown)

    if len(courses) > len(shown):
        out.append("")
        out.append(f"_… {len(courses) - len(shown)} more courses not shown (raise `limit`)._")
    out.append("")
    out.append(
        f"_{len(shown)} entries listed, {unique} distinct LV numbers. A course is repeated when "
        "it counts for several modules. Use get_course with an LV number for full details._"
    )
    return "\n".join(out)


def render_staff_search(result: SearchResult[Person], query: str) -> str:
    if not result.items:
        return f'No staff found for "{query}".'
    lines = [
        _dot(
            [
                f"- **{person.name}** (id `{person.id}`)",
                person.affiliations[0].unit if person.affiliations else None,
                person.emails[0] if person.emails else None,
                (person.rooms[0] if person.rooms else person.note),
                None if person.active else "inactive",
            ]
        )
        for person in result.items
    ]
    return "\n".join([f'**{result.total}** hits for "{query}", showing {len(result.items)}:', "", *lines])


def render_person(person: Person) -> str:
    out = [
        f"# {person.name}",
        _dot(
            [
                f"id `{person.id}`",
                person.username,
                "active" if person.active else "inactive",
                "on leave" if person.on_leave else None,
            ]
        ),
    ]
    if person.emails:
        out.append(f"Email: {', '.join(person.emails)}")
    if person.phones:
        out.append(f"Phone: {', '.join(person.phones)}")
    if person.rooms:
        out.append(f"Room: {', '.join(person.rooms)}")
    if person.note:
        out.append(person.note)
    if person.affiliations:
        out.append("")
        out.append("## Affiliations")
        for affiliation in person.affiliations:
            roles = f": {', '.join(affiliation.roles)}" if affiliation.roles else ""
            unit_id = f" (unit `{affiliation.unit_id}`)" if affiliation.unit_id else ""
            out.append(f"- {affiliation.unit}{roles}{unit_id}")
    out.append("")
    out.append(f"u:find page: {person.url}")
    out.append("_Courses taught: call search_courses with the surname plus a semester code._")
    return "\n".join(out)


def render_unit_search(result: SearchResult[Unit], query: str) -> str:
    if not result.items:
        return f'No organisational units found for "{query}".'
    lines = [
        _dot(
            [
                f"- **{unit.name}** (id `{unit.id}`)",
                unit.locations[0].address if unit.locations else None,
                unit.website,
            ]
        )
        for unit in result.items
    ]
    return "\n".join([f'**{result.total}** hits for "{query}", showing {len(result.items)}:', "", *lines])


def render_unit(unit: Unit) -> str:
    out = [
        f"# {unit.name}",
        _dot([f"id `{unit.id}`", unit.name_other, f"level {unit.level}" if unit.level else None]),
    ]
    if unit.hierarchy:
        out.append(" › ".join(unit.hierarchy))
    if unit.website:
        out.append(f"Website: {unit.website}")
    if unit.locations:
        out.append("")
        out.append("## Locations")
        for location in unit.locations:
            out.append("- " + ", ".join(p for p in (location.address, location.zip, location.town) if p))
    out.append("")
    out.append(f"u:find page: {unit.url}")
    return "\n".join(out)
