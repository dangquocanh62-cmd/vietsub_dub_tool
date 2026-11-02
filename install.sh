#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo "============================================"
echo "  CÀI ĐẶT TOOL VIETSUB + LỒNG TIẾNG AI"
echo "============================================"
echo

# --- Kiểm tra Python ---
if ! command -v python3 &> /dev/null; then
    echo "[LỖI] Không tìm thấy python3."
    echo "macOS:  brew install python"
    echo "Linux:  sudo apt install python3 python3-pip python3-venv python3-tk"
    exit 1
fi
echo "[OK] Đã tìm thấy Python: $(python3 --version)"

# --- Tạo môi trường ảo (venv) riêng cho tool, tránh xung đột/lỗi với Python hệ thống ---
echo
echo "Đang tạo môi trường Python riêng cho tool (thư mục .venv)..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv || {
        echo "[LỖI] Không tạo được venv. Thử cài: sudo apt install python3-venv";
        exit 1;
    }
fi
echo "[OK] Đã có môi trường riêng tại .venv/"

# --- Cài thư viện Python vào venv ---
echo
echo "Đang cài các thư viện Python cần thiết (có thể mất vài phút)..."
./.venv/bin/python3 -m pip install --upgrade pip
./.venv/bin/python3 -m pip install -r requirements.txt
echo "[OK] Đã cài xong thư viện Python."

# --- Kiểm tra / cài ffmpeg (cài vào hệ thống, không phải venv) ---
echo
if ! command -v ffmpeg &> /dev/null; then
    echo "Chưa có ffmpeg, đang thử cài tự động..."
    if command -v brew &> /dev/null; then
        brew install ffmpeg
    elif command -v apt &> /dev/null; then
        sudo apt update && sudo apt install -y ffmpeg
    else
        echo "[CẢNH BÁO] Không tìm được trình quản lý gói phù hợp."
        echo "Hãy tự cài ffmpeg: https://ffmpeg.org/download.html"
    fi
else
    echo "[OK] Đã có ffmpeg."
fi

# --- Kiểm tra tkinter (cho GUI) ---
echo
if ! python3 -c "import tkinter" &> /dev/null; then
    echo "[CẢNH BÁO] Chưa có tkinter (cần cho giao diện đồ hoạ)."
    if command -v apt &> /dev/null; then
        echo "Đang cài đặt python3-tk..."
        sudo apt install -y python3-tk
    else
        echo "macOS: tkinter thường có sẵn theo Python từ python.org."
    fi
else
    echo "[OK] Đã có tkinter."
fi

echo
echo "============================================"
echo "  CÀI ĐẶT XONG!"
echo "============================================"
echo "Nhớ lấy Gemini API key (miễn phí) tại https://aistudio.google.com/apikey"
echo "để dùng được bước dịch phụ đề — xem hướng dẫn trong README.md mục 1."
echo
echo "Chạy GUI bằng lệnh:   ./run_gui.sh"
echo "Hoặc dùng dòng lệnh:  ./.venv/bin/python3 dub_tool.py --help"
echo
