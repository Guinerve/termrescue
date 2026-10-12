import shutil
import sys
import time

import pytest
from ptyshell import start_zsh

from termrescue.sequences import PROMPT_RESET

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("zsh") is None,
    reason="needs a Unix pseudo-terminal and zsh")

# A program that turns on mouse reporting and then dies without turning it off,
# the way a remote tmux/vim does when the SSH link drops.
DIES_IN_MOUSE_MODE = "sh -c 'printf \"\\033[?1003h\\033[?1006h\"; kill -9 $$'\r"


@pytest.fixture
def zsh(tmp_path):
    shell = start_zsh(tmp_path)
    yield shell
    shell.close()


def test_prompt_after_a_dead_program_switches_mouse_reporting_off(zsh):
    pos = zsh.wait_for_prompt()
    zsh.send(DIES_IN_MOUSE_MODE)
    out = zsh.read_until("\x1b[?1006h", start=pos)
    enabled_at = out.index("\x1b[?1006h", pos)
    zsh.wait_for_prompt(after=enabled_at)
    assert PROMPT_RESET in zsh.output[enabled_at:]


def test_mouse_reports_queued_while_a_command_ran_are_dropped_but_typing_is_kept(zsh, tmp_path):
    pos = zsh.wait_for_prompt()
    zsh.send("sleep 1\r")
    time.sleep(0.3)
    # Mouse movement and a focus event arrive while `sleep` runs, then the user types.
    zsh.send("\x1b[<35;45;23M\x1b[<35;46;23M\x1b[O" + "echo kept\r")
    out = zsh.read_until("\r\nkept\r\n", start=pos, timeout=8)
    assert "kept" in out
    assert (tmp_path / "last-command").read_text() == "echo kept"


def test_existing_line_init_widgets_still_run(tmp_path):
    rc = (
        "autoload -Uz add-zle-hook-widget\n"
        "mine() { print -rn -- ran > $HOME/mine-ran }\n"
        "add-zle-hook-widget line-init mine\n"
    )
    shell = start_zsh(tmp_path, rc_extra=rc)
    try:
        shell.wait_for_prompt()
        deadline = time.monotonic() + 5
        while not (tmp_path / "mine-ran").exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert (tmp_path / "mine-ran").read_text() == "ran"
    finally:
        shell.close()
