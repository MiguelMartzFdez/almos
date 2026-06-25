"""Launch EasyALMOS using only its bundled Conda environment."""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from uuid import uuid4


STARTUP_NOTICE_TITLE = "EasyALMOS"
STARTUP_NOTICE_MESSAGE = "EasyALMOS is opening..."
STARTUP_NOTICE_DETAIL = "Please wait. This message will close automatically."
WINDOW_POLL_SECONDS = 0.25
STARTUP_NOTICE_TIMEOUT_SECONDS = 120


def create_startup_signal_path() -> Path:
    return Path(tempfile.gettempdir()) / f"easyalmos-launch-{uuid4().hex}.ready"


def mark_startup_ready(signal_path: Path | None) -> None:
    if signal_path is None:
        return

    try:
        signal_path.write_text("ready", encoding="utf-8")
    except OSError:
        pass


def current_process_has_visible_window() -> bool:
    if os.name != "nt":
        return False

    user32 = ctypes.windll.user32
    current_pid = os.getpid()
    found_window = False

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def enum_windows_callback(window_handle, _lparam):
        nonlocal found_window

        process_id = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(window_handle, ctypes.byref(process_id))
        if process_id.value != current_pid:
            return True

        if not user32.IsWindowVisible(window_handle):
            return True

        if user32.GetWindow(window_handle, 4):
            return True

        found_window = True
        return False

    user32.EnumWindows(enum_windows_callback, 0)
    return found_window


def start_window_ready_watcher(signal_path: Path | None) -> None:
    if signal_path is None or os.name != "nt":
        return

    def watch_for_window() -> None:
        deadline = time.monotonic() + STARTUP_NOTICE_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if signal_path.exists():
                return

            if current_process_has_visible_window():
                mark_startup_ready(signal_path)
                return

            time.sleep(WINDOW_POLL_SECONDS)

    threading.Thread(target=watch_for_window, daemon=True).start()


def start_startup_notice(signal_path: Path) -> None:
    if os.name != "nt":
        return

    subprocess.Popen(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--show-startup-notice",
            str(signal_path),
            str(os.getpid()),
        ]
    )


def parent_process_is_running(parent_pid: int) -> bool:
    if os.name != "nt":
        return True

    kernel32 = ctypes.windll.kernel32
    process_handle = kernel32.OpenProcess(0x100000, False, parent_pid)
    if not process_handle:
        return False

    try:
        wait_result = kernel32.WaitForSingleObject(process_handle, 0)
        return wait_result == 0x00000102
    finally:
        kernel32.CloseHandle(process_handle)


def run_startup_notice(signal_path: Path, parent_pid: int) -> int:
    import tkinter as tk

    root = tk.Tk()
    root.title(STARTUP_NOTICE_TITLE)
    root.resizable(False, False)
    root.attributes("-topmost", True)
    root.protocol("WM_DELETE_WINDOW", lambda: None)

    frame = tk.Frame(root, padx=18, pady=16)
    frame.pack(fill="both", expand=True)

    tk.Label(
        frame,
        text=STARTUP_NOTICE_MESSAGE,
        font=("Segoe UI", 11, "bold"),
        anchor="w",
        justify="left",
    ).pack(anchor="w")

    tk.Label(
        frame,
        text=STARTUP_NOTICE_DETAIL,
        font=("Segoe UI", 9),
        anchor="w",
        justify="left",
        wraplength=300,
    ).pack(anchor="w", pady=(8, 0))

    root.update_idletasks()
    width = root.winfo_width()
    height = root.winfo_height()
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    position_x = max((screen_width - width) // 2, 0)
    position_y = max((screen_height - height) // 3, 0)
    root.geometry(f"{width}x{height}+{position_x}+{position_y}")

    started_at = time.monotonic()

    def poll_for_close() -> None:
        if signal_path.exists():
            root.destroy()
            return

        if not parent_process_is_running(parent_pid):
            root.destroy()
            return

        if time.monotonic() - started_at >= STARTUP_NOTICE_TIMEOUT_SECONDS:
            root.destroy()
            return

        root.after(int(WINDOW_POLL_SECONDS * 1000), poll_for_close)

    root.after(int(WINDOW_POLL_SECONDS * 1000), poll_for_close)
    root.mainloop()
    return 0


def configure_private_environment() -> None:
    app_dir = Path(__file__).resolve().parent
    miniforge_dir = app_dir / "miniforge"
    env_dir = miniforge_dir / "envs" / "almos"

    private_paths = [
        env_dir,
        env_dir / "Scripts",
        env_dir / "Library" / "bin",
        env_dir / "Library" / "usr" / "bin",
        env_dir / "Library" / "mingw-w64" / "bin",
        miniforge_dir / "condabin",
    ]

    existing_path = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join(
        [str(path) for path in private_paths if path.exists()] + [existing_path]
    )
    os.environ["CONDA_PREFIX"] = str(env_dir)
    os.environ["CONDA_DEFAULT_ENV"] = "almos"
    os.environ["CONDA_SHLVL"] = "1"


def suppress_console_subprocesses() -> None:
    if os.name != "nt":
        return

    original_popen = subprocess.Popen

    def hidden_popen(*args, **kwargs):
        creationflags = kwargs.get("creationflags", 0)
        kwargs["creationflags"] = creationflags | subprocess.CREATE_NO_WINDOW

        startupinfo = kwargs.get("startupinfo")
        if startupinfo is None:
            startupinfo = subprocess.STARTUPINFO()

        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = startupinfo

        return original_popen(*args, **kwargs)

    subprocess.Popen = hidden_popen


def main() -> int:
    if len(sys.argv) >= 4 and sys.argv[1] == "--show-startup-notice":
        return run_startup_notice(Path(sys.argv[2]), int(sys.argv[3]))

    startup_signal_path = create_startup_signal_path()
    start_startup_notice(startup_signal_path)
    start_window_ready_watcher(startup_signal_path)

    configure_private_environment()
    suppress_console_subprocesses()
    try:
        from almos.easyalmos import main as easyalmos_main

        result = easyalmos_main()
        return result if isinstance(result, int) else 0
    finally:
        mark_startup_ready(startup_signal_path)


if __name__ == "__main__":
    sys.exit(main())
