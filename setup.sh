#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT_DIR"

if [ -n "${EM_RAG_PYTHON:-}" ]; then
  exec "$EM_RAG_PYTHON" -m src.bootstrap_launcher "$@"
fi

for PYTHON in python3 python3.11 python; do
  if command -v "$PYTHON" >/dev/null 2>&1; then
    exec "$PYTHON" -m src.bootstrap_launcher "$@"
  fi
done

echo "未找到可用的 Python，请先安装 Python 3.11+。"
exit 1
