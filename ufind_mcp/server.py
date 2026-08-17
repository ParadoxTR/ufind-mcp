from __future__ import annotations

from typing import Annotated

try:
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:
    from mcp.server.fastmcp import FastMCP as _Server

from mcp.types import ToolAnnotations
from pydantic import Field

from . import api, format as fmt
from .cache import cache_location
from .coursepage import get_course_info
from .semester import current_semester, resolve_semester, semester_label, semester_range
from .vvz import (
    get_index,
    get_node_courses,
    get_node_modules,
    rank_nodes,
    resolve_node,
)

SEMESTER_DESC = (
    'Semester code such as "2026W" (winter 2026/27) or "2027S". Also accepts "current", '
    '"next", "previous". Defaults to the current semester.'
)

READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=True)

INSTRUCTIONS = (
    "u:find is the course catalogue of the University of Vienna. "
    "Course search is free text: a semester code, LV number or lecturer name can go straight "
    "into the query. To answer 'which courses does department/programme X offer this semester', "
    "use get_program_courses, which returns the complete list in one call. VVZ paths are "
    "semester-specific, so always resolve a programme for the semester being asked about. "
    "Data for a semester that has not started yet is incomplete: descriptions and registration "
    "windows are often still empty."
)

mcp = _Server("ufind", instructions=INSTRUCTIONS, version="0.1.0")

Semester = Annotated[str | None, Field(default=None, description=SEMESTER_DESC)]


@mcp.tool(annotations=READ_ONLY)
async def search_courses(
    query: Annotated[
        str,
        Field(description='Keywords, e.g. "logik", "180013", "Schnieder sprachphilosophie".'),
    ],
    semester: Annotated[
        str | None,
        Field(default=None, description=SEMESTER_DESC + ' Pass "" to search all semesters.'),
    ] = None,
    limit: Annotated[int, Field(default=10, ge=1, le=60, description="Maximum courses.")] = 10,
) -> str:
    """Free-text search over all u:find courses (Lehrveranstaltungen).

    Matches titles, LV numbers, lecturer names and semester codes. Use for
    "is there a course about X" or "what does lecturer Y teach".
    """
    code = None if semester == "" else resolve_semester(semester)
    full_query = f"{query} {code}" if code else query
    result = await api.search_courses(full_query, limit)
    head = f"Semester filter: {semester_label(code)}\n\n" if code else ""
    return head + fmt.render_course_search(result, full_query)


@mcp.tool(annotations=READ_ONLY)
async def get_course(
    lv: Annotated[str, Field(description='LV number, e.g. "180013" or "051010".')],
    semester: Semester = None,
    include_description: Annotated[
        bool,
        Field(
            default=True,
            description="Also read the course web page for description, registration window and "
            "exam dates (one extra request).",
        ),
    ] = True,
) -> str:
    """Everything about one course: type, ECTS, groups, lecturers, all dates with rooms,
    curriculum placement, plus description, assessment, registration
    window and exam dates."""
    code = resolve_semester(semester)
    course = await api.get_course(lv.strip(), code)
    info = await get_course_info(course.lv, course.semester) if include_description else None
    return fmt.render_course(course, info)


@mcp.tool(annotations=READ_ONLY)
async def get_course_schedule(
    lv: Annotated[str, Field(description="LV number.")],
    semester: Semester = None,
    group: Annotated[
        str | None, Field(default=None, description='Group number, e.g. "1". Omit for all groups.')
    ] = None,
    as_ical: Annotated[
        bool, Field(default=False, description="Return the raw .ics feed instead of a summary.")
    ] = False,
) -> str:
    """Dates, times and rooms of a course group, as a weekday summary plus every single
    date, or as an iCal feed to subscribe to."""
    code = resolve_semester(semester)
    if as_ical:
        ics = await api.get_ical(lv.strip(), code, group or "1")
        return f"iCal feed for {lv} group {group or '1'} ({code}):\n\n```\n{ics.strip()}\n```"

    course = await api.get_course(lv.strip(), code)
    groups = [g for g in course.groups if g.name == group] if group else course.groups
    if not groups:
        available = ", ".join(g.name for g in course.groups) or "none"
        return f'Course {course.lv} ({code}) has no group "{group}". Available: {available}.'

    out = [
        f"# Schedule: {course.lv} {course.type} {course.title} ({semester_label(course.semester)})"
    ]
    max_dates = 40
    for g in groups:
        out.append("")
        teachers = ", ".join(l.name for l in g.lecturers)
        out.append(f"## Group {g.name}" + (f": {teachers}" if teachers else ""))
        summary = fmt.summarise_events(g.events)
        if not summary:
            out.append("No dates published.")
        else:
            out.extend(f"- {s}" for s in summary)
            out.append("")
            out.append("All dates:")
            for event in g.events[:max_dates]:
                suffix = " (Vorbesprechung)" if event.preliminary else ""
                out.append(
                    f"- {event.begin[:16].replace('T', ' ')}-{event.end[11:16]} "
                    f"{event.room or ''}{suffix}".rstrip()
                )
            if len(g.events) > max_dates:
                out.append(f"- … {len(g.events) - max_dates} more (see the iCal feed)")
        if g.ical_url:
            out.append(f"iCal: {g.ical_url}")
    return "\n".join(out)


@mcp.tool(annotations=READ_ONLY)
async def list_departments(semester: Semester = None) -> str:
    """All top-level units of the Vorlesungsverzeichnis for a semester: the
    'Studienprogrammleitung' (SPL) departments plus special categories, each with the VVZ
    path needed to list its courses."""
    code = resolve_semester(semester)
    return fmt.render_departments(await get_index(code))


@mcp.tool(annotations=READ_ONLY)
async def list_programs(
    semester: Semester = None,
    department: Annotated[
        str | None,
        Field(default=None, description='Restrict to one department: name ("Informatik") or VVZ path.'),
    ] = None,
    query: Annotated[
        str | None, Field(default=None, description='Filter by programme name, e.g. "Master Informatik".')
    ] = None,
    limit: Annotated[int, Field(default=60, ge=1, le=600, description="Maximum entries.")] = 60,
) -> str:
    """Degree programmes and extension curricula (Bachelor, Master, Doktorat,
    Erweiterungscurriculum) offered in a semester, optionally filtered by department or name."""
    code = resolve_semester(semester)
    index = await get_index(code)
    nodes = index.programmes
    notes: list[str] = []

    if department:
        needle = department.strip()
        if needle.isdigit():
            match = next((d for d in index.departments if d.path == needle), None)
        else:
            ranked = rank_nodes(index.departments, needle)
            match = ranked[0][0] if ranked else None
        if match is None:
            return f'No department matched "{department}" in {semester_label(code)}.'
        nodes = [p for p in nodes if p.department_path == match.path]
        notes.append(f"department: {match.name}")

    if query:
        allowed = {node.path for node, _ in rank_nodes(index.programmes, query)}
        nodes = [p for p in nodes if p.path in allowed]
        notes.append(f'name: "{query}"')

    capped = nodes[:limit]
    text = fmt.render_programmes(index, capped, ", ".join(notes))
    if len(nodes) > len(capped):
        text += f"\n\n_… {len(nodes) - len(capped)} more (raise `limit`)._"
    return text


@mcp.tool(annotations=READ_ONLY)
async def get_program_courses(
    program: Annotated[
        str,
        Field(
            description='Programme or department: name ("Bachelor Informatik", "SPL 18 Philosophie") '
            'or a VVZ path ("341848").'
        ),
    ],
    semester: Semester = None,
    module: Annotated[
        str | None,
        Field(default=None, description='Only courses whose module trail contains this text, e.g. "StEOP".'),
    ] = None,
    limit: Annotated[
        int, Field(default=400, ge=1, le=2000, description="Maximum course entries to print.")
    ] = 400,
    with_details: Annotated[
        bool,
        Field(default=True, description="Include groups, lecturers and weekly times inline."),
    ] = True,
    group_by_module: Annotated[
        bool, Field(default=True, description="Print module headings.")
    ] = True,
) -> str:
    """The complete course list a department or degree programme offers in one semester,
    grouped by curriculum module, in one request. Use this for "what does
    department/programme X offer in semester Y"."""
    code = resolve_semester(semester)
    resolution = await resolve_node(code, program)

    if resolution.kind == "notfound":
        return (
            f'Nothing in the {semester_label(code)} catalogue matched "{program}". '
            "Try list_departments or list_programs to see the exact names."
        )
    if resolution.kind == "ambiguous":
        if resolution.weak:
            lead = (
                f'No programme in {semester_label(code)} clearly matches "{program}". Closest names '
                "(check whether any is what you meant, or use list_departments / list_programs):"
            )
        else:
            lead = (
                f'"{program}" matches several entries in {semester_label(code)}. Pick one and call '
                "again with its name or path:"
            )
        lines = [
            f"- {c.name}, path `{c.path}`" + (f" ({c.department})" if c.department else "")
            for c in resolution.candidates
        ]
        return "\n".join([lead, "", *lines])

    assert resolution.node is not None
    listing = await get_node_courses(
        resolution.node.path, details=with_details, expected_semester=code
    )
    text = fmt.render_listing(
        listing, limit=limit, module_filter=module, group_by_module=group_by_module
    )
    if resolution.alternatives:
        others = ", ".join(f"{a.name} (`{a.path}`)" for a in resolution.alternatives[:4])
        text += f"\n\n_Other close matches: {others}._"
    return text


@mcp.tool(annotations=READ_ONLY)
async def get_program_modules(
    program: Annotated[str, Field(description="Programme/department name or VVZ path.")],
    semester: Semester = None,
) -> str:
    """Module tree of a programme or department without any courses, a cheap overview of
    how a curriculum is structured."""
    code = resolve_semester(semester)
    resolution = await resolve_node(code, program)
    if resolution.kind == "notfound":
        return f'Nothing matched "{program}" in {semester_label(code)}.'
    if resolution.kind == "ambiguous":
        lines = [f"- {c.name}, `{c.path}`" for c in resolution.candidates]
        return "\n".join([f'"{program}" is ambiguous:', "", *lines])

    assert resolution.node is not None
    title, modules = await get_node_modules(resolution.node.path)
    if not modules:
        return (
            f"{title} ({semester_label(code)}) has no module headings. "
            "call get_program_courses for its course list."
        )
    lines = [
        f"{'  ' * max(0, level - 1)}- {name}" + (f", path `{path}`" if path else "")
        for name, path, level in modules
    ]
    return "\n".join(
        [
            f"# {title}, {semester_label(code)}",
            "",
            f"{len(modules)} module headings:",
            "",
            *lines,
            "",
            "_Call get_program_courses with any of these paths (or the `module` filter) to see the courses._",
        ]
    )


@mcp.tool(annotations=READ_ONLY)
async def search_staff(
    query: Annotated[str, Field(description="Name or part of a name.")],
    limit: Annotated[int, Field(default=10, ge=1, le=60, description="Maximum people.")] = 10,
) -> str:
    """Find university staff by name; returns ids, unit, email and room where published."""
    return fmt.render_staff_search(await api.search_staff(query, limit), query)


@mcp.tool(annotations=READ_ONLY)
async def get_staff(
    id: Annotated[str, Field(description='Person id from search_staff, e.g. "36131".')],
) -> str:
    """Contact details, room and affiliations of one person."""
    return fmt.render_person(await api.get_staff(id.strip()))


@mcp.tool(annotations=READ_ONLY)
async def search_units(
    query: Annotated[str, Field(description='e.g. "Philosophie", "Translationswissenschaft".')],
    limit: Annotated[int, Field(default=10, ge=1, le=60, description="Maximum units.")] = 10,
) -> str:
    """Find institutes, departments and faculties (addresses, website, hierarchy)."""
    return fmt.render_unit_search(await api.search_units(query, limit), query)


@mcp.tool(annotations=READ_ONLY)
async def get_unit(
    id: Annotated[str, Field(description='Unit id from search_units, e.g. "464".')],
) -> str:
    """One institute/department: name, website, locations and place in the university hierarchy."""
    return fmt.render_unit(await api.get_unit(id.strip()))


@mcp.tool(annotations=READ_ONLY)
async def search_exams(
    query: Annotated[str, Field(description="Keywords, LV number or lecturer name.")],
    semester: Annotated[
        str | None,
        Field(default=None, description=SEMESTER_DESC + ' Pass "" for all semesters.'),
    ] = None,
    limit: Annotated[int, Field(default=10, ge=1, le=60, description="Maximum courses.")] = 10,
) -> str:
    """Courses with matching exam records (Prüfungstermine). Returns the courses; call
    get_course for the concrete exam dates."""
    code = None if semester == "" else resolve_semester(semester)
    full_query = f"{query} {code}" if code else query
    return fmt.render_course_search(await api.search_exams(full_query, limit), full_query)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
async def list_semesters() -> str:
    """Which semester codes to use, and which one counts as 'current'. Past semesters are
    archived; a semester more than one term ahead is usually still empty."""
    lines = [f"- `{code}`: {semester_label(code)}" for code in semester_range(6, 1)]
    return "\n".join(
        [
            f"Current semester: **{semester_label(current_semester())}**",
            "",
            "Usable codes (most recent last):",
            *lines,
            "",
            "Winter runs October to February, summer March to September. Every tool accepts an exact "
            "code, `current`, `next` or `previous`.",
            f"Cache directory: {cache_location()}",
        ]
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
