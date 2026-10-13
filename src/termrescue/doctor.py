"""Ask the terminal which modes are on, using DECRQM.

For each mode we send ESC [ ? mode $ p and the terminal replies
ESC [ ? mode ; state $ y. We finish with a primary device-attributes query
(ESC [ c), which every terminal answers, so we know when the replies are done.
Terminals that don't support DECRQM answer only the device-attributes query.
"""

from __future__ import annotations

import re

from . import terminal
from .sequences import ALL_MODES, MOUSE_MODES

_MODE_REPLY = re.compile(r"\x1b\[\?(\d+);(\d)\$y")
_DEVICE_ATTRIBUTES = re.compile(r"\x1b\[\?[\d;]*c")

_STATES = {0: "unsupported", 1: "on", 2: "off", 3: "on (permanent)", 4: "off (permanent)"}

# Modes that should never be on at a shell prompt.
STUCK_IF_ON = set(MOUSE_MODES) | {1004}


def parse_mode_reports(text: str) -> dict[int, str]:
    return {int(m[1]): _STATES.get(int(m[2]), "unknown") for m in _MODE_REPLY.finditer(text)}


def query_modes(timeout: float) -> dict[int, str] | None:
    """Mode states from the terminal, or None if it didn't answer at all."""
    queries = "".join(f"\x1b[?{mode}$p" for mode in ALL_MODES) + "\x1b[c"
    with terminal.open_terminal() as term, term.raw():
        term.write(queries)
        replies = terminal.read_until(
            term, lambda t: _DEVICE_ATTRIBUTES.search(t) is not None, timeout)
    if not _DEVICE_ATTRIBUTES.search(replies):
        return None
    return parse_mode_reports(replies)


def run(timeout: float) -> int:
    with terminal.open_terminal() as term:
        input_report, input_stuck = term.input_mode_report(), term.input_mode_stuck()
    if input_report:
        print(input_report)
    code = _report_terminal_modes(timeout)
    return 1 if input_stuck else code


def _report_terminal_modes(timeout: float) -> int:
    states = query_modes(timeout)
    if states is None:
        print(f"The terminal did not answer within {timeout:g} s, so termrescue cannot tell "
              "which modes are on.\nIf the input looks wrong, run `termrescue fix`.")
        return 2
    if not states:
        print("This terminal does not answer mode queries (DECRQM), so the state is unknown.\n"
              "If the input looks wrong, run `termrescue fix`.")
        return 2

    for mode, name in ALL_MODES.items():
        state = states.get(mode, "unknown")
        shown = state.upper() if mode in STUCK_IF_ON and state.startswith("on") else state
        print(f"{mode:>5}  {name:<26}{shown}")

    stuck = [m for m in STUCK_IF_ON if states.get(m) == "on"]
    if stuck:
        print(f"\nStuck at the prompt: {', '.join(ALL_MODES[m] for m in sorted(stuck))}. "
              "Run `termrescue fix`.")
        return 1
    print("\nNothing stuck.")
    return 0
