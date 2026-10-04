#!/usr/bin/env bash
# Установка chatstyle в Linux: отдельное виртуальное окружение и команды в ~/.local/bin.
# Запуск из распакованной папки: ./install.sh
set -euo pipefail

cd "$(dirname "$0")"
PREFIX="${CHATSTYLE_PREFIX:-$HOME/.local/share/chatstyle-app}"
BIN="${CHATSTYLE_BIN:-$HOME/.local/bin}"

need() {
    command -v "$1" >/dev/null 2>&1 || { echo "Не найдено: $1. $2" >&2; exit 1; }
}
need python3 "Установите python3 (3.11 или новее)."
need cmake "Установите cmake (3.20 или новее)."
need g++ "Установите компилятор: sudo apt install build-essential"

python3 - <<'EOF'
import sys
if sys.version_info < (3, 11):
    sys.exit("Нужен Python 3.11 или новее, найден %d.%d" % sys.version_info[:2])
EOF
python3 -c "import venv, sysconfig, os; assert os.path.exists(sysconfig.get_paths()['include'] + '/Python.h')" 2>/dev/null \
    || { echo "Нет заголовков Python: sudo apt install python3-dev python3-venv" >&2; exit 1; }

echo "Создаю окружение в $PREFIX"
python3 -m venv "$PREFIX"
"$PREFIX/bin/python" -m pip install --upgrade pip
echo "Собираю ядро и ставлю chatstyle (с частями речи)"
"$PREFIX/bin/python" -m pip install ".[morph]"

mkdir -p "$BIN"
ln -sf "$PREFIX/bin/chatstyle" "$BIN/chatstyle"
ln -sf "$PREFIX/bin/chatstyle-gui" "$BIN/chatstyle-gui"

"$PREFIX/bin/chatstyle" --help >/dev/null
echo
echo "Готово. Команды: chatstyle, chatstyle-gui (в $BIN)."
case ":$PATH:" in
    *":$BIN:"*) ;;
    *) echo "Добавьте $BIN в PATH: export PATH=\"$BIN:\$PATH\"" ;;
esac
echo "Для окна (chatstyle-gui) нужен GTK: sudo apt install python3-gi gir1.2-webkit2-4.1"
echo "  или Qt: $PREFIX/bin/python -m pip install 'pywebview[qt]'"
echo "Удаление: rm -rf $PREFIX $BIN/chatstyle $BIN/chatstyle-gui"
