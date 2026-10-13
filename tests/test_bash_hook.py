import shutil
import sys

import pytest
from ptyshell import start_bash

from termrescue.sequences import PROMPT_RESET

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None,
    reason="needs a Unix pseudo-terminal and bash")

DIES_IN_MOUSE_MODE = "sh -c 'printf \"\\033[?1003h\\033[?1006h\"; kill -9 $$'\r"


def test_prompt_after_a_dead_program_switches_mouse_reporting_off(tmp_path):
    shell = start_bash(tmp_path)
    try:
        pos = shell.wait_for_prompt()
        shell.send(DIES_IN_MOUSE_MODE)
        out = shell.read_until("\x1b[?1006h", start=pos)
        enabled_at = out.index("\x1b[?1006h", pos)
        shell.wait_for_prompt(after=enabled_at)
        assert PROMPT_RESET in shell.output[enabled_at:]
    finally:
        shell.close()


def test_existing_prompt_command_still_runs(tmp_path):
    shell = start_bash(tmp_path, rc_extra="PROMPT_COMMAND='echo mine >> $HOME/mine-ran'")
    try:
        pos = shell.wait_for_prompt()
        shell.send("true\r")
        shell.wait_for_prompt(after=pos)
        assert (tmp_path / "mine-ran").read_text().count("mine") >= 2
        assert PROMPT_RESET in shell.output
    finally:
        shell.close()


def test_existing_prompt_command_still_sees_the_last_exit_status(tmp_path):
    # Prompt themes (starship, liquidprompt, powerline) colour the prompt from $?.
    shell = start_bash(tmp_path, rc_extra="PROMPT_COMMAND='echo \"status=$?\" >> $HOME/status'")
    try:
        pos = shell.wait_for_prompt()
        shell.send("false\r")
        shell.wait_for_prompt(after=pos)
        assert "status=1" in (tmp_path / "status").read_text()
    finally:
        shell.close()


def test_hook_loads_when_the_rc_file_uses_set_u(tmp_path):
    # With `set -u`, reading an unset PROMPT_COMMAND is an error that stops `source`.
    shell = start_bash(tmp_path, rc_extra="set -u")
    try:
        pos = shell.wait_for_prompt()
        shell.send("true\r")
        shell.wait_for_prompt(after=pos)
        assert PROMPT_RESET in shell.output
        assert "unbound variable" not in shell.output
    finally:
        shell.close()


def test_sourcing_the_hook_twice_adds_it_to_prompt_command_once(tmp_path):
    # ~/.bash_profile often sources ~/.bashrc, so both files may load the hook.
    from ptyshell import SHELL_DIR

    shell = start_bash(tmp_path, rc_extra=f"source {SHELL_DIR / 'termrescue.bash'}")
    try:
        pos = shell.wait_for_prompt()
        shell.send("echo \"pc=$PROMPT_COMMAND\" > $HOME/pc\r")
        shell.wait_for_prompt(after=pos)
        assert (tmp_path / "pc").read_text() == "pc=_termrescue_reset\n"
    finally:
        shell.close()
