import importlib.util
import os

# Графический chatstyle-gui.exe: тот же код, что в консольном exe, но без консольного окна
# (console=False) и с окном на pywebview (WebView2). По умолчанию один файл; CHATSTYLE_ONEDIR=1 даёт папку для отладки.
root = os.path.dirname(os.path.abspath(SPECPATH))

core_spec = importlib.util.find_spec("chatstyle._core")
if core_spec is None or core_spec.origin is None:
    raise SystemExit("chatstyle._core not found: run pip install -e .[dev] first")

onedir = os.environ.get("CHATSTYLE_ONEDIR") == "1"
icon_path = os.path.join(root, "python", "chatstyle", "resources", "chatstyle.ico")
version_path = os.path.join(root, "build", "version_info.txt")  # создаёт build_exe.ps1

# Как в консольном spec: окружение разработчика в exe не попадает. Окно рисует WebView2, tkinter не нужен.
EXCLUDES = [
    "tkinter",
    "_tkinter",
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
    "pytest",
    "_pytest",
    "trio",
    "openpyxl",
    "sqlalchemy",
    "sympy",
    "experiments",
]

a = Analysis(
    scripts=[os.path.join(root, "python", "chatstyle", "gui", "__main__.py")],
    pathex=[os.path.join(root, "python")],
    hiddenimports=[
        "chatstyle",
        "chatstyle._core",
        "chatstyle.gui",
        "chatstyle.gui.app",
        "chatstyle.gui.model",
        "chatstyle.gui.api",
        "webview",
        "webview.platforms.edgechromium",
        "webview.platforms.winforms",
        "clr",
        "chatstyle.securestore",
        "chatstyle.collectors.telegram_login",
        "cryptography.hazmat.primitives.ciphers.aead",
    ],
    datas=[
        (os.path.join(root, "python", "chatstyle", "resources"), "chatstyle/resources"),
        (os.path.join(root, "python", "chatstyle", "gui", "web"), "chatstyle/gui/web"),
    ],
    binaries=[(core_spec.origin, "chatstyle")],
    excludes=EXCLUDES,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    *([] if onedir else [a.binaries, a.datas]),
    exclude_binaries=onedir,
    name="chatstyle-gui",
    console=False,
    upx=False,
    icon=icon_path if os.path.exists(icon_path) else None,
    version=version_path if os.path.exists(version_path) else None,
)

if onedir:
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="chatstyle-gui")
