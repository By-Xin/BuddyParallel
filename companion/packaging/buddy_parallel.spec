# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


REPO_ROOT = Path(SPECPATH).resolve().parents[1]
COMPANION_ROOT = REPO_ROOT / "companion"
APP_ROOT = COMPANION_ROOT / "app"
ENTRYPOINT = COMPANION_ROOT / "scripts" / "run_companion.py"

hiddenimports = sorted(
    set(
        collect_submodules("buddy_parallel")
        + collect_submodules("esptool")
        + collect_submodules("lark_oapi.ws.pb")
        + [
            "PIL._tkinter_finder",
            "socks",
            "pystray._win32",
        ]
    )
)

firmware_sources = [
    REPO_ROOT / "firmware" / ".pio" / "build" / "m5stickc-plus" / "bootloader.bin",
    REPO_ROOT / "firmware" / ".pio" / "build" / "m5stickc-plus" / "partitions.bin",
    REPO_ROOT / "firmware" / ".pio" / "build" / "m5stickc-plus" / "firmware.bin",
    REPO_ROOT
    / "firmware"
    / ".platformio_local"
    / "packages"
    / "framework-arduinoespressif32"
    / "tools"
    / "partitions"
    / "boot_app0.bin",
]
datas = collect_data_files("esptool") + [(str(path), "firmware") for path in firmware_sources if path.exists()]
excludes = [
    "IPython",
    "PyQt5",
    "black",
    "docutils",
    "jedi",
    "jupyter_client",
    "lxml",
    "matplotlib",
    "numpy",
    "pandas",
    "pytest",
    "scipy",
    "sphinx",
    "twisted",
    "zmq",
]

a = Analysis(
    [str(ENTRYPOINT)],
    pathex=[str(APP_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    name="BuddyParallel",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    exclude_binaries=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="BuddyParallel",
)
