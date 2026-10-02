import importlib.util
import os

root = os.path.dirname(os.path.abspath(SPECPATH))

core_spec = importlib.util.find_spec("chatstyle._core")
if core_spec is None or core_spec.origin is None:
    raise SystemExit("chatstyle._core not found: run pip install -e .[dev] first")

# По умолчанию один файл (--onefile) для релиза; CHATSTYLE_ONEDIR=1 даёт папку для отладки.
onedir = os.environ.get("CHATSTYLE_ONEDIR") == "1"
icon_path = os.path.join(root, "python", "chatstyle", "resources", "chatstyle.ico")
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

# Части речи (pymorphy3): build_exe.ps1 кладёт их в exe по умолчанию (CHATSTYLE_WITH_MORPH=1),
# с ключом -NoMorph переменная не задаётся, и они исключаются (меньше примерно на 9 МБ).
MORPH_MODULES = ["pymorphy3", "pymorphy3_dicts_ru", "dawg2_python"]
WITH_MORPH = os.environ.get("CHATSTYLE_WITH_MORPH") == "1"
if WITH_MORPH:
    from PyInstaller.utils.hooks import collect_data_files

    MORPH_DATAS = collect_data_files("pymorphy3_dicts_ru") + collect_data_files("pymorphy3")
else:
    EXCLUDES += MORPH_MODULES
    MORPH_DATAS = []

a = Analysis(
    scripts=[os.path.join(root, "python", "chatstyle", "__main__.py")],
    pathex=[os.path.join(root, "python")],
    hiddenimports=["chatstyle", "chatstyle._core"] + (MORPH_MODULES if WITH_MORPH else []),
    datas=[(os.path.join(root, "python", "chatstyle", "resources"), "chatstyle/resources")]
    + MORPH_DATAS,
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
