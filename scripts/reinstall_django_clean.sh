#!/usr/bin/env bash
# Полная переустановка Django из одного wheel — устраняет смешанную установку
# (типичная ошибка: ImportError: cannot import name 'PickleSerializer' из base).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -f "$ROOT/env/bin/pip" ]]; then
  PIP="$ROOT/env/bin/pip"
  PY="$ROOT/env/bin/python"
else
  PIP="pip"
  PY="python3"
fi
VER="${1:-$("$PY" -c "import importlib.metadata as m; print(m.version('Django'))" 2>/dev/null || echo 6.0.2)}"
echo "Reinstalling Django==$VER via $PIP"
"$PIP" uninstall -y Django 2>/dev/null || true
"$PIP" install "Django==$VER"
"$PY" -c "import django; print('Django', django.get_version(), 'OK')"
