from __future__ import annotations

import asyncio
import os
import sys
from typing import Awaitable, Callable

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ufind_mcp import api, http
from ufind_mcp.coursepage import get_course_info
from ufind_mcp.format import render_course, render_course_search, render_listing
from ufind_mcp.semester import current_semester, resolve_semester
from ufind_mcp.vvz import get_index, get_node_courses, get_node_modules, resolve_node

SEM = os.environ.get("SMOKE_SEMESTER", "2026W")
failures = 0


async def check(name: str, fn: Callable[[], Awaitable[str]]) -> None:
    global failures
    try:
        note = await fn()
    except Exception as err:
        failures += 1
        print(f"❌ {name} | {type(err).__name__}: {err}")
    else:
        print(f"✅ {name}" + (f" | {note}" if note else ""))


async def semesters() -> str:
    assert resolve_semester("2026w") == "2026W"
    assert resolve_semester("26S") == "2026S"
    try:
        resolve_semester("someday")
    except ValueError:
        pass
    else:
        raise AssertionError("bad semester code accepted")
    return f"current = {current_semester()}"


async def course_search() -> str:
    result = await api.search_courses(f"logik {SEM}", 5)
    assert result.total > 0, "no hits"
    assert len(result.items) == 5, f"{len(result.items)} items"
    first = result.items[0]
    assert first.lv and first.title and first.type, "course fields missing"
    assert first.lv in render_course_search(result, "logik")
    return f"{result.total} hits, first: {first.lv} {first.title}"


async def course_detail() -> str:
    course = await api.get_course("180013", SEM)
    assert course.lv == "180013" and course.semester == SEM
    assert course.groups, "no groups"
    group = course.groups[0]
    assert group.events, "no events"
    assert group.lecturers, "no lecturers"
    assert course.modules, "no curriculum mapping"
    info = await get_course_info("180013", SEM)
    markdown = render_course(course, info)
    assert "Group 1" in markdown and "Where it counts" in markdown
    return f"{course.title}, {len(group.events)} dates, {len(group.lecturers)} teachers"


async def archived_description() -> str:
    info = await get_course_info("180013", "2025W")
    assert info.aims and len(info.aims) > 100, "no description text"
    return info.aims[:40].replace("\n", " ") + "…"


async def vvz_index() -> str:
    index = await get_index(SEM)
    assert len(index.departments) > 40, f"only {len(index.departments)} departments"
    assert len(index.programmes) > 300, f"only {len(index.programmes)} programmes"
    assert all(p.department for p in index.programmes), "programme without department"
    return f"{len(index.departments)} departments, {len(index.programmes)} programmes"


async def resolve_by_name() -> str:
    resolution = await resolve_node(SEM, "Bachelor Informatik")
    assert resolution.kind == "resolved", resolution.kind
    assert resolution.node is not None and "Bachelor Informatik" in resolution.node.name
    return f"{resolution.node.name} → path {resolution.node.path}"


async def programme_courses() -> str:
    resolution = await resolve_node(SEM, "Bachelor Informatik")
    assert resolution.node is not None
    listing = await get_node_courses(resolution.node.path, details=True, expected_semester=SEM)
    assert len(listing.courses) > 50, f"only {len(listing.courses)} courses"
    assert listing.semester_mismatch is None
    with_times = [c for c in listing.courses if any(g.times for g in c.groups)]
    with_module = [c for c in listing.courses if c.module_trail]
    assert len(with_times) > 20, "details missing (times)"
    assert len(with_module) > 40, "module trail missing"
    markdown = render_listing(listing, limit=500)
    assert "051010" in markdown, "known course missing from output"

    child_path = next(p for p, _ in listing.child_paths)
    child = await get_node_courses(child_path, details=False)
    parent_lvs = {c.lv for c in listing.courses}
    extra = [c.lv for c in child.courses if c.lv not in parent_lvs]
    assert not extra, f"child {child_path} adds {len(extra)} courses"
    return f"{len(listing.courses)} rows, {len(with_times)} with times, child adds 0"


async def department_courses() -> str:
    resolution = await resolve_node(SEM, "Studienprogrammleitung 5")
    assert resolution.node is not None
    listing = await get_node_courses(resolution.node.path, details=True, expected_semester=SEM)
    assert len(listing.courses) > 100, f"only {len(listing.courses)} courses"
    return f"{resolution.node.name}: {len(listing.courses)} rows"


async def semester_mismatch() -> str:
    listing = await get_node_courses("341848", details=False, expected_semester="2026S")
    assert listing.semester_mismatch, "mismatch not reported"
    return listing.semester_mismatch[:60] + "…"


async def module_tree() -> str:
    resolution = await resolve_node(SEM, "Bachelor Informatik")
    assert resolution.node is not None
    title, modules = await get_node_modules(resolution.node.path)
    assert len(modules) >= 2, "no modules"
    return f"{title}: {len(modules)} module headings"


async def staff() -> str:
    result = await api.search_staff("Schmid", 3)
    assert result.total > 0 and len(result.items) == 3
    person = await api.get_staff(result.items[0].id)
    assert len(person.name) > 3
    assert "/9j/4" not in repr(person), "base64 photo leaked into output"
    return f"{result.total} hits, detail: {person.name}"


async def units() -> str:
    result = await api.search_units("Philosophie", 3)
    assert result.items
    unit = await api.get_unit("464")
    assert "Philosophie" in unit.name, unit.name
    return f"{result.total} hits, unit 464 = {unit.name}"


async def exams() -> str:
    result = await api.search_exams("logik", 3)
    assert result.items
    return f"{result.total} exam records"


async def main() -> int:
    await check("semester helpers", semesters)
    await check("search_courses", course_search)
    await check("get_course + description", course_detail)
    await check("archived semester has descriptions", archived_description)
    await check("vvz index", vvz_index)
    await check("resolve programme by name", resolve_by_name)
    await check("programme course list is complete", programme_courses)
    await check("department course list", department_courses)
    await check("semester mismatch is detected", semester_mismatch)
    await check("module tree", module_tree)
    await check("staff", staff)
    await check("units", units)
    await check("exams", exams)
    await http.aclose()
    print("\nAll checks passed." if failures == 0 else f"\n{failures} check(s) failed.")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
