from termrescue.reports import find_reports, strip_reports

SGR_PRESS = "\x1b[<0;45;23M"
SGR_MOVE = "\x1b[<35;46;23M"
SGR_RELEASE = "\x1b[<0;45;23m"
URXVT = "\x1b[32;45;23M"
X10 = "\x1b[M" + chr(32) + chr(32 + 45) + chr(32 + 23)
FOCUS_IN = "\x1b[I"
FOCUS_OUT = "\x1b[O"


def test_strip_removes_sgr_mouse_reports():
    assert strip_reports(f"ls{SGR_PRESS}{SGR_MOVE}{SGR_RELEASE} -la") == "ls -la"


def test_strip_removes_urxvt_and_x10_mouse_reports():
    assert strip_reports(f"a{URXVT}b{X10}c") == "abc"


def test_strip_removes_focus_events():
    assert strip_reports(f"{FOCUS_OUT}git status{FOCUS_IN}") == "git status"


def test_strip_keeps_ordinary_keys_and_escape_sequences():
    arrows = "\x1b[A\x1b[B\x1b[1;5C"  # up, down, ctrl-right
    paste = "\x1b[200~hello\x1b[201~"
    text = f"echo 1;2;3M {arrows}{paste}"
    assert strip_reports(text) == text


def test_find_reports_decodes_sgr_mouse_coordinates():
    (report,) = find_reports(SGR_MOVE)
    assert report.kind == "mouse"
    assert report.encoding == "sgr"
    assert (report.button, report.column, report.row) == (35, 46, 23)
    assert report.raw == SGR_MOVE


def test_find_reports_decodes_x10_mouse_coordinates():
    (report,) = find_reports(X10)
    assert report.encoding == "x10"
    assert (report.button, report.column, report.row) == (0, 45, 23)


def test_find_reports_labels_focus_events():
    kinds = [(r.kind, r.encoding) for r in find_reports(FOCUS_IN + FOCUS_OUT)]
    assert kinds == [("focus", "in"), ("focus", "out")]
