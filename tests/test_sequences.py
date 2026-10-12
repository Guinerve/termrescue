from termrescue.sequences import FULL_RESET, MOUSE_MODES, PROMPT_RESET, describe


def test_prompt_reset_disables_every_mouse_mode_and_focus_reporting():
    for mode in [*MOUSE_MODES, 1004]:
        assert f"\x1b[?{mode}l" in PROMPT_RESET


def test_prompt_reset_shows_the_cursor():
    assert "\x1b[?25h" in PROMPT_RESET


def test_prompt_reset_leaves_the_alternate_screen_and_bracketed_paste_alone():
    # Leaving the alt screen at every prompt would move the cursor to an old
    # saved position; the shell's line editor manages bracketed paste itself.
    assert "1049" not in PROMPT_RESET
    assert "2004" not in PROMPT_RESET


def test_full_reset_also_clears_alt_screen_paste_keypad_and_keyboard_protocol():
    assert FULL_RESET.startswith(PROMPT_RESET)
    for seq in ["\x1b[?2004l", "\x1b[?1049l", "\x1b[?1l", "\x1b>", "\x1b[<99u"]:
        assert seq in FULL_RESET


def test_describe_shows_escape_as_caret_notation():
    assert describe("\x1b[?1000l") == "^[[?1000l"
