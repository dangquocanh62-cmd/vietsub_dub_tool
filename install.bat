@echo off
chcp 65001 >nul
echo ============================================
echo   CAI DAT TOOL VIETSUB + LONG TIENG AI
echo ============================================
echo.

REM --- Kiem tra Python ---
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [LOI] Khong tim thay Python.
    echo Hay cai Python tai https://www.python.org/downloads/
    echo Luu y: luc cai nho TICK CHON "Add python.exe to PATH"
    echo.
    pause
    exit /b 1
)
echo [OK] Da tim thay Python.
python --version

REM --- Cai thu vien Python ---
echo.
echo Dang cai cac thu vien Python can thiet (co the mat vai phut)...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [LOI] Cai thu vien Python that bai. Xem loi phia tren.
    pause
    exit /b 1
)
echo [OK] Da cai xong thu vien Python.

REM --- Kiem tra / cai ffmpeg ---
echo.
where ffmpeg >nul 2>nul
if %errorlevel% neq 0 (
    echo Chua co ffmpeg, dang thu cai tu dong bang winget...
    where winget >nul 2>nul
    if %errorlevel% equ 0 (
        winget install --id Gyan.FFmpeg -e --silent --accept-package-agreements --accept-source-agreements
    ) else (
        echo [CANH BAO] Khong tim thay winget de tu cai ffmpeg.
        echo Hay tu tai va cai ffmpeg tai: https://ffmpeg.org/download.html
        echo Sau khi cai, nho them duong dan ffmpeg vao bien moi truong PATH.
    )
) else (
    echo [OK] Da co ffmpeg.
)

echo.
echo ============================================
echo   CAI DAT XONG!
echo ============================================
echo Neu vua cai them ffmpeg, hay DONG cua so nay
echo va MO LAI (hoac khoi dong lai may) de PATH duoc cap nhat.
echo.
echo Nho lay Gemini API key (mien phi) tai https://aistudio.google.com/apikey
echo de dung duoc buoc dich phu de - xem huong dan trong README.md muc 1.
echo.
echo Bam dup vao file "run_gui.bat" de mo tool.
echo.
pause
