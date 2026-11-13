# PyInstaller build recipe:  pyinstaller dabireh.spec
# Produces dist/Dabireh/Dabireh.exe (folder build, no console window).
# NOTE: prepared for a later phase; it has not been built or tested on Windows yet.

a = Analysis(
    ["main.py"],
    pathex=["."],
    datas=[("resources", "resources")],
    hiddenimports=["PySide6.QtSvg", "PySide6.QtPrintSupport", "docx", "lxml"],
    excludes=["tkinter", "pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Dabireh", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="Dabireh")
