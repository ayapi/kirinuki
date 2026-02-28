# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

sqlite_vec_datas, sqlite_vec_binaries, sqlite_vec_hiddenimports = collect_all("sqlite_vec")

a = Analysis(
    ["src/kirinuki/cli/main.py"],
    pathex=["src"],
    binaries=sqlite_vec_binaries,
    datas=sqlite_vec_datas,
    hiddenimports=[
        "pydantic",
        "pydantic_settings",
        "sqlite_vec",
        *sqlite_vec_hiddenimports,
    ],
    hookspath=["hooks"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="kirinuki",
    debug=False,
    strip=False,
    upx=True,
    console=True,
)
