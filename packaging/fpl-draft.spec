from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


project_root = Path(SPECPATH).parent
frontend_dist = project_root / "frontend" / "dist"
if not frontend_dist.exists():
    raise SystemExit("frontend/dist is missing. Run: cd frontend && npm run build")

playwright_datas = collect_data_files("playwright")
playwright_hiddenimports = collect_submodules("playwright")

a = Analysis(
    [str(project_root / "webapi" / "launcher.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        (str(frontend_dist), "frontend/dist"),
        *playwright_datas,
    ],
    hiddenimports=["webapi.app", *playwright_hiddenimports],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="fpl-draft",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="fpl-draft",
)
