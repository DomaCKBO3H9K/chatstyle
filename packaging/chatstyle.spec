import importlib.util
import os

root = os.path.dirname(os.path.abspath(SPECPATH))

core_spec = importlib.util.find_spec("chatstyle._core")
if core_spec is None or core_spec.origin is None:
    raise SystemExit("chatstyle._core not found: run pip install -e .[dev] first")

# По умолчанию один файл (--onefile) для релиза; CHATSTYLE_ONEDIR=1 даёт папку для отладки.
onedir = os.environ.get("CHATSTYLE_ONEDIR") == "1"
icon_path = os.path.join(root, "packaging", "chatstyle.ico")
version_path = os.path.join(root, "build", "version_info.txt")  # создаёт build_exe.ps1

# rich.pretty условно импортирует IPython, а тот тянет numpy, pandas, matplotlib и всё окружение
# разработчика; в exe этого быть не должно (размер не должен зависеть от машины сборки).
EXCLUDES = [
    "IPython",
    "ipykernel",
    "jupyter_client",
    "matplotlib",
    "numpy",
    "pandas",
    "scipy",
    "PIL",
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
    "tkinter",
    "pytest",
    "_pytest",
    "trio",
    "openpyxl",
    "sqlalchemy",
    "sympy",
    "experiments",
]

a = Analysis(
    scripts=[os.path.join(root, "python", "chatstyle", "__main__.py")],
    pathex=[os.path.join(root, "python")],
    hiddenimports=["chatstyle", "chatstyle._core"],
    datas=[(os.path.join(root, "python", "chatstyle", "resources"), "chatstyle/resources")],
    binaries=[(core_spec.origin, "chatstyle")],
    excludes=EXCLUDES,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    *([] if onedir else [a.binaries, a.datas]),
    exclude_binaries=onedir,
    name="chatstyle",
    console=True,
    upx=False,
    icon=icon_path if os.path.exists(icon_path) else None,
    version=version_path if os.path.exists(version_path) else None,
)

if onedir:
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="chatstyle")
