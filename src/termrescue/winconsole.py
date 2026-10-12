"""The Windows console.

On Windows a second thing gets stuck besides the terminal's mouse mode.
ssh.exe switches the console's input to "virtual-terminal input"
(ENABLE_VIRTUAL_TERMINAL_INPUT) so it can forward escape codes to the remote
side. If it dies without switching it back, PowerShell and cmd receive the
terminal's raw escape codes (mouse reports, arrow keys) as if they were typed.

The helpers at the top are pure, so they can be tested anywhere; the
WindowsTerminal class needs a real console.
"""

from __future__ import annotations

import ctypes
import time
from collections.abc import Iterator
from contextlib import contextmanager

ENABLE_PROCESSED_INPUT = 0x0001
ENABLE_LINE_INPUT = 0x0002
ENABLE_ECHO_INPUT = 0x0004
ENABLE_VIRTUAL_TERMINAL_INPUT = 0x0200
ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004  # output mode flag


def repaired_input_mode(mode: int) -> int:
    """``mode`` with virtual-terminal input switched off and everything else kept."""
    return mode & ~ENABLE_VIRTUAL_TERMINAL_INPUT


def describe_input_mode(mode: int) -> str:
    if mode & ENABLE_VIRTUAL_TERMINAL_INPUT:
        return (f"Console input mode 0x{mode:04X}: virtual-terminal input is ON. PowerShell and "
                "cmd will read the terminal's escape codes (mouse reports, arrow keys) as typed "
                "text. `termrescue fix` turns it off.")
    return (f"Console input mode 0x{mode:04X}: virtual-terminal input is off "
            "(normal for PowerShell and cmd).")


class NoConsoleError(OSError):
    pass


class WindowsTerminal:
    def __init__(self) -> None:
        from ctypes import wintypes

        self._wt = wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateFileW.restype = wintypes.HANDLE
        k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                    wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
                                    wintypes.HANDLE]
        k32.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        k32.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k32.WriteConsoleW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, wintypes.DWORD,
                                      ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
        k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k32.WaitForSingleObject.restype = wintypes.DWORD
        k32.GetNumberOfConsoleInputEvents.argtypes = [wintypes.HANDLE,
                                                      ctypes.POINTER(wintypes.DWORD)]
        k32.ReadConsoleInputW.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                                          ctypes.POINTER(wintypes.DWORD)]
        k32.FlushConsoleInputBuffer.argtypes = [wintypes.HANDLE]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        self._k32 = k32

        self.conin = self._open("CONIN$")
        self.conout = self._open("CONOUT$")

    def _open(self, name: str) -> int:
        generic_read_write = 0x80000000 | 0x40000000
        share_read_write = 0x1 | 0x2
        open_existing = 3
        handle = self._k32.CreateFileW(name, generic_read_write, share_read_write, None,
                                       open_existing, 0, None)
        if handle in (None, ctypes.c_void_p(-1).value):
            raise NoConsoleError(ctypes.get_last_error(), f"no console attached ({name})")
        return handle

    def close(self) -> None:
        self._k32.CloseHandle(self.conin)
        self._k32.CloseHandle(self.conout)

    # --- modes ------------------------------------------------------------------

    def _mode(self, handle: int) -> int:
        mode = self._wt.DWORD()
        if not self._k32.GetConsoleMode(handle, ctypes.byref(mode)):
            raise ctypes.WinError(ctypes.get_last_error())
        return mode.value

    def _set_mode(self, handle: int, mode: int) -> None:
        if not self._k32.SetConsoleMode(handle, mode):
            raise ctypes.WinError(ctypes.get_last_error())

    def input_mode(self) -> int:
        return self._mode(self.conin)

    def set_input_mode(self, mode: int) -> None:
        self._set_mode(self.conin, mode)

    def repair_input_mode(self) -> bool:
        mode = self.input_mode()
        fixed = repaired_input_mode(mode)
        if fixed == mode:
            return False
        self.set_input_mode(fixed)
        self._k32.FlushConsoleInputBuffer(self.conin)  # reports the dead session left queued
        return True

    def input_mode_stuck(self) -> bool:
        return bool(self.input_mode() & ENABLE_VIRTUAL_TERMINAL_INPUT)

    def input_mode_report(self) -> str | None:
        return describe_input_mode(self.input_mode())

    # --- output -----------------------------------------------------------------

    def write(self, text: str) -> None:
        """Write ``text``, with escape-code processing on for the duration."""
        saved = self._mode(self.conout)
        if not saved & ENABLE_VIRTUAL_TERMINAL_PROCESSING:
            self._set_mode(self.conout, saved | ENABLE_VIRTUAL_TERMINAL_PROCESSING)
        try:
            written = self._wt.DWORD()
            units = len(text.encode("utf-16-le")) // 2
            self._k32.WriteConsoleW(self.conout, text, units, ctypes.byref(written), None)
        finally:
            if not saved & ENABLE_VIRTUAL_TERMINAL_PROCESSING:
                self._set_mode(self.conout, saved)

    # --- input ------------------------------------------------------------------

    @contextmanager
    def raw(self) -> Iterator[None]:
        """Escape codes passed through as characters, no echo or line editing.

        Leaving restores the previous mode and discards anything left over.
        """
        saved = self.input_mode()
        raw = (saved | ENABLE_VIRTUAL_TERMINAL_INPUT) & ~(
            ENABLE_LINE_INPUT | ENABLE_ECHO_INPUT | ENABLE_PROCESSED_INPUT)
        self.set_input_mode(raw)
        try:
            yield
        finally:
            self.set_input_mode(saved)
            self._k32.FlushConsoleInputBuffer(self.conin)

    def read_available(self, timeout: float) -> str:
        """Characters typed (or sent by the terminal) within ``timeout`` seconds."""
        wt = self._wt

        class KeyEventRecord(ctypes.Structure):
            _fields_ = [("bKeyDown", wt.BOOL), ("wRepeatCount", wt.WORD),
                        ("wVirtualKeyCode", wt.WORD), ("wVirtualScanCode", wt.WORD),
                        ("UnicodeChar", wt.WCHAR), ("dwControlKeyState", wt.DWORD)]

        class Event(ctypes.Union):
            _fields_ = [("KeyEvent", KeyEventRecord), ("_size", ctypes.c_byte * 16)]

        class InputRecord(ctypes.Structure):
            _fields_ = [("EventType", wt.WORD), ("Event", Event)]

        key_event = 0x0001
        deadline = time.monotonic() + max(timeout, 0)
        while True:
            remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
            if self._k32.WaitForSingleObject(self.conin, remaining_ms) != 0:
                return ""
            count = wt.DWORD()
            self._k32.GetNumberOfConsoleInputEvents(self.conin, ctypes.byref(count))
            if count.value:
                records = (InputRecord * count.value)()
                read = wt.DWORD()
                self._k32.ReadConsoleInputW(self.conin, records, count.value, ctypes.byref(read))
                chars = "".join(
                    r.Event.KeyEvent.UnicodeChar * max(1, r.Event.KeyEvent.wRepeatCount)
                    for r in records[: read.value]
                    if r.EventType == key_event and r.Event.KeyEvent.bKeyDown
                    and r.Event.KeyEvent.UnicodeChar != "\x00"
                )
                if chars:
                    return chars
            if time.monotonic() >= deadline:
                return ""
