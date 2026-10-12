"""Access to the terminal the user is sitting at, on Unix and Windows."""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Protocol


class Terminal(Protocol):
    def write(self, text: str) -> None: ...

    def read_available(self, timeout: float) -> str:
        """Whatever arrives within ``timeout`` seconds (empty string if nothing)."""
        ...

    def raw(self) -> AbstractContextManager[None]:
        """No echo, no line buffering, escape codes passed through."""
        ...

    def repair_input_mode(self) -> bool:
        """Undo input settings a dead program left behind; True if anything was wrong."""
        ...

    def input_mode_report(self) -> str | None:
        """A one-line description of the input mode, where the platform has one."""
        ...

    def input_mode_stuck(self) -> bool:
        """True if a dead program left the input mode broken."""
        ...


class PosixTerminal:
    def __init__(self, read_fd: int, write_fd: int):
        self.read_fd = read_fd
        self.write_fd = write_fd

    def write(self, text: str) -> None:
        os.write(self.write_fd, text.encode())

    def read_available(self, timeout: float) -> str:
        import select

        ready, _, _ = select.select([self.read_fd], [], [], max(timeout, 0))
        if not ready:
            return ""
        return os.read(self.read_fd, 4096).decode(errors="replace")

    @contextmanager
    def raw(self) -> Iterator[None]:
        """Entering keeps input that has already arrived; leaving discards anything
        left over so late replies don't leak into the shell."""
        import termios
        import tty

        saved = termios.tcgetattr(self.read_fd)
        tty.setraw(self.read_fd, termios.TCSANOW)
        try:
            yield
        finally:
            termios.tcsetattr(self.read_fd, termios.TCSAFLUSH, saved)

    def repair_input_mode(self) -> bool:
        return False  # the shell's line editor resets the tty itself

    def input_mode_report(self) -> str | None:
        return None

    def input_mode_stuck(self) -> bool:
        return False


@contextmanager
def open_terminal() -> Iterator[Terminal]:
    """The user's terminal: the Windows console, /dev/tty, or else stdin/stdout."""
    if sys.platform == "win32":
        from .winconsole import WindowsTerminal

        term = WindowsTerminal()
        try:
            yield term
        finally:
            term.close()
        return
    try:
        fd = os.open("/dev/tty", os.O_RDWR | os.O_NOCTTY)
    except OSError:
        yield PosixTerminal(0, 1)
        return
    try:
        yield PosixTerminal(fd, fd)
    finally:
        os.close(fd)


def read_until(term: Terminal, done: Callable[[str], bool], timeout: float) -> str:
    """Read until ``done(text)`` is true or ``timeout`` seconds pass."""
    text = ""
    deadline = time.monotonic() + timeout
    while not done(text):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        text += term.read_available(remaining)
    return text
