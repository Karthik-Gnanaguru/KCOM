#!/usr/bin/env python3
"""Strip unused Qt6 modules from a PyInstaller dist directory.

KCom only uses these Qt modules:
    QtCore · QtGui · QtWidgets · QtNetwork · QtSerialPort

PyInstaller bundles roughly 30+ extra Qt modules (QtQuick, QtQml, Qt3D*,
QtMultimedia, QtCharts, QtPdf, QtWebEngine, all SQL drivers, the entire
QML module tree, etc.) — totalling 50–100 MB of dead weight. This script
walks the PyInstaller output, removes Qt files KCom never loads, and
reports how much it saved.

Usage (called automatically by the per-OS build scripts):
    python build/post_clean.py dist/KCom
"""

from __future__ import annotations

import os
import shutil
import sys


# Qt6 modules KCom actually imports (verified via grep across kcom/).
KEEP_QT_MODULES = {
    "Core",
    "Gui",
    "Widgets",
    "Network",
    "SerialPort",
    # Runtime dependencies of the above
    "DBus",        # Linux IPC backend
    "OpenGL",      # pulled in by QtGui on some platforms
    "Svg",         # SVG image-format plugin uses this
    "XcbQpa",      # xcb platform plugin (Linux)
}

# Qt plugin folders we keep (under plugins/). Everything else is wiped.
KEEP_PLUGIN_DIRS = {
    "platforms",              # xcb / cocoa / windows — required
    "platformthemes",         # native look & feel
    "platforminputcontexts",  # IME support
    "imageformats",           # PNG / JPEG / ICO / SVG (further trimmed below)
    "iconengines",            # SVG icon engine
    "styles",                 # native style plugins
    "tls",                    # QtNetwork TLS backend
    "networkinformation",     # QtNetwork
    "generic",                # input devices
}

# Within imageformats/, keep only these formats (matched case-insensitively).
KEEP_IMAGE_FORMATS = {"png", "jpeg", "jpg", "ico", "svg", "gif"}


def _find_qt_root(dist_dir: str) -> str | None:
    """Return the path to PyQt6/Qt6 inside the PyInstaller output."""
    for rel in (
        ("_internal", "PyQt6", "Qt6"),
        ("PyQt6", "Qt6"),
        ("Contents", "MacOS", "_internal", "PyQt6", "Qt6"),
        ("Contents", "Resources", "_internal", "PyQt6", "Qt6"),
        ("Contents", "MacOS", "PyQt6", "Qt6"),
        ("Contents", "Frameworks", "PyQt6", "Qt6"),
    ):
        path = os.path.join(dist_dir, *rel)
        if os.path.isdir(path):
            return path
    return None


def _dir_size(path: str) -> int:
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def _qt_module_name(filename: str) -> str | None:
    """Extract the Qt module name from a binary file name.

    Examples:
        libQt6Network.so.6        -> "Network"
        Qt6Network.dll            -> "Network"
        QtNetwork                 -> "Network"   (macOS framework dir)
    """
    name = filename
    # Strip common prefixes
    for prefix in ("libQt6", "libqt6", "Qt6", "qt6", "Qt"):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    else:
        return None
    # Take leading alpha chars as the module name
    out = ""
    for c in name:
        if c.isalpha():
            out += c
        else:
            break
    return out or None


def _rm(path: str) -> int:
    """Remove a file or directory; return bytes freed (best-effort)."""
    try:
        if os.path.isdir(path) and not os.path.islink(path):
            freed = _dir_size(path)
            shutil.rmtree(path, ignore_errors=True)
            return freed
        size = os.path.getsize(path)
        os.remove(path)
        return size
    except OSError:
        return 0


def _clean(qt_root: str) -> int:
    """Run all cleanup passes inside the Qt6 root. Return bytes freed."""
    freed = 0

    # 1. Wipe the QML module tree entirely (KCom doesn't use QML).
    qml = os.path.join(qt_root, "qml")
    if os.path.isdir(qml):
        freed += _rm(qml)

    # 2. Wipe entire plugin subdirs we don't need.
    plugins = os.path.join(qt_root, "plugins")
    if os.path.isdir(plugins):
        for entry in os.listdir(plugins):
            if entry not in KEEP_PLUGIN_DIRS:
                freed += _rm(os.path.join(plugins, entry))

    # 3. Trim imageformats to essentials (drop tiff/webp/heic/wbmp/etc.).
    img = os.path.join(plugins, "imageformats")
    if os.path.isdir(img):
        for f in os.listdir(img):
            low = f.lower()
            keep = any(fmt in low for fmt in KEEP_IMAGE_FORMATS)
            if not keep:
                freed += _rm(os.path.join(img, f))

    # 4. Strip unused Qt6 shared libraries from lib/ and bin/.
    for libdir_name in ("lib", "bin"):
        libdir = os.path.join(qt_root, libdir_name)
        if not os.path.isdir(libdir):
            continue
        for fname in list(os.listdir(libdir)):
            module = _qt_module_name(fname)
            if module is None:
                continue
            if module in KEEP_QT_MODULES:
                continue
            freed += _rm(os.path.join(libdir, fname))

    # 5. macOS frameworks layout: lib/Qt<Module>.framework/
    lib = os.path.join(qt_root, "lib")
    if os.path.isdir(lib):
        for entry in os.listdir(lib):
            if not entry.endswith(".framework"):
                continue
            module = _qt_module_name(entry[: -len(".framework")])
            if module and module not in KEEP_QT_MODULES:
                freed += _rm(os.path.join(lib, entry))

    # 6. Translations — keep only English.
    tr = os.path.join(qt_root, "translations")
    if os.path.isdir(tr):
        for f in os.listdir(tr):
            if f == "qtbase_en.qm" or f.startswith("qtbase_en."):
                continue
            freed += _rm(os.path.join(tr, f))

    # 7. (libicudata.so is NOT removed — Qt6Core requires it even for the
    #    most basic operations; deleting it causes ImportError at startup.)

    # 8. FFmpeg codecs (only ever used by QtMultimedia, which we already cut).
    for libdir_name in ("lib", "bin"):
        libdir = os.path.join(qt_root, libdir_name)
        if not os.path.isdir(libdir):
            continue
        for fname in list(os.listdir(libdir)):
            low = fname.lower()
            if low.startswith(("libavcodec", "libavformat", "libavutil",
                               "libswresample", "libswscale", "libavfilter",
                               "libavdevice")):
                freed += _rm(os.path.join(libdir, fname))

    # 9. QScintilla API hints (build-time IDE auto-complete data, useless at runtime).
    qsci = os.path.join(qt_root, "qsci")
    if os.path.isdir(qsci):
        freed += _rm(qsci)

    # 10. Qt resources directory (icudtl.dat for QtWebEngine, etc.).
    res = os.path.join(qt_root, "resources")
    if os.path.isdir(res):
        freed += _rm(res)

    # 11. libexec — Qt helper binaries (QtWebEngineProcess, etc.).
    libexec = os.path.join(qt_root, "libexec")
    if os.path.isdir(libexec):
        freed += _rm(libexec)

    return freed


# ── Top-level dist cleanup (libraries outside PyQt6/) ───────────────────────

# Python packages that get pulled in transitively but KCom never imports.
# These are removed from the top-level _internal/ directory.
DROP_PACKAGES = {
    "cryptography",  # fastapi pulls it in for HTTPS; KCom's API is HTTP-only
    "uvloop",        # alternative asyncio loop; stdlib asyncio works fine
}

# Top-level shared libraries that are phantom pull-ins or duplicated by the OS.
DROP_LIB_PREFIXES = (
    "libgtk-3",        # GTK file-dialog backend; Qt has its own
    "libgdk-3",
    "libapt-pkg",      # APT lib, no idea why it's bundled
    "libavcodec",      # FFmpeg multimedia (also wiped inside Qt6/)
    "libavformat",
    "libavutil",
    "libswresample",
    "libswscale",
    "libavfilter",
    "libavdevice",
)


def _find_internal_dir(dist_dir: str) -> str | None:
    """Locate PyInstaller's `_internal/` directory (or root for older layouts)."""
    for rel in (
        ("_internal",),
        ("Contents", "MacOS", "_internal"),
        ("Contents", "Resources", "_internal"),
    ):
        path = os.path.join(dist_dir, *rel)
        if os.path.isdir(path):
            return path
    # Older PyInstaller put everything next to the binary
    if os.path.isfile(os.path.join(dist_dir, "base_library.zip")):
        return dist_dir
    return None


def _clean_internal(internal: str) -> int:
    """Strip dead-weight packages and system libs from PyInstaller's _internal/."""
    freed = 0

    # Drop unused Python packages.
    for pkg in DROP_PACKAGES:
        pkg_dir = os.path.join(internal, pkg)
        if os.path.isdir(pkg_dir):
            freed += _rm(pkg_dir)
        # Some packages ship as .so files instead of dirs
        for ext in (".so", ".pyd", ".dylib"):
            for entry in os.listdir(internal):
                low = entry.lower()
                if low.startswith(pkg) and low.endswith(ext):
                    freed += _rm(os.path.join(internal, entry))

    # Drop phantom system libs.
    for entry in list(os.listdir(internal)):
        low = entry.lower()
        if any(low.startswith(p) for p in DROP_LIB_PREFIXES):
            freed += _rm(os.path.join(internal, entry))

    return freed


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: post_clean.py <dist/KCom>", file=sys.stderr)
        return 2

    dist = sys.argv[1]
    if not os.path.isdir(dist):
        print(f"Not a directory: {dist}", file=sys.stderr)
        return 1

    qt = _find_qt_root(dist)
    if qt is None:
        print(f"PyQt6/Qt6 not found inside {dist} — nothing to clean.")
        return 0

    before = _dir_size(dist)
    freed = _clean(qt)

    internal = _find_internal_dir(dist)
    if internal is not None:
        freed += _clean_internal(internal)

    after = _dir_size(dist)

    def mb(n: int) -> str:
        return f"{n / 1024 / 1024:6.1f} MB"

    print("── PyQt6 cleanup ───────────────────────────────────────────")
    print(f"  Before : {mb(before)}")
    print(f"  After  : {mb(after)}")
    print(f"  Saved  : {mb(freed)}  ({100 * freed / before:.1f} %)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
