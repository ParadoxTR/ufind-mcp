from __future__ import annotations

import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


async def main() -> int:
    params = StdioServerParameters(command=sys.executable, args=["-m", "ufind_mcp"], cwd=ROOT)
    unexpected = 0
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listing = await session.list_tools()
            print(f"{len(listing.tools)} tools: {', '.join(t.name for t in listing.tools)}\n")

            calls = [
                ("list_semesters", {}),
                (
                    "get_program_courses",
                    {"program": "Bachelor Informatik", "semester": "2026W", "module": "StEOP", "limit": 20},
                ),
                ("get_course", {"lv": "051010", "semester": "2026W", "include_description": False}),
                ("search_courses", {"query": "sprachphilosophie", "semester": "2026W", "limit": 3}),
                ("list_departments", {"semester": "2026W"}),
                ("get_course_schedule", {"lv": "180013", "semester": "2026W", "group": "1"}),
                ("search_staff", {"query": "Schnieder", "limit": 2}),
                ("get_program_modules", {"program": "Master Philosophie", "semester": "2026W"}),
                ("get_course", {"lv": "999999", "semester": "2026W"}),
                ("get_program_courses", {"program": "Voynich Studies", "semester": "2026W"}),
            ]

            for name, args in calls:
                result = await session.call_tool(name, args)
                text = "\n".join(c.text for c in result.content if getattr(c, "text", None))
                flag = "  [ERROR]" if result.is_error else ""
                head = "\n".join(text.splitlines()[:6])
                print(f">> {name} {args}{flag}\n{head}\n… ({len(text)} chars)\n")
                if result.is_error and "999999" not in text and "HTTP 404" not in text:
                    unexpected += 1

    print("protocol smoke: OK" if unexpected == 0 else f"protocol smoke: {unexpected} unexpected error(s)")
    return 0 if unexpected == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
