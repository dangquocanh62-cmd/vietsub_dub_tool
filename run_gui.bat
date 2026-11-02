@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [LOI] Khong tim thay Python. Hay chay install.bat truoc.
    pause
    exit /b 1
)

REM Kiem tra thu vien da cai chua, neu chua thi nhac chay install.bat
python -c "import edge_tts, pydub, srt, tqdm" >nul 2>nul
if %errorlevel% neq 0 (
    echo [LOI] Chua cai du thu vien. Hay bam dup "install.bat" truoc, sau do moi chay lai file nay.
    pause
    exit /b 1
)

python gui.py
if %errorlevel% neq 0 (
    echo.
    echo Co loi xay ra khi chay giao dien. Xem chi tiet loi phia tren.
    pause
)
