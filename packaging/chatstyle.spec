import importlib.util
import os

root = os.path.dirname(os.path.abspath(SPECPATH))

core_spec = importlib.util.find_spec("chatstyle._core")
if core_spec is None or core_spec.origin is None:
    raise SystemExit("chatstyle._core not found: run pip install -e .[dev] first")

a = Analysis(
    scripts=[os.path.join(root, "python", "chatstyle", "__main__.py")],
    pathex=[os.path.join(root, "python")],
    hiddenimports=["chatstyle", "chatstyle._core"],
    datas=[(os.path.join(root, "python", "chatstyle", "resources"), "chatstyle/resources")],
    binaries=[(core_spec.origin, "chatstyle")],
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="chatstyle",
    console=True,
    upx=False,
)
