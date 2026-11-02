#!/usr/bin/env bash
cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python3" ]; then
    echo "[LỖI] Chưa cài đặt. Hãy chạy ./install.sh trước."
    exit 1
fi

if ! ./.venv/bin/python3 -c "import edge_tts, pydub, srt, tqdm" &> /dev/null; then
    echo "[LỖI] Chưa cài đủ thư viện. Hãy chạy ./install.sh trước."
    exit 1
fi

./.venv/bin/python3 gui.py
