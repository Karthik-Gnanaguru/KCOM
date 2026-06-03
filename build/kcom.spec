# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for KCom
#
# Usage (from the project root):
#   pyinstaller build/kcom.spec
#
# Output:  dist/KCom  (folder)  or  dist/KCom.exe  (Windows one-file)
#
# Optional:  pyinstaller build/kcom.spec --onefile   (single executable)

import sys
import os

block_cipher = None

# Collect all kcom sub-packages
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(SPEC)))

# Include kcom package data (themes, icons, etc.)
datas = [
    (os.path.join(_ROOT, "kcom", "resources"), "kcom/resources"),
    (os.path.join(_ROOT, "examples"), "examples"),
]

# Pull in PyQt6 plugins
datas += collect_data_files("PyQt6")

hidden_imports = [
    "kcom.protocols.serial_port",
    "kcom.protocols.tcp_client",
    "kcom.protocols.tcp_server",
    "kcom.protocols.udp_socket",
    "kcom.protocols.named_pipe",
    "kcom.protocols.usb_hid",
    "kcom.api.server",
    "kcom.scripting.runtime",
    "serial",
    "serial.tools.list_ports",
    "PyQt6.QtNetwork",
    "PyQt6.QtSerialPort",
]

# Optional: include fastapi+uvicorn if installed
try:
    import fastapi
    hidden_imports += collect_submodules("fastapi")
    hidden_imports += collect_submodules("uvicorn")
    hidden_imports += collect_submodules("starlette")
except ImportError:
    pass

# Optional: hidapi
try:
    import hid
    hidden_imports.append("hid")
except ImportError:
    pass

a = Analysis(
    [os.path.join(_ROOT, "main.py")],
    pathex=[_ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # General Python modules KCom never imports
        "tkinter", "matplotlib", "numpy", "scipy", "pandas",
        "IPython", "jupyter", "notebook", "sphinx",
        "PIL", "pytest", "setuptools",
        # PyQt6 sub-modules KCom never imports — keeps the analyzer
        # from pulling in their hidden imports.
        "PyQt6.Qt3DCore", "PyQt6.Qt3DRender", "PyQt6.Qt3DAnimation",
        "PyQt6.Qt3DExtras", "PyQt6.Qt3DInput", "PyQt6.Qt3DLogic",
        "PyQt6.QtBluetooth", "PyQt6.QtCharts", "PyQt6.QtDataVisualization",
        "PyQt6.QtDesigner", "PyQt6.QtHelp", "PyQt6.QtMultimedia",
        "PyQt6.QtMultimediaWidgets", "PyQt6.QtNfc", "PyQt6.QtOpenGL",
        "PyQt6.QtOpenGLWidgets", "PyQt6.QtPdf", "PyQt6.QtPdfWidgets",
        "PyQt6.QtPositioning", "PyQt6.QtPrintSupport", "PyQt6.QtQml",
        "PyQt6.QtQuick", "PyQt6.QtQuick3D", "PyQt6.QtQuickWidgets",
        "PyQt6.QtRemoteObjects", "PyQt6.QtScxml", "PyQt6.QtSensors",
        "PyQt6.QtSpatialAudio", "PyQt6.QtSql", "PyQt6.QtStateMachine",
        "PyQt6.QtSvg", "PyQt6.QtSvgWidgets", "PyQt6.QtTest",
        "PyQt6.QtTextToSpeech", "PyQt6.QtWebChannel", "PyQt6.QtWebEngineCore",
        "PyQt6.QtWebEngineQuick", "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtWebSockets", "PyQt6.QtWebView", "PyQt6.QtXml",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Pick the right icon format per platform.
#   Windows → .ico   (PyInstaller refuses .png on Windows)
#   macOS   → .icns  (build script generates this at bundle time)
#   Linux   → .png   (works for both EXE icon resource and AppImage)
_ICON_DIR = os.path.join(_ROOT, "kcom", "resources", "icons")
if sys.platform == "win32":
    _ICON = os.path.join(_ICON_DIR, "kcom_logo.ico")
else:
    _ICON = os.path.join(_ICON_DIR, "kcom_logo.png")

# `strip` is a Unix tool. Asking PyInstaller to run it on Windows
# produces a flood of "Failed to run strip" warnings (and no benefit).
_STRIP = sys.platform != "win32"

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="KCom",
    debug=False,
    bootloader_ignore_signals=False,
    strip=_STRIP,
    upx=True,
    console=False,  # No console window on Windows
    icon=_ICON,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=_STRIP,
    upx=True,
    upx_exclude=[],
    name="KCom",
)
