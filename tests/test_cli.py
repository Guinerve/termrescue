import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest
from ptyshell import SHELL_DIR, PtyShell, base_env

from termrescue.cli import main
from termrescue.doctor import parse_mode_reports
from termrescue.sequences import FULL_RESET, PROMPT_RESET, describe

CLI = [sys.executable, "-m", "termrescue"]
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="needs a Unix pseudo-terminal")
DIES_IN_MOUSE_MODE = ["sh", "-c", 'printf "\\033[?1049h\\033[?1003h"; kill -9 $$']


def run_in_pty(args, tmp_path):
    env = base_env(tmp_path) | {"PYTHONPATH": str(Path(__file__).parent.parent / "src")}
    return PtyShell([*CLI, *args], env, tmp_path)


# --- shell hooks stay in sync with sequences.py ------------------------------

def test_zsh_hook_sends_exactly_the_prompt_reset():
    text = (SHELL_DIR / "termrescue.zsh").read_text()
    literal = re.search(r"_termrescue_reset=\$'([^']*)'", text).group(1)
    assert literal.replace("\\e", "\x1b") == PROMPT_RESET


def test_bash_hook_sends_exactly_the_prompt_reset():
    text = (SHELL_DIR / "termrescue.bash").read_text()
    literal = re.search(r"printf '([^']*)'", text).group(1)
    assert literal.replace("\\033", "\x1b") == PROMPT_RESET


# --- init ---------------------------------------------------------------------

@pytest.mark.parametrize("shell", ["zsh", "bash"])
def test_init_prints_the_hook_for_that_shell(shell, capsys):
    assert main(["init", shell]) == 0
    assert capsys.readouterr().out == (SHELL_DIR / f"termrescue.{shell}").read_text()


# --- fix ----------------------------------------------------------------------

def test_fix_print_shows_the_sequence_without_sending_it(capsys):
    assert main(["fix", "--print"]) == 0
    out = capsys.readouterr().out
    assert describe(FULL_RESET) in out
    assert "\x1b" not in out


@posix_only
def test_fix_sends_the_full_reset_to_the_terminal(tmp_path):
    proc = run_in_pty(["fix"], tmp_path)
    try:
        proc.read_until(FULL_RESET)
    finally:
        proc.close()


# --- run ----------------------------------------------------------------------

@posix_only
def test_run_resets_the_terminal_after_the_command_dies(tmp_path):
    proc = run_in_pty(["run", "--", *DIES_IN_MOUSE_MODE], tmp_path)
    try:
        out = proc.read_until(FULL_RESET)
        assert out.index("\x1b[?1003h") < out.index(FULL_RESET)
    finally:
        proc.close()


def test_run_passes_through_the_command_exit_status():
    result = subprocess.run([*CLI, "run", "--", sys.executable, "-c", "raise SystemExit(7)"],
                            capture_output=True, check=False,
                            env=os.environ | {"PYTHONPATH": str(Path(__file__).parent.parent / "src")})
    assert result.returncode == 7


# --- capture ------------------------------------------------------------------

@posix_only
def test_capture_decodes_what_the_terminal_sends_until_q(tmp_path):
    proc = run_in_pty(["capture", "--seconds", "5"], tmp_path)
    try:
        proc.read_until("Press q")
        proc.send("\x1b[<35;45;23M" + "x" + "q")
        out = proc.read_until("'x'")
        assert "Raw: ^[[<35;45;23Mx" in out
        assert re.search(r"mouse.*sgr.*button 35.*column 45.*row 23", proc.output)
    finally:
        proc.close()


# --- doctor -------------------------------------------------------------------

def test_parse_mode_reports_reads_decrqm_replies():
    replies = "\x1b[?1000;1$y\x1b[?1006;2$y\x1b[?1015;0$y\x1b[?62;22c"
    assert parse_mode_reports(replies) == {1000: "on", 1006: "off", 1015: "unsupported"}


@posix_only
def test_doctor_reports_stuck_modes_and_exits_nonzero(tmp_path):
    proc = run_in_pty(["doctor"], tmp_path)
    try:
        # Play the terminal: answer each mode query, then the device-attributes query.
        out = proc.read_until("\x1b[c")
        for mode in map(int, re.findall(r"\x1b\[\?(\d+)\$p", out)):
            state = 1 if mode in {1003, 1006} else 2
            proc.send(f"\x1b[?{mode};{state}$y")
        proc.send("\x1b[?62;22c")
        report = proc.read_until("termrescue fix")
        assert re.search(r"1003\s+mouse motion\s+ON", report)
        assert re.search(r"1006\s+SGR mouse encoding\s+ON", report)
        assert re.search(r"1000\s+mouse clicks\s+off", report)
        deadline = time.monotonic() + 5
        while proc.proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert proc.proc.returncode == 1
    finally:
        proc.close()


@posix_only
def test_doctor_says_unknown_when_the_terminal_does_not_answer(tmp_path):
    proc = run_in_pty(["doctor", "--timeout", "0.3"], tmp_path)
    try:
        proc.read_until("\x1b[c")
        out = proc.read_until("did not answer", timeout=5)
        assert "did not answer" in out
    finally:
        proc.close()
