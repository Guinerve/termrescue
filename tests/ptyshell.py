"""Drive a real interactive shell inside a pseudo-terminal for tests."""

from __future__ import annotations

import os
import select
import subprocess
import time
from pathlib import Path

PROMPT = "READY> "
SHELL_DIR = Path(__file__).resolve().parent.parent / "src" / "termrescue" / "shell"


class PtyShell:
    def __init__(self, argv: list[str], env: dict[str, str], cwd: Path):
        import pty  # Unix only; tests that use PtyShell skip on Windows

        self.master, slave = pty.openpty()
        self.proc = subprocess.Popen(
            argv, stdin=slave, stdout=slave, stderr=slave, env=env, cwd=cwd,
            start_new_session=True,
        )
        os.close(slave)
        self.output = ""

    def send(self, text: str) -> None:
        os.write(self.master, text.encode())

    def read_until(self, needle: str, timeout: float = 5.0, start: int = 0) -> str:
        """Read until ``needle`` appears after offset ``start``; return all output."""
        deadline = time.monotonic() + timeout
        while needle not in self.output[start:]:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"{needle!r} not seen; output so far: {self.output!r}")
            ready, _, _ = select.select([self.master], [], [], remaining)
            if ready:
                try:
                    chunk = os.read(self.master, 65536)
                except OSError:
                    chunk = b""
                if not chunk:
                    raise EOFError(f"shell exited; output: {self.output!r}")
                self.output += chunk.decode(errors="replace")
        return self.output

    def wait_for_prompt(self, after: int = 0) -> int:
        """Wait for the next prompt after offset ``after``; return the new offset."""
        self.read_until(PROMPT, start=after)
        return self.output.index(PROMPT, after) + len(PROMPT)

    def close(self) -> None:
        self.proc.kill()
        self.proc.wait()
        os.close(self.master)


def base_env(home: Path) -> dict[str, str]:
    return {
        "HOME": str(home),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "TERM": "xterm-256color",
        "LANG": "en_US.UTF-8",
    }


def start_zsh(home: Path, rc_extra: str = "") -> PtyShell:
    (home / ".zshrc").write_text(
        f"PS1='{PROMPT}'\n"
        f"source {SHELL_DIR / 'termrescue.zsh'}\n"
        "preexec() { print -rn -- \"$1\" > $HOME/last-command }\n"
        f"{rc_extra}\n"
    )
    env = base_env(home) | {"ZDOTDIR": str(home)}
    # -d: skip system-wide startup files (e.g. Ubuntu's /etc/zsh/zshrc runs compinit,
    # which can stop at an interactive question), so only our .zshrc is loaded.
    return PtyShell(["zsh", "-d", "-i"], env, home)


def start_bash(home: Path, rc_extra: str = "") -> PtyShell:
    rc = home / ".bashrc"
    rc.write_text(
        f"PS1='{PROMPT}'\n"
        f"{rc_extra}\n"
        f"source {SHELL_DIR / 'termrescue.bash'}\n"
    )
    return PtyShell(["bash", "--noprofile", "--rcfile", str(rc), "-i"], base_env(home), home)
