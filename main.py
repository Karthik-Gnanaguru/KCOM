#!/usr/bin/env python3
"""KCom — Professional Serial & Network Communication Studio.

Entry point. Run with:
    python main.py [options] [project.kcom]

Options
-------
--run SCRIPT        Load and immediately execute a Python script.
--minimize          Start with the main window minimized.
--invisible         Start without showing the main window (headless scripting).
project.kcom        Optional project file to load on startup.
"""

from __future__ import annotations

import argparse
import sys
import os
import subprocess

# Prefer the stable XCB (X11) backend on Linux/Wayland to avoid Wayland
# compositor limitations (pointer warp, window positioning, etc.).
if sys.platform.startswith("linux") and "QT_QPA_PLATFORM" not in os.environ:
    os.environ["QT_QPA_PLATFORM"] = "xcb"

# Ensure the package root is importable when running as a script
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _ensure_dependencies() -> None:
    """Install any missing packages from requirements.txt before the app starts.

    Uses import probing as a fast check — only calls pip when something is
    actually missing, so normal startups add zero overhead.
    """
    _PROBE = [
        ("PyQt6",   "PyQt6"),
        ("serial",  "pyserial"),
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
    ]
    missing = [name for mod, name in _PROBE if not _importable(mod)]
    if not missing:
        return

    req_file = os.path.join(_ROOT, "requirements.txt")
    print(f"KCom: missing packages detected: {', '.join(missing)}")
    print("KCom: installing from requirements.txt …")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", req_file, "--quiet"],
            check=True,
        )
        print("KCom: all packages installed — ready.")
    except subprocess.CalledProcessError as exc:
        print(
            f"KCom: install failed (exit {exc.returncode}).\n"
            "      Run manually:  pip install -r requirements.txt",
            file=sys.stderr,
        )


def _importable(module: str) -> bool:
    import importlib.util
    return importlib.util.find_spec(module) is not None


_ensure_dependencies()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="kcom",
        description="KCom — Serial & Network Communication Studio",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "project",
        nargs="?",
        metavar="project.kcom",
        help="KCom project file to load on startup",
    )
    parser.add_argument(
        "--run",
        metavar="SCRIPT",
        help="Python script to load and run automatically on startup",
    )
    parser.add_argument(
        "--minimize",
        action="store_true",
        help="Start with the main window minimized",
    )
    parser.add_argument(
        "--invisible",
        action="store_true",
        help="Start without showing the main window (headless scripting)",
    )
    return parser.parse_args()


def _apply_process_priority(priority: str) -> None:
    """Set OS process priority. Best-effort — failure is silently ignored."""
    try:
        if sys.platform == "win32":
            import ctypes
            _WIN_PRIORITY = {
                "idle":         0x0040,
                "below_normal": 0x4000,
                "normal":       0x0020,
                "above_normal": 0x8000,
                "high":         0x0080,
            }
            p = _WIN_PRIORITY.get(priority)
            if p:
                handle = ctypes.windll.kernel32.GetCurrentProcess()  # type: ignore[attr-defined]
                ctypes.windll.kernel32.SetPriorityClass(handle, p)  # type: ignore[attr-defined]
        else:
            import os as _os
            _NICE = {
                "idle": 19, "below_normal": 10, "normal": 0,
                "above_normal": -5, "high": -10,
            }
            n = _NICE.get(priority)
            if n is not None:
                _os.nice(n - _os.nice(0))
    except Exception:
        pass


def main() -> int:
    """Application entry point."""
    args = _parse_args()

    # Must be created before any other Qt objects
    from kcom.app import KComApp

    app = KComApp()

    # Apply process priority from settings before heavy work
    from kcom.core.settings_store import SettingsStore
    _apply_process_priority(SettingsStore().get_process_priority())

    # Show splash only when the window will be visible
    splash = None
    if not args.invisible:
        splash = app.show_splash()
        app.processEvents()

    # Import heavy modules after splash is visible
    from kcom.core.session_manager import SessionManager
    from kcom.ui.main_window import MainWindow

    # Create core objects
    session_manager = SessionManager()

    # Build main window
    window = MainWindow(
        session_manager=session_manager,
        theme_manager=app.theme_manager,
        settings=app.settings,
    )

    # Apply window visibility options
    if args.invisible:
        pass  # window stays hidden
    elif args.minimize:
        window.showMinimized()
    else:
        if splash is not None:
            splash.finish(window)
            app.hide_splash()
        window.show()

    # Load project file if provided
    if args.project:
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(
            200,
            lambda: window._load_project(os.path.abspath(args.project)),
        )

    # Load and optionally run a script
    if args.run:
        script_path = os.path.abspath(args.run)
        from PyQt6.QtCore import QTimer

        def _load_script() -> None:
            window._script_panel.load_file(script_path)
            window._script_dock.show()
            window._toggle_script_panel_action.setChecked(True)
            # Auto-run when --run flag is given
            window._script_runtime.run_script(
                open(script_path, "r", encoding="utf-8").read(),
                script_path,
            )

        QTimer.singleShot(400, _load_script)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
