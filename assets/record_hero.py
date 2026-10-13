"""Record assets/before-after.svg from two real zsh sessions.

Each session runs zsh in a pseudo terminal. This script plays the terminal:
it tracks the mouse modes that zsh's output turns on and off, and while
mouse motion reporting (mode 1003) is on, it "moves the mouse" by sending
SGR mouse reports, the way a real terminal does. pyte draws the screen.

    uv run --no-project --with pyte python assets/record_hero.py

Needs macOS or Linux with zsh.
"""

from __future__ import annotations

import os
import pty
import re
import select
import subprocess
import tempfile
import time
from html import escape
from pathlib import Path

import pyte

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "src" / "termrescue" / "shell" / "termrescue.zsh"
COLS, ROWS = 58, 10
MODE = re.compile(r"\x1b\[\?1003([hl])")


class Session:
    def __init__(self, with_hook: bool):
        self.home = Path(tempfile.mkdtemp())
        # pyte wraps the padding of zsh's PROMPT_SP into blank lines; real terminals don't.
        rc = "PS1='%F{blue}~%f %# '\nunsetopt prompt_sp\n"
        if with_hook:
            rc += f"source {HOOK}\n"
        (self.home / ".zshrc").write_text(rc)
        program = self.home / "dies-in-mouse-mode"
        # What a remote tmux or vim leaves behind when the SSH link drops.
        program.write_text("#!/bin/sh\nprintf '\\033[?1003h\\033[?1006h'\nkill -9 $$\n")
        program.chmod(0o755)
        self.master, slave = pty.openpty()
        env = {"HOME": str(self.home), "ZDOTDIR": str(self.home), "TERM": "xterm-256color",
               "PATH": "/usr/bin:/bin", "LANG": "en_US.UTF-8"}
        self.proc = subprocess.Popen(["zsh", "-d", "-i"], stdin=slave, stdout=slave,
                                     stderr=slave, env=env, cwd=self.home,
                                     start_new_session=True)
        os.close(slave)
        self.screen = pyte.Screen(COLS, ROWS)
        self.stream = pyte.Stream(self.screen)
        self.raw = ""
        self.mouse_motion = False

    def pump(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while (left := deadline - time.monotonic()) > 0:
            ready, _, _ = select.select([self.master], [], [], left)
            if ready:
                chunk = os.read(self.master, 65536).decode(errors="replace")
                self.raw += chunk
                for on_off in MODE.findall(chunk):
                    self.mouse_motion = on_off == "h"
                self.stream.feed(chunk)

    def type(self, text: str) -> None:
        for ch in text:
            os.write(self.master, ch.encode())
            self.pump(0.03)

    def move_mouse(self) -> None:
        """Send motion reports only while the terminal is in motion-reporting mode."""
        for x in range(30, 33):
            if self.mouse_motion:
                os.write(self.master, f"\x1b[<35;{x};{6 + x % 3}M".encode())
            self.pump(0.02)

    def close(self) -> list[list[tuple[str, str]]]:
        self.proc.kill()
        self.proc.wait()
        os.close(self.master)
        return [[(self.screen.buffer[y][x].data, self.screen.buffer[y][x].fg)
                 for x in range(COLS)] for y in range(ROWS)]


def record(with_hook: bool) -> list[list[tuple[str, str]]]:
    s = Session(with_hook)
    s.pump(1.0)
    s.type("./dies-in-mouse-mode\r")
    s.pump(0.8)
    s.move_mouse()
    s.pump(0.3)
    s.type("echo hello\r")
    s.pump(0.8)
    return s.close()


COLOURS = {"blue": "#58a6ff", "default": "#e6edf3"}


def panel(rows, x0: int, title: str, title_class: str) -> str:
    out = [f'<g transform="translate({x0} 0)">',
           '<rect x="0.5" y="0.5" width="489" height="299" rx="10" fill="#0d1117" stroke="#30363d"/>',
           ('<path d="M0.5 36 V10.5 A10 10 0 0 1 10.5 0.5 H479.5 A10 10 0 0 1 489.5 10.5 V36 Z"'
           ' fill="#161b22"/>'),
           ('<circle cx="20" cy="18" r="5.5" fill="#ff5f57"/><circle cx="38" cy="18" r="5.5"'
           ' fill="#febc2e"/><circle cx="56" cy="18" r="5.5" fill="#28c840"/>'),
           f'<text x="245" y="23" text-anchor="middle" class="label {title_class}">{title}</text>',
           '<text class="mono" xml:space="preserve">']
    for y, row in enumerate(rows):
        spans, current, text = [], None, ""
        for ch, fg in row:
            colour = COLOURS.get(fg, COLOURS["default"])
            if colour != current and text:
                spans.append(f'<tspan fill="{current}">{escape(text)}</tspan>')
                text = ""
            current = colour
            text += ch
        text = text.rstrip()
        if text:
            spans.append(f'<tspan fill="{current}">{escape(text)}</tspan>')
        if spans:
            out.append(f'<tspan x="16" y="{62 + y * 24}">{"".join(spans)}</tspan>')
    out += ["</text>", "</g>"]
    return "\n".join(out)


def main() -> None:
    before, after = record(with_hook=False), record(with_hook=True)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 300" role="img" aria-labelledby="title desc">
<title id="title">termrescue: before and after</title>
<desc id="desc">Two real zsh sessions. A program turns on mouse reporting and is killed. Without termrescue, mouse movement types escape codes into the next command. With termrescue, the prompt switches mouse reporting off and the command runs.</desc>
<style>
.mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; font-size: 14px; }}
.label {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; font-size: 13px; font-weight: 600; letter-spacing: .04em; }}
.junk {{ fill: #ff7b72; }}
.ok {{ fill: #3fb950; }}
</style>
{panel(before, 0, "ZSH WITHOUT TERMRESCUE", "junk")}
{panel(after, 510, "ZSH WITH TERMRESCUE", "ok")}
</svg>
"""
    (ROOT / "assets" / "before-after.svg").write_text(svg)


if __name__ == "__main__":
    main()
