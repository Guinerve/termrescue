"""Recognise input a terminal sends when it is still in a reporting mode.

Mouse reports come in three encodings, depending on which mode the program
that died had enabled:

* SGR (mode 1006):   ESC [ < button ; column ; row M   (m on release)
* urxvt (mode 1015): ESC [ button+32 ; column ; row M
* X10 (mode 1000):   ESC [ M then three bytes, each value + 32

Focus reporting (mode 1004) sends ESC [ I on focus in and ESC [ O on focus out.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_REPORT = re.compile(
    r"\x1b\[<(?P<sgr_b>\d+);(?P<sgr_x>\d+);(?P<sgr_y>\d+)(?P<sgr_end>[Mm])"
    r"|\x1b\[(?P<urxvt_b>\d+);(?P<urxvt_x>\d+);(?P<urxvt_y>\d+)M"
    r"|\x1b\[M(?P<x10>[\x20-\U0010ffff]{3})"
    r"|\x1b\[(?P<focus>[IO])"
)


@dataclass(frozen=True)
class Report:
    kind: str  # "mouse" or "focus"
    encoding: str  # "sgr", "urxvt", "x10" for mouse; "in"/"out" for focus
    raw: str
    button: int | None = None
    column: int | None = None
    row: int | None = None
    released: bool = False


def _to_report(m: re.Match[str]) -> Report:
    raw = m.group(0)
    if m["sgr_b"] is not None:
        return Report("mouse", "sgr", raw, int(m["sgr_b"]), int(m["sgr_x"]),
                      int(m["sgr_y"]), released=m["sgr_end"] == "m")
    if m["urxvt_b"] is not None:
        return Report("mouse", "urxvt", raw, int(m["urxvt_b"]) - 32,
                      int(m["urxvt_x"]), int(m["urxvt_y"]))
    if m["x10"] is not None:
        b, x, y = (ord(ch) - 32 for ch in m["x10"])
        return Report("mouse", "x10", raw, b, x, y)
    return Report("focus", "in" if m["focus"] == "I" else "out", raw)


def find_reports(text: str) -> list[Report]:
    """Every mouse or focus report in ``text``, in order."""
    return [_to_report(m) for m in _REPORT.finditer(text)]


def strip_reports(text: str) -> str:
    """``text`` with mouse and focus reports removed and everything else kept."""
    return _REPORT.sub("", text)
