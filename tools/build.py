"""Build dist/yomitsuke.ankiaddon: the add-on with fugashi and UniDic bundled for every platform.

Anki add-ons can't install Python packages, so everything is inside: fugashi's wheels for
Mac (universal), Windows and Linux (x86_64 and arm64), for Python 3.13 (Anki 26.09) and 3.14, and the
unidic-lite dictionary. Python picks the compiled module that matches the machine.

    uv run python tools/build.py
"""

import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "yomitsuke"
BUILD = ROOT / "build"
DIST = ROOT / "dist"
WHEELS = BUILD / "wheels"
ADDON = BUILD / "yomitsuke"
VENDOR = ADDON / "vendor"

FUGASHI = "1.5.2"
PLATFORMS = [
    "macosx_11_0_universal2",  # takes the 3.13 (10.13) and 3.14 (10.15) universal wheels
    "win_amd64",
    "manylinux2014_x86_64",
    "manylinux2014_aarch64",
]
# Anki 26.09 runs Python 3.13; 3.14 is bundled too, so a newer Anki on it works from day one.
# Python picks the compiled module named for its own version.
PYTHONS = ["3.13", "3.14"]
MIN_POINT_VERSION = 260900  # Anki 26.09: yomitsuke follows the newest Anki, no back-support

FUGASHI_INIT = """\
# Written by yomitsuke's build: the per-platform wheels each ship their own version of this file.
import os as _os
import sys as _sys

if _sys.platform == "win32":
    _libs = _os.path.join(_os.path.dirname(__file__), _os.pardir, "fugashi.libs")
    if _os.path.isdir(_libs):
        _os.add_dll_directory(_os.path.abspath(_libs))

from .fugashi import *
"""


def download_fugashi() -> None:
    WHEELS.mkdir(parents=True, exist_ok=True)
    for python in PYTHONS:
        for platform in PLATFORMS:  # pip skips wheels it already has
            subprocess.run(
                ["uvx", "--from", "pip", "pip", "download", f"fugashi=={FUGASHI}", "--no-deps",
                 "--only-binary=:all:", "--platform", platform, "--python-version", python,
                 "--implementation", "cp", "--abi", f"cp{python.replace('.', '')}",
                 "--dest", str(WHEELS), "--quiet"],
                check=True,
            )


def unidic_lite() -> Path:
    import unidic_lite

    return Path(unidic_lite.__file__).parent


def unidic_lite_licence(name: str) -> Path:
    from importlib.metadata import distribution

    dist = distribution("unidic-lite")
    return Path(dist.locate_file(next(f for f in dist.files if f.name == name and "licenses" in str(f))))


def main() -> None:
    shutil.rmtree(ADDON, ignore_errors=True)
    shutil.copytree(SRC, ADDON, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "meta.json", "user_files"))
    download_fugashi()
    VENDOR.mkdir()
    for wheel in sorted(WHEELS.glob("fugashi-*.whl")):
        with zipfile.ZipFile(wheel) as z:
            z.extractall(VENDOR)
    # Each wheel has its own fugashi/__init__.py; the Windows one finds MeCab's DLL with a call
    # that only exists on Windows. One file that works everywhere replaces them.
    (VENDOR / "fugashi" / "__init__.py").write_text(FUGASHI_INIT)
    shutil.copytree(unidic_lite(), VENDOR / "unidic_lite", ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("LICENSE", "LICENSE.unidic"):  # unidic-lite's own licences, kept beside its package
        shutil.copy(unidic_lite_licence(name), VENDOR / "unidic_lite" / name)
    shutil.copy(ROOT / "LICENSE", ADDON / "LICENSE")
    shutil.copy(ROOT / "NOTICE.md", ADDON / "NOTICE.md")
    (ADDON / "manifest.json").write_text(
        json.dumps({"package": "yomitsuke", "name": "yomitsuke", "min_point_version": MIN_POINT_VERSION}, indent=2)
    )

    DIST.mkdir(exist_ok=True)
    out = DIST / "yomitsuke.ankiaddon"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path in sorted(ADDON.rglob("*")):
            if path.is_file():
                z.write(path, path.relative_to(ADDON))  # contents only, no top folder
    print(f"{out.relative_to(ROOT)}: {out.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    sys.exit(main())
