"""Escape sequences that switch terminal modes back off.

DEC private modes are enabled with ESC [ ? n h and disabled with ESC [ ? n l.
"""

MOUSE_MODES = {
    9: "X10 mouse",
    1000: "mouse clicks",
    1001: "mouse highlight",
    1002: "mouse drag",
    1003: "mouse motion",
    1005: "UTF-8 mouse encoding",
    1006: "SGR mouse encoding",
    1015: "urxvt mouse encoding",
    1016: "SGR pixel mouse encoding",
}

OTHER_MODES = {
    1004: "focus reporting",
    25: "cursor visible",
    2004: "bracketed paste",
    1049: "alternate screen",
    1: "application cursor keys",
}

ALL_MODES = {**MOUSE_MODES, **OTHER_MODES}


def _off(mode: int) -> str:
    return f"\x1b[?{mode}l"


# Safe to send at every prompt: no program is running, so nothing should be
# reporting mouse or focus events, and the cursor should be visible.
PROMPT_RESET = "".join(_off(m) for m in MOUSE_MODES) + _off(1004) + "\x1b[?25h"

# For `termrescue fix`, run by hand when the terminal is visibly broken.
FULL_RESET = (
    PROMPT_RESET
    + _off(2004)  # bracketed paste (the line editor re-enables it if wanted)
    + _off(1049)  # leave the alternate screen
    + _off(1)  # normal cursor keys
    + "\x1b>"  # normal keypad
    + "\x1b[<99u"  # pop the kitty keyboard-protocol stack
    + "\x1b[>4;0m"  # xterm modifyOtherKeys off
)


def describe(seq: str) -> str:
    """Show ``seq`` the way `cat -v` would, with ESC as ^[."""
    return seq.replace("\x1b", "^[")
