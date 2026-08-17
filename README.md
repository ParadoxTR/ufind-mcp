# ufind-mcp

An MCP server for [u:find](https://ufind.univie.ac.at), the course catalogue of the University of Vienna. Ask your assistant what a department offers this semester, when a course meets, who teaches it, or where a room is. Read only, no account, no API key.

## Install

```bash
git clone https://github.com/ParadoxTR/ufind-mcp.git
cd ufind-mcp
uv sync
```

Add it to Claude Code:

```bash
claude mcp add ufind --scope user -- uv --directory /absolute/path/to/ufind-mcp run ufind-mcp
```

Or add it to Claude Desktop, Cursor or any other MCP client:

```json
{
  "mcpServers": {
    "ufind": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/ufind-mcp", "run", "ufind-mcp"]
    }
  }
}
```

## What you can ask

> Which courses does the Bachelor Informatik programme offer in 2026W?

> When and where does 180013 meet, and who teaches it?

> Find logic courses next semester with fewer than 3 ECTS.

> What is Benjamin Schnieder teaching this winter?

> Give me the module structure of the Master Philosophie curriculum.

## Tools

| Tool | What it does |
| --- | --- |
| `search_courses` | Free text course search across titles, LV numbers, lecturers and semesters |
| `get_course` | One course in full: groups, lecturers, every date and room, curriculum placement, description, registration window, exams |
| `get_course_schedule` | Weekly pattern and all dates of a group, or the raw iCal feed |
| `list_departments` | Every top level unit of the Vorlesungsverzeichnis for a semester |
| `list_programs` | Bachelor, Master, Doktorat and extension curricula, filterable by department or name |
| `get_program_courses` | Every course a department or programme offers in a semester, grouped by module |
| `get_program_modules` | Curriculum structure without the courses |
| `search_staff`, `get_staff` | Staff lookup with room, email and affiliations |
| `search_units`, `get_unit` | Institutes, departments and faculties |
| `search_exams` | Courses that have exam records |
| `list_semesters` | Which semester codes exist and which one is current |

Semesters are written `2026W` (winter 2026/27) or `2027S`. Every tool also accepts `current`, `next` and `previous`.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `UFIND_MCP_LANG` | `de` | Set to `en` for English pages and titles |
| `UFIND_MCP_CACHE_DIR` | `~/.cache/ufind-mcp` | Where responses are cached |
| `UFIND_MCP_NO_CACHE` | unset | Set to `1` to disable the cache |
| `UFIND_MCP_TIMEOUT_S` | `60` | Request timeout, the staff search page can be slow |
| `UFIND_MCP_MIN_GAP_S` | `0.25` | Minimum pause between requests |
| `UFIND_MCP_USER_AGENT` | `ufind-mcp/0.1 ...` | User agent sent to u:find |

## Good to know

u:find has no public API. This server reads the XML endpoints that the mobile clients use and, for the parts those endpoints do not cover, the public web pages. That means the university can change things without notice. Requests go out one at a time with a small pause, and every response is cached on disk, so normal use stays light on their servers.

A semester that has not started yet is incomplete. Course descriptions, registration windows and exam dates often stay empty until the term begins.

Catalogue paths are specific to one semester, so a programme has a different id in 2026W than in 2026S. The server resolves programmes by name for the semester you ask about and warns you if a path belongs to a different term.

A course that counts towards several modules appears once per module in a programme listing. Output always states how many entries and how many distinct courses that is.

## Tests

```bash
uv run python tests/smoke.py      # live data, parsing and completeness
uv run python tests/mcp_smoke.py  # calls every tool over the MCP protocol
```

## Disclaimer

This project is not affiliated with, endorsed by or supported by the University of Vienna. It reads endpoints that are not part of a documented public API, so it can break at any time. Use it for your own studies and keep the default rate limiting in place. If you need guaranteed access, ask the university.

## License

MIT
