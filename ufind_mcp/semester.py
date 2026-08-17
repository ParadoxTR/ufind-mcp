from __future__ import annotations

import re
from datetime import date

_CODE = re.compile(r"^(\d{4})([WS])$", re.IGNORECASE)
_SHORT = re.compile(r"^(\d{2})([WS])$", re.IGNORECASE)


def is_semester_code(value: str) -> bool:
    return bool(_CODE.match(value.strip()))


def current_semester(today: date | None = None) -> str:
    today = today or date.today()
    if today.month <= 2:
        return f"{today.year - 1}W"
    if today.month <= 7:
        return f"{today.year}S"
    return f"{today.year}W"


def _split(code: str) -> tuple[int, str]:
    match = _CODE.match(code.strip())
    if not match:
        raise ValueError(f"invalid semester code: {code}")
    return int(match.group(1)), match.group(2).upper()


def next_semester(code: str) -> str:
    year, half = _split(code)
    return f"{year}W" if half == "S" else f"{year + 1}S"


def previous_semester(code: str) -> str:
    year, half = _split(code)
    return f"{year}S" if half == "W" else f"{year - 1}W"


def resolve_semester(value: str | None) -> str:
    raw = (value or "current").strip()
    if re.match(r"^(current|now|aktuell|jetzt)$", raw, re.IGNORECASE):
        return current_semester()
    if re.match(r"^(next|n(ä|ae)chste|kommend)", raw, re.IGNORECASE):
        return next_semester(current_semester())
    if re.match(r"^(prev|previous|last|vorig|letzte)", raw, re.IGNORECASE):
        return previous_semester(current_semester())
    short = _SHORT.match(raw)
    if short:
        return f"20{short.group(1)}{short.group(2).upper()}"
    match = _CODE.match(raw)
    if not match:
        raise ValueError(
            f'Unrecognised semester "{value}". Use e.g. "2026W", "2027S", '
            'or "current" / "next" / "previous".'
        )
    return f"{match.group(1)}{match.group(2).upper()}"


def semester_label(code: str) -> str:
    match = _CODE.match(code or "")
    if not match:
        return code
    year = int(match.group(1))
    if match.group(2).upper() == "W":
        return f"Wintersemester {year}/{(year + 1) % 100:02d} ({code})"
    return f"Sommersemester {year} ({code})"


def semester_range(back: int = 6, forward: int = 1) -> list[str]:
    code = current_semester()
    for _ in range(back):
        code = previous_semester(code)
    out: list[str] = []
    for _ in range(back + forward + 1):
        out.append(code)
        code = next_semester(code)
    return out
