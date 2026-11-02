#!/usr/bin/env python3
"""
GUI cho Tool Vietsub + Lồng tiếng AI (CustomTkinter Version).
Chạy: python gui.py
"""

import os
import re
import sys
import json
import platform
import subprocess
import threading
import tempfile
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, colorchooser
import customtkinter as ctk
from PIL import Image, ImageTk
from voices import VOICES

# windnd can cause PyEval_RestoreThread GIL crash when overriding CustomTkinter's WNDPROC
HAS_WINDND = False

try:
    import srt
    HAS_SRT = True
except Exception:
    HAS_SRT = False

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DUB_TOOL = os.path.join(SCRIPT_DIR, "dub_tool.py")
PROGRESS_RE = re.compile(r"(\d+)%(?:\||(?:\s*\[))")

ctk.set_appearance_mode("System")
try:
    theme_path = os.path.join(SCRIPT_DIR, "theme_custom.json")
    if os.path.exists(theme_path):
        ctk.set_default_color_theme(theme_path)
    else:
        ctk.set_default_color_theme("blue")
except Exception as e:
    print(f"Warning: Failed to load custom theme ({e}), falling back to blue.")
    ctk.set_default_color_theme("blue")

# ── Hằng Số Màu Ngữ Nghĩa & Typography & Widget ──────────────────────────────
COLOR_SUCCESS = "#22C55E"
COLOR_SUCCESS_BG = "#14532D"
COLOR_WARNING = "#EAB308"
COLOR_WARNING_BG = "#422006"
COLOR_DANGER = "#DC2626"
COLOR_DANGER_HOVER = "#B91C1C"
COLOR_DANGER_BG = "#450A0A"
COLOR_ACCENT = "#3B82F6"
COLOR_ACCENT_HOVER = "#2563EB"
COLOR_TEXT_MUTED = "#A3A3A3"
COLOR_TEXT_DIM = "#6B7280"
COLOR_BORDER = "#333333"
COLOR_CARD_BG = "#232323"

FONT_FAMILY = "Be Vietnam Pro"

def _load_embedded_fonts():
    """Tự động nạp các file font tiếng Việt từ thư mục assets/fonts vào Windows runtime."""
    if platform.system() == "Windows":
        try:
            import ctypes
            fonts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts")
            if os.path.isdir(fonts_dir):
                for f in os.listdir(fonts_dir):
                    if f.lower().endswith((".ttf", ".otf")):
                        full_p = os.path.join(fonts_dir, f)
                        ctypes.windll.gdi32.AddFontResourceExW(full_p, 0x10, 0)
        except Exception:
            pass

_load_embedded_fonts()

# Đặt font Be Vietnam Pro làm mặc định cho toàn bộ widget CustomTkinter
try:
    ctk.ThemeManager.theme["CTkFont"]["family"] = FONT_FAMILY
except Exception:
    pass

FONT_HEADING = lambda: ctk.CTkFont(family=FONT_FAMILY, size=17, weight="bold")
FONT_SUBHEADING = lambda: ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold")
FONT_LABEL = lambda: ctk.CTkFont(family=FONT_FAMILY, size=13)
FONT_CAPTION = lambda: ctk.CTkFont(family=FONT_FAMILY, size=11)

INPUT_HEIGHT = 32

OUTLINE_BTN = {
    "fg_color": "transparent",
    "border_width": 1,
    "border_color": "#555555",
    "hover_color": "#2A2A2A",
    "text_color": "#E5E7EB",
}

PRIMARY_BTN = {
    "fg_color": COLOR_ACCENT,
    "hover_color": COLOR_ACCENT_HOVER,
    "text_color": "#FFFFFF",
}

DANGER_BTN = {
    "fg_color": COLOR_DANGER,
    "hover_color": COLOR_DANGER_HOVER,
    "text_color": "#FFFFFF",
}


def open_with_default_app(path):
    """Mở file bằng ứng dụng mặc định của hệ điều hành."""
    system = platform.system()
    try:
        if system == "Windows":
            os.startfile(path)
        elif system == "Darwin":
            subprocess.run(["open", path])
        else:
            subprocess.run(["xdg-open", path])
    except Exception as e:
        messagebox.showerror("Lỗi", f"Không mở được file tự động.\nHãy tự mở file này:\n{path}\n\n{e}")


def play_audio_file(path):
    """Phát file audio bằng thư viện có sẵn (playsound/simpleaudio/winsound) hoặc open_with_default_app."""
    try:
        import playsound
        playsound.playsound(path)
        return
    except Exception:
        pass

    try:
        import simpleaudio as sa
        wave_obj = sa.WaveObject.from_wave_file(path)
        play_obj = wave_obj.play()
        play_obj.wait_done()
        return
    except Exception:
        pass

    if platform.system() == "Windows":
        try:
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME)
            return
        except Exception:
            pass

    open_with_default_app(path)


def is_vietnamese_content(filepath_or_text) -> bool:
    """Kiểm tra xem nội dung văn bản hoặc file có chứa các ký tự tiếng Việt có dấu hay không."""
    try:
        if isinstance(filepath_or_text, str) and os.path.isfile(filepath_or_text):
            with open(filepath_or_text, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read(8000)
        else:
            text = str(filepath_or_text)
        vi_chars = set("àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ"
                       "ÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴĐ")
        return sum(1 for c in text if c in vi_chars) >= 4
    except Exception:
        return False


class SettingsDialog(ctk.CTkToplevel):
    """Cửa sổ Modal Cài đặt API (Groq, Gemini, HuggingFace) riêng biệt."""
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("⚙ Cài đặt API & Dịch thuật AI")
        self.geometry("640x580")
        self.minsize(560, 480)
        self.grab_set()

        # Tiêu đề Header
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=20, pady=(16, 8))
        ctk.CTkLabel(hdr, text="⚙ Cài Đặt Khóa API & Model AI", font=FONT_HEADING()).pack(side="left")

        # Scrollable Frame chứa các nhóm cài đặt
        sf = ctk.CTkScrollableFrame(self, fg_color="transparent")
        sf.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        # ── 1. Groq Cloud ─────────────────────────────────────────────────────
        card_groq = ctk.CTkFrame(sf, fg_color=COLOR_CARD_BG, border_width=1, border_color=COLOR_BORDER, corner_radius=8)
        card_groq.pack(fill="x", pady=6)
        ctk.CTkLabel(card_groq, text="1. Groq Cloud (Dịch siêu tốc ~500 tok/s - Khuyên Dùng)", font=FONT_SUBHEADING(), text_color=COLOR_ACCENT).pack(anchor="w", padx=14, pady=(10, 6))

        r_g1 = ctk.CTkFrame(card_groq, fg_color="transparent")
        r_g1.pack(fill="x", padx=14, pady=3)
        ctk.CTkLabel(r_g1, text="Groq API Key:", font=FONT_LABEL(), width=130, anchor="w").pack(side="left")
        self.groq_key_entry = ctk.CTkEntry(r_g1, textvariable=self.parent.groq_api_key, show="•", height=INPUT_HEIGHT)
        self.groq_key_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._groq_show = False
        def _toggle_groq_show():
            self._groq_show = not self._groq_show
            self.groq_key_entry.configure(show="" if self._groq_show else "•")
        ctk.CTkButton(r_g1, text="👁", width=36, height=INPUT_HEIGHT, command=_toggle_groq_show, **OUTLINE_BTN).pack(side="left")

        r_g2 = ctk.CTkFrame(card_groq, fg_color="transparent")
        r_g2.pack(fill="x", padx=14, pady=4)
        ctk.CTkLabel(r_g2, text="Groq Model:", font=FONT_LABEL(), width=130, anchor="w").pack(side="left")
        ctk.CTkComboBox(
            r_g2, variable=self.parent.groq_model,
            values=["qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b"],
            height=INPUT_HEIGHT
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        btn_chk_groq = ctk.CTkButton(
            r_g2, text="🔍 Kiểm tra", width=95, height=INPUT_HEIGHT,
            command=lambda: self.parent.run_check_quota(btn_chk_groq), **OUTLINE_BTN
        )
        btn_chk_groq.pack(side="left")

        ctk.CTkLabel(
            card_groq, text="💡 Lấy API key miễn phí tại: https://console.groq.com/keys",
            text_color=COLOR_TEXT_MUTED, font=FONT_CAPTION()
        ).pack(anchor="w", padx=14, pady=(2, 10))

        # ── 2. Google Gemini API ──────────────────────────────────────────────
        card_gemini = ctk.CTkFrame(sf, fg_color=COLOR_CARD_BG, border_width=1, border_color=COLOR_BORDER, corner_radius=8)
        card_gemini.pack(fill="x", pady=6)
        ctk.CTkLabel(card_gemini, text="2. Google Gemini API", font=FONT_SUBHEADING()).pack(anchor="w", padx=14, pady=(10, 6))

        r_gm1 = ctk.CTkFrame(card_gemini, fg_color="transparent")
        r_gm1.pack(fill="x", padx=14, pady=3)
        ctk.CTkLabel(r_gm1, text="Gemini API Key:", font=FONT_LABEL(), width=130, anchor="w").pack(side="left")
        self.gemini_key_entry = ctk.CTkEntry(r_gm1, textvariable=self.parent.gemini_api_key, show="•", height=INPUT_HEIGHT)
        self.gemini_key_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._gemini_show = False
        def _toggle_gemini_show():
            self._gemini_show = not self._gemini_show
            self.gemini_key_entry.configure(show="" if self._gemini_show else "•")
        ctk.CTkButton(r_gm1, text="👁", width=36, height=INPUT_HEIGHT, command=_toggle_gemini_show, **OUTLINE_BTN).pack(side="left")

        r_gm2 = ctk.CTkFrame(card_gemini, fg_color="transparent")
        r_gm2.pack(fill="x", padx=14, pady=4)
        ctk.CTkLabel(r_gm2, text="Gemini Model:", font=FONT_LABEL(), width=130, anchor="w").pack(side="left")
        ctk.CTkComboBox(
            r_gm2, variable=self.parent.gemini_model,
            values=["gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-flash-latest"],
            height=INPUT_HEIGHT
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        btn_chk_gemini = ctk.CTkButton(
            r_gm2, text="🔍 Kiểm tra", width=95, height=INPUT_HEIGHT,
            command=lambda: self.parent.run_check_quota(btn_chk_gemini), **OUTLINE_BTN
        )
        btn_chk_gemini.pack(side="left")

        ctk.CTkLabel(
            card_gemini, text="💡 Lấy API key miễn phí tại: https://aistudio.google.com/apikey",
            text_color=COLOR_TEXT_MUTED, font=FONT_CAPTION()
        ).pack(anchor="w", padx=14, pady=(2, 10))

        # ── 3. HuggingFace Token (Diarization) ─────────────────────────────────
        card_hf = ctk.CTkFrame(sf, fg_color=COLOR_CARD_BG, border_width=1, border_color=COLOR_BORDER, corner_radius=8)
        card_hf.pack(fill="x", pady=6)
        ctk.CTkLabel(card_hf, text="3. HuggingFace Token (Nhận diện & phân vai nhân vật)", font=FONT_SUBHEADING()).pack(anchor="w", padx=14, pady=(10, 6))

        r_hf = ctk.CTkFrame(card_hf, fg_color="transparent")
        r_hf.pack(fill="x", padx=14, pady=3)
        ctk.CTkLabel(r_hf, text="HF Token:", font=FONT_LABEL(), width=130, anchor="w").pack(side="left")
        self.hf_entry = ctk.CTkEntry(r_hf, textvariable=self.parent.hf_token, show="•", height=INPUT_HEIGHT, placeholder_text="hf_...")
        self.hf_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._hf_show = False
        def _toggle_hf_show():
            self._hf_show = not self._hf_show
            self.hf_entry.configure(show="" if self._hf_show else "•")
        ctk.CTkButton(r_hf, text="👁", width=36, height=INPUT_HEIGHT, command=_toggle_hf_show, **OUTLINE_BTN).pack(side="left")

        ctk.CTkLabel(
            card_hf, text="💡 Dùng để tải model pyannote/speaker-diarization tại: huggingface.co/settings/tokens",
            text_color=COLOR_TEXT_MUTED, font=FONT_CAPTION()
        ).pack(anchor="w", padx=14, pady=(2, 10))

        # Bottom row
        bottom_row = ctk.CTkFrame(self, fg_color="transparent")
        bottom_row.pack(fill="x", padx=20, pady=(6, 16))

        btn_save = ctk.CTkButton(
            bottom_row, text="💾 Lưu tất cả cài đặt",
            command=self._save_and_close, height=38,
            **PRIMARY_BTN, font=ctk.CTkFont(size=13, weight="bold")
        )
        btn_save.pack(side="right", padx=(8, 0))

        btn_close = ctk.CTkButton(
            bottom_row, text="Đóng",
            command=self.destroy, height=38,
            width=90, **OUTLINE_BTN
        )
        btn_close.pack(side="right")

    def _save_and_close(self):
        self.parent.save_api_key()
        if self.parent.hf_token.get().strip():
            self.parent.save_hf_token()
        if hasattr(self.parent, "_update_ai_status_banner"):
            self.parent._update_ai_status_banner()
        messagebox.showinfo("Đã lưu", "Đã lưu toàn bộ cài đặt API thành công!")
        self.destroy()


class PhoneShareDialog(ctk.CTkToplevel):
    """Cửa sổ Modal hiển thị mã QR để điện thoại quét và tải video qua mạng Wi-Fi nội bộ."""
    def __init__(self, parent, video_path: str):
        super().__init__(parent)
        self.parent = parent
        self.video_path = video_path
        self.title("📱 Quét Mã Tải Video Về Điện Thoại")
        self.geometry("450x640")
        self.minsize(420, 580)
        self.resizable(False, False)

        # Đảm bảo hiển thị ở trung tâm và trên cùng
        self.transient(parent)
        self.grab_set()

        # Khởi động máy chủ HTTP chia sẻ file
        from core.share_server import ShareServer, generate_qr_image
        self.server = ShareServer(video_path, port=0, on_activity=self._on_server_activity)
        self.url = self.server.start()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Header
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=20, pady=(16, 4))
        ctk.CTkLabel(hdr, text="📱 Chuyển Video Sang Điện Thoại", font=FONT_HEADING(), text_color="#34D399").pack(anchor="center")
        ctk.CTkLabel(
            hdr, text="Kết nối điện thoại cùng mạng Wi-Fi rồi quét mã bên dưới",
            font=FONT_CAPTION(), text_color=COLOR_TEXT_MUTED
        ).pack(anchor="center", pady=(2, 0))

        # Khung QR Code viền trắng nổi bật
        qr_container = ctk.CTkFrame(self, fg_color="#FFFFFF", corner_radius=16, border_width=3, border_color="#10B981")
        qr_container.pack(padx=20, pady=(10, 8))

        qr_img = generate_qr_image(self.url, size=240)
        self.qr_ctk_img = ctk.CTkImage(light_image=qr_img, dark_image=qr_img, size=(240, 240))
        lbl_qr = ctk.CTkLabel(qr_container, image=self.qr_ctk_img, text="")
        lbl_qr.pack(padx=14, pady=14)

        # Thông tin file video
        fname = os.path.basename(video_path)
        fsize_mb = os.path.getsize(video_path) / (1024 * 1024)
        info_str = f"🎬 {fname} ({fsize_mb:.1f} MB)"
        ctk.CTkLabel(
            self, text=info_str,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color="#E2E8F0"
        ).pack(padx=20, pady=(2, 6))

        # Hộp chứa liên kết URL trực tiếp
        url_box = ctk.CTkFrame(self, fg_color=COLOR_CARD_BG, border_width=1, border_color=COLOR_BORDER, corner_radius=8)
        url_box.pack(fill="x", padx=24, pady=(2, 8))

        self.url_entry = ctk.CTkEntry(url_box, height=INPUT_HEIGHT, border_width=0, fg_color="transparent", font=ctk.CTkFont(size=12))
        self.url_entry.insert(0, self.url)
        self.url_entry.configure(state="readonly")
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(8, 4), pady=4)

        btn_copy = ctk.CTkButton(
            url_box, text="📋 Sao chép", width=80, height=INPUT_HEIGHT - 6,
            command=self._copy_url, **PRIMARY_BTN, font=ctk.CTkFont(size=11, weight="bold")
        )
        btn_copy.pack(side="right", padx=(0, 6), pady=4)

        # Trạng thái kết nối thời gian thực
        self.status_lbl = ctk.CTkLabel(
            self, text="🟢 Đang chờ điện thoại quét mã...",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12), text_color="#34D399"
        )
        self.status_lbl.pack(pady=(2, 8))

        # Hướng dẫn nhanh cho người dùng
        tips_box = ctk.CTkFrame(self, fg_color="#1E293B", corner_radius=8, border_width=1, border_color="#334155")
        tips_box.pack(fill="x", padx=24, pady=(0, 12))
        tips_txt = (
            "💡 Mẹo: Mở Camera (iPhone) hoặc Zalo (Android) để quét.\n"
            "Tốc độ truyền mạng LAN 15-40 MB/s, không tốn 4G/Internet."
        )
        ctk.CTkLabel(
            tips_box, text=tips_txt, font=FONT_CAPTION(),
            text_color="#94A3B8", justify="left"
        ).pack(padx=10, pady=8)

        # Nút Đóng
        ctk.CTkButton(
            self, text="Đóng", command=self._on_close, width=130, height=32,
            **OUTLINE_BTN, font=ctk.CTkFont(size=12)
        ).pack(pady=(0, 12))

    def _on_server_activity(self, message: str):
        if hasattr(self, "status_lbl") and self.status_lbl.winfo_exists():
            self.after(0, lambda: self.status_lbl.configure(text=f"✨ {message}", text_color="#60A5FA"))

    def _copy_url(self):
        self.clipboard_clear()
        self.clipboard_append(self.url)
        self.status_lbl.configure(text="✔ Đã sao chép liên kết vào Clipboard!", text_color=COLOR_SUCCESS)

    def _on_close(self):
        if hasattr(self, "server") and self.server:
            self.server.stop()
            self.server = None
        self.destroy()


class DownloadVideoDialog(ctk.CTkToplevel):
    """Cửa sổ Modal tải video từ link (TikTok, Douyin, YouTube, Facebook...) loại bỏ Watermark."""
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("⬇ Tải Video Từ Link (Không Watermark / Logo)")
        self.geometry("640x480")
        self.minsize(580, 440)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._downloading = False
        self._downloaded_file = None

        # Header
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=20, pady=(16, 4))
        ctk.CTkLabel(
            hdr, text="⬇ Tải Video Từ Link Trực Tuyến",
            font=FONT_HEADING(), text_color="#60A5FA"
        ).pack(side="left")

        sub_hdr = ctk.CTkLabel(
            self,
            text="Hỗ trợ Douyin, TikTok, YouTube (Shorts), Facebook (Reels), Bilibili, Kuaishou...\nTự động bóc tách và loại bỏ sạch sẽ Watermark / Logo video Douyin & TikTok.",
            font=FONT_CAPTION(), text_color=COLOR_TEXT_MUTED, justify="left"
        )
        sub_hdr.pack(anchor="w", padx=20, pady=(0, 10))

        # Card nhập link
        card = ctk.CTkFrame(self, fg_color=COLOR_CARD_BG, border_width=1, border_color=COLOR_BORDER, corner_radius=8)
        card.pack(fill="x", padx=20, pady=4)

        r1 = ctk.CTkFrame(card, fg_color="transparent")
        r1.pack(fill="x", padx=14, pady=(12, 6))
        ctk.CTkLabel(r1, text="Đường link hoặc nội dung chia sẻ:", font=FONT_LABEL()).pack(side="left")

        btn_paste = ctk.CTkButton(
            r1, text="📋 Dán từ Clipboard", command=self._paste_clipboard,
            width=130, height=28, **OUTLINE_BTN, font=ctk.CTkFont(size=11)
        )
        btn_paste.pack(side="right")

        self.url_entry = ctk.CTkEntry(
            card,
            placeholder_text="Dán link hoặc nội dung chia sẻ (VD: https://v.douyin.com/... hoặc 7.12 复制打开抖音...)",
            height=36
        )
        self.url_entry.pack(fill="x", padx=14, pady=(0, 10))
        self.url_entry.focus_set()

        # Tuỳ chọn
        r2 = ctk.CTkFrame(card, fg_color="transparent")
        r2.pack(fill="x", padx=14, pady=(0, 10))

        self.var_no_wm = ctk.BooleanVar(value=True)
        chk_wm = ctk.CTkCheckBox(
            r2, text="Loại bỏ Watermark / Logo (Douyin, TikTok)",
            variable=self.var_no_wm, font=FONT_LABEL(),
            checkbox_width=20, checkbox_height=20
        )
        chk_wm.pack(side="left", padx=(0, 16))

        self.var_auto_load = ctk.BooleanVar(value=True)
        chk_load = ctk.CTkCheckBox(
            r2, text="Tự động nạp vào tool sau khi tải",
            variable=self.var_auto_load, font=FONT_LABEL(),
            checkbox_width=20, checkbox_height=20
        )
        chk_load.pack(side="left")

        # Thư mục lưu
        r_dest = ctk.CTkFrame(card, fg_color="transparent")
        r_dest.pack(fill="x", padx=14, pady=(0, 12))
        ctk.CTkLabel(r_dest, text="Lưu tại:", font=FONT_LABEL(), width=60, anchor="w").pack(side="left")

        default_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        self.var_out_dir = ctk.StringVar(value=default_dir)
        self.entry_dir = ctk.CTkEntry(r_dest, textvariable=self.var_out_dir, height=28)
        self.entry_dir.pack(side="left", fill="x", expand=True, padx=(0, 8))

        btn_browse_dir = ctk.CTkButton(
            r_dest, text="📂 Chọn", width=70, height=28, command=self._browse_dir, **OUTLINE_BTN
        )
        btn_browse_dir.pack(side="left")

        # Khung tiến trình
        prog_frame = ctk.CTkFrame(self, fg_color="transparent")
        prog_frame.pack(fill="x", padx=20, pady=(12, 4))

        self.prog_bar = ctk.CTkProgressBar(prog_frame, height=10)
        self.prog_bar.pack(fill="x", pady=(0, 6))
        self.prog_bar.set(0)

        self.status_lbl = ctk.CTkLabel(
            prog_frame,
            text="Sẵn sàng tải. Dán link và nhấn nút Bắt đầu tải bên dưới.",
            font=FONT_CAPTION(), text_color=COLOR_TEXT_MUTED, anchor="w"
        )
        self.status_lbl.pack(fill="x")

        # Bottom buttons
        self.btn_row = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_row.pack(fill="x", padx=20, pady=(16, 12), side="bottom")

        self.btn_start = ctk.CTkButton(
            self.btn_row, text="⬇ Bắt đầu tải video",
            command=self._start_download, height=38,
            **PRIMARY_BTN, font=ctk.CTkFont(size=13, weight="bold")
        )
        self.btn_start.pack(side="right", padx=(8, 0))

        self.btn_open_folder = ctk.CTkButton(
            self.btn_row, text="📁 Mở thư mục tải",
            command=self._open_target_folder, height=38,
            width=130, **OUTLINE_BTN, font=ctk.CTkFont(size=12)
        )

        self.btn_close = ctk.CTkButton(
            self.btn_row, text="Đóng",
            command=self.destroy, height=38,
            width=90, **OUTLINE_BTN
        )
        self.btn_close.pack(side="right")

    def _paste_clipboard(self):
        try:
            txt = self.clipboard_get()
            if txt:
                self.url_entry.delete(0, "end")
                self.url_entry.insert(0, txt.strip())
        except Exception:
            pass

    def _browse_dir(self):
        d = filedialog.askdirectory(initialdir=self.var_out_dir.get())
        if d:
            self.var_out_dir.set(d)

    def _open_target_folder(self):
        folder = self.var_out_dir.get().strip()
        if self._downloaded_file and os.path.exists(self._downloaded_file):
            folder = os.path.dirname(os.path.abspath(self._downloaded_file))
        if os.path.isdir(folder):
            open_with_default_app(folder)

    def _start_download(self):
        if self._downloading:
            return
        raw_text = self.url_entry.get().strip()
        if not raw_text:
            self.status_lbl.configure(text="⚠ Vui lòng dán link video trước khi tải!", text_color=COLOR_WARNING)
            return

        from core.downloader import extract_url, download_clean_video
        url = extract_url(raw_text)
        if not url:
            self.status_lbl.configure(text="⚠ Không tìm thấy đường link URL hợp lệ trong nội dung đã nhập!", text_color=COLOR_DANGER)
            return

        out_dir = self.var_out_dir.get().strip()
        if not out_dir or not os.path.isdir(out_dir):
            out_dir = os.path.join(os.path.expanduser("~"), "Downloads")
            os.makedirs(out_dir, exist_ok=True)

        self._downloading = True
        self.btn_start.configure(state="disabled", text="⏳ Đang tải...")
        self.prog_bar.set(0)
        self.status_lbl.configure(text="Đang kết nối tới máy chủ video...", text_color="#60A5FA")

        prefer_no_wm = self.var_no_wm.get()

        def _worker():
            def _progress_cb(msg, pct):
                def _update():
                    if hasattr(self, "status_lbl") and self.status_lbl.winfo_exists():
                        self.status_lbl.configure(text=msg, text_color="#60A5FA")
                        self.prog_bar.set(pct)
                self.after(0, _update)

            try:
                file_path, title = download_clean_video(
                    url,
                    output_dir=out_dir,
                    progress_cb=_progress_cb,
                    prefer_no_watermark=prefer_no_wm
                )

                def _success():
                    self._downloading = False
                    self._downloaded_file = file_path
                    self.prog_bar.set(1.0)
                    self.status_lbl.configure(text=f"✔ Đã tải xong: {title[:50]}", text_color=COLOR_SUCCESS)
                    self.btn_start.configure(state="normal", text="⬇ Tải video khác")
                    self.btn_open_folder.pack(side="left")

                    if self.var_auto_load.get() and hasattr(self.parent, "video_path"):
                        self.parent._current_preview_path = None
                        self.parent.video_path.set(file_path)
                        if hasattr(self.parent, "status_label"):
                            self.parent.status_label.configure(
                                text=f"✔ Đã nạp video từ link: {os.path.basename(file_path)}",
                                text_color=COLOR_SUCCESS
                            )
                self.after(0, _success)

            except Exception as e:
                err_msg = str(e)
                def _fail():
                    self._downloading = False
                    self.btn_start.configure(state="normal", text="⬇ Thử lại")
                    self.prog_bar.set(0)
                    self.status_lbl.configure(text=f"❌ Lỗi: {err_msg[:120]}", text_color=COLOR_DANGER)
                self.after(0, _fail)

        threading.Thread(target=_worker, daemon=True).start()


class DubToolGUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Vietsub & Dub AI Studio")
        self.geometry("1380x860")
        self.minsize(1180, 720)
        self._current_sub_index = 0

        # Trạng thái tiến trình
        self._job_running = False
        self._current_proc = None
        self._active_btn = None
        self._active_btn_orig_text = None
        self._run_buttons = []
        self._dot_anim_id = None
        self._last_completed_file = None

        # Hàng đợi đồng bộ thread an toàn tuyệt đối với Tkinter
        import queue
        self._ui_queue = queue.Queue()
        self._poll_ui_queue()

        # Nạp toàn bộ session & cài đặt đã lưu
        saved_settings = self._load_app_settings()

        # Khởi động ở trạng thái sạch (không nạp lại file cũ), chỉ lưu và áp dụng toàn bộ cấu hình cài đặt
        self.video_path = tk.StringVar(value="")
        self.job_output_dir = tk.StringVar(value="")
        self.srt_path = tk.StringVar(value="")
        self.orig_srt_path = tk.StringVar(value="")
        self.output_path = tk.StringVar(value="")
        self.voice = tk.StringVar(value=saved_settings.get("voice", "nu-hoaimy"))
        self.single_voice = tk.BooleanVar(value=saved_settings.get("single_voice", False))
        self.tts_engine = tk.StringVar(value=saved_settings.get("tts_engine", "edge"))
        self.capcut_rate = tk.DoubleVar(value=saved_settings.get("capcut_rate", 1.0))
        self.sub_source_mode = tk.StringVar(value=saved_settings.get("sub_source_mode", "whisper"))
        fps_init = saved_settings.get("ocr_fps", "1.5")
        if str(fps_init) in ["4.0", "4"]:
            fps_init = "1.5"
        self.ocr_fps = tk.StringVar(value=str(fps_init))
        self.crop_left = tk.StringVar(value=str(saved_settings.get("crop_left", "0.00")))
        self.crop_right = tk.StringVar(value=str(saved_settings.get("crop_right", "1.00")))
        self.whisper_model = tk.StringVar(value=saved_settings.get("whisper_model", "small"))
        self.enable_diarize = tk.BooleanVar(value=saved_settings.get("enable_diarize", False))
        self.hf_token = tk.StringVar(value=saved_settings.get("hf_token") or os.environ.get("HF_TOKEN", ""))
        self.keep_original = tk.StringVar(value=saved_settings.get("keep_original", "voiceover"))
        self.bg_volume = tk.DoubleVar(value=saved_settings.get("bg_volume", 0.15))
        self.dub_volume = tk.DoubleVar(value=saved_settings.get("dub_volume", 1.0))
        self.mask_original = tk.BooleanVar(value=saved_settings.get("mask_original", False))
        self.mask_style = tk.StringVar(value=saved_settings.get("mask_style", "box"))
        self.mask_top = tk.StringVar(value=saved_settings.get("mask_top", "0.75"))
        self.mask_bottom = tk.StringVar(value=saved_settings.get("mask_bottom", "0.97"))
        self.mask_blur = tk.StringVar(value=saved_settings.get("mask_blur", "25"))
        self.translate_engine = tk.StringVar(value=saved_settings.get("translate_engine", "gemini"))
        self.gemini_api_key = tk.StringVar(value=saved_settings.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY", ""))
        gemini_model_val = saved_settings.get("gemini_model", "gemini-3.6-flash")
        if gemini_model_val in ["gemini-2.5-flash", "gemini-pro-latest", "gemini-flash-latest"]:
            gemini_model_val = "gemini-3.6-flash"
        self.gemini_model = tk.StringVar(value=gemini_model_val)
        self.groq_api_key = tk.StringVar(value=saved_settings.get("groq_api_key") or os.environ.get("GROQ_API_KEY", ""))
        groq_model_val = saved_settings.get("groq_model", "qwen/qwen3.8-27b")
        if "llama" in groq_model_val.lower() or groq_model_val in ["qwen/qwen3.6-27b", "groq/compound"]:
            groq_model_val = "qwen/qwen3.8-27b"
        self.groq_model = tk.StringVar(value=groq_model_val)
        self.dubbed_video_path = tk.StringVar(value="")
        self.speaker_voice_vars = {}
        self._saved_speaker_voices = saved_settings.get("speaker_voices", {})
        self.font_name = tk.StringVar(value=saved_settings.get("font_name", "Arial"))
        self.font_size = tk.StringVar(value=str(saved_settings.get("font_size", "16")))
        self.font_color = tk.StringVar(value=saved_settings.get("font_color", "white"))
        self.outline_color = tk.StringVar(value=saved_settings.get("outline_color", "black"))
        self.outline_width = tk.StringVar(value=str(saved_settings.get("outline_width", "2")))
        self.sub_position = tk.StringVar(value=saved_settings.get("sub_position", "bottom"))
        self.sub_bold = tk.BooleanVar(value=saved_settings.get("sub_bold", False))
        self.use_free_pos = tk.BooleanVar(value=saved_settings.get("use_free_pos", False))
        self.pos_x = tk.StringVar(value=str(saved_settings.get("pos_x", "0.5")))
        self.pos_y = tk.StringVar(value=str(saved_settings.get("pos_y", "0.85")))
        self.sub_box = tk.BooleanVar(value=saved_settings.get("sub_box", False))
        self.box_color = tk.StringVar(value=saved_settings.get("box_color", "white"))
        self.video_encoder = tk.StringVar(value=saved_settings.get("video_encoder", "Tự động (GPU QuickSync/MF/NVENC)"))
        self.export_preset = tk.StringVar(value=saved_settings.get("export_preset", "Rất nhanh (veryfast - Mặc định)"))
        self._extra_blur_rows = []

        # Subtitle Quick-Editor state
        self.sub_editor_target = tk.StringVar(value="vi")
        self._editor_sub_entries = []
        self._all_subs_data = []
        self._sub_page_size = 20
        self._sub_current_page = 0
        self._load_subs_timer_id = None
        self._refresh_spk_timer_id = None
        self._current_loaded_sub_path = None
        self._current_loaded_sub_mtime = 0
        self._current_loaded_sub_target = None
        self._current_spk_ui_file = None
        self._current_spk_ui_mtime = 0

        # Preview video state
        self.preview_seek_sec = tk.StringVar(value="2")
        self._current_preview_path = None
        self._preview_image = None
        self._preview_token = 0

        # Embedded Position Editor state
        self.pos_editor_seek_var = tk.StringVar(value="3")
        self._pos_editor_vid_w = 1280
        self._pos_editor_vid_h = 720
        self._pos_editor_canvas_w = 533
        self._pos_editor_canvas_h = 300
        self._pos_editor_dragging = None
        self._pos_canvas_photo = None
        self._pos_editor_raw_pil_frame = None
        self._pos_editor_maximized = False
        self._pos_editor_items_created = False

        self._build_ui()

        # Tự động lưu session khi đóng cửa sổ
        self.protocol("WM_DELETE_WINDOW", self._on_close_window)

        # Cài đặt Drag & Drop bằng windnd nếu có
        if HAS_WINDND:
            try:
                windnd.hook_dropfiles(self, func=self._on_files_dropped)
            except Exception as e:
                print(f"Warning: Failed to hook drag-and-drop: {e}")

        # Thêm trace để tự động cập nhật icon trạng thái, preview & position editor
        self.video_path.trace_add("write", lambda *args: self._on_video_path_changed())
        for var in [self.srt_path, self.orig_srt_path, self.output_path, self.dubbed_video_path]:
            var.trace_add("write", lambda *args: self._update_status_icons())
        for var in [self.mask_top, self.mask_bottom, self.crop_left, self.crop_right, self.pos_x, self.pos_y, self.use_free_pos,
                    self.font_size, self.font_name, self.font_color, self.outline_color,
                    self.sub_bold, self.sub_box, self.box_color]:
            var.trace_add("write", lambda *args: self._pos_editor_sync_from_vars())
        self.srt_path.trace_add("write", lambda *args: self._schedule_refresh_speaker_voice_ui())
        self.single_voice.trace_add("write", lambda *args: self._schedule_refresh_speaker_voice_ui())
        self.srt_path.trace_add("write", lambda *args: self._schedule_load_subtitles())
        self.orig_srt_path.trace_add("write", lambda *args: self._schedule_load_subtitles())
        self._update_status_icons()

        # Tự động nạp dữ liệu session đã lưu (Video preview, Frame canvas, Phụ đề)
        self.after(150, self._init_session_preview_and_subs)

    def _schedule_load_subtitles(self, delay_ms=120):
        """Chống dội (debounce) nạp phụ đề để không đọc và vẽ lại UI nhiều lần liên tiếp khi biến đổi."""
        if getattr(self, "_load_subs_timer_id", None):
            try:
                self.after_cancel(self._load_subs_timer_id)
            except Exception:
                pass
        self._load_subs_timer_id = self.after(delay_ms, self._load_subtitles_into_editor)

    def _schedule_refresh_speaker_voice_ui(self, delay_ms=100):
        """Chống dội (debounce) cập nhật danh sách nhân vật gán giọng."""
        if getattr(self, "_refresh_spk_timer_id", None):
            try:
                self.after_cancel(self._refresh_spk_timer_id)
            except Exception:
                pass
        self._refresh_spk_timer_id = self.after(delay_ms, self.refresh_speaker_voice_ui)

    def _poll_ui_queue(self):
        """Rút các thao tác cập nhật UI từ các worker thread về thực thi trên main thread."""
        try:
            while hasattr(self, "_ui_queue") and not self._ui_queue.empty():
                callback = self._ui_queue.get_nowait()
                try:
                    callback()
                except Exception as e:
                    print(f"Error executing UI callback: {e}")
        except Exception:
            pass
        finally:
            if hasattr(self, "after"):
                try:
                    self.after(50, self._poll_ui_queue)
                except Exception:
                    pass

    def run_on_ui_thread(self, func):
        """Chạy an toàn một hàm cập nhật UI từ bất kỳ thread phụ nào."""
        if hasattr(self, "_ui_queue"):
            self._ui_queue.put(func)
        else:
            try:
                self.after(0, func)
            except Exception:
                pass

    def _build_ui(self):
        # ── 1. Status Bar cố định ở đáy cửa sổ ──────────────────────────────
        self._build_status_bar()

        # ── 2. Top Header Bar (Video selection, Presets, Settings, Xuất video) ────
        self._build_top_bar()

        # ── 3. Studio Workspace (3 Cột: Phụ đề | Video Canvas | Inspector) ────
        self.workspace = ctk.CTkFrame(self, fg_color="transparent")
        self.workspace.pack(fill="both", expand=True, padx=8, pady=(4, 0))

        # Cột Trái: Transcript & Subtitle Editor (340px)
        self.left_col = ctk.CTkFrame(self.workspace, width=340, fg_color=COLOR_CARD_BG, corner_radius=8, border_width=1, border_color=COLOR_BORDER)
        self.left_col.pack(side="left", fill="y", padx=(0, 6), pady=0)
        self.left_col.pack_propagate(False)

        # Cột Phải: Inspector Thuộc tính & Settings (450px) - PACK TRƯỚC CỘT GIỮA ĐỂ BẢO TOÀN ĐỘ RỘNG
        self.right_col = ctk.CTkFrame(self.workspace, width=450, fg_color=COLOR_CARD_BG, corner_radius=8, border_width=1, border_color=COLOR_BORDER)
        self.right_col.pack(side="right", fill="y", padx=(6, 0), pady=0)
        self.right_col.pack_propagate(False)

        # Cột Giữa: Video Center Canvas & Interactive Placer (Chiếm toàn bộ khoảng trống còn lại)
        self.center_col = ctk.CTkFrame(self.workspace, fg_color=COLOR_CARD_BG, corner_radius=8, border_width=1, border_color=COLOR_BORDER)
        self.center_col.pack(side="left", fill="both", expand=True, padx=0, pady=0)

        # Khởi dựng nội dung cho 3 cột
        self._build_left_column()
        self._build_center_column()
        self._build_right_column()

        self._update_status_icons()

    def _build_status_bar(self):
        """Khởi tạo thanh trạng thái cố định ở đáy cửa sổ (mặc định thu gọn)."""
        self.status_bar = ctk.CTkFrame(self, corner_radius=0)
        self.status_bar.pack(side="bottom", fill="x", padx=0, pady=0)

        self._log_expanded = False

        # Panel Log mở rộng (đặt phía trên hàng thu gọn)
        self.log_panel = ctk.CTkFrame(self.status_bar, fg_color="transparent")

        self.log = ctk.CTkTextbox(self.log_panel, height=200)
        self.log.pack(fill="both", expand=True, padx=10, pady=(4, 4))
        self.log.configure(state="disabled")

        # Hàng trạng thái thu gọn (~36px)
        self.status_bar_row = ctk.CTkFrame(self.status_bar, fg_color="transparent", height=36)
        self.status_bar_row.pack(fill="x", padx=10, pady=4)

        # Nút toggle log (▲ / ▼) bên phải ngoài cùng
        self.btn_toggle_log = ctk.CTkButton(
            self.status_bar_row,
            text="▼ Log",
            width=58,
            height=28,
            command=self._toggle_log_panel,
            **OUTLINE_BTN
        )
        self.btn_toggle_log.pack(side="right", padx=(4, 0))

        # Nút Dừng (ẩn mặc định, pack khi job running)
        self.btn_cancel = ctk.CTkButton(
            self.status_bar_row,
            text="⏹ Dừng",
            **DANGER_BTN,
            width=80,
            height=28,
            command=self._cancel_job
        )

        # Label hiển thị trạng thái ngắn / log gần nhất
        self.status_label = ctk.CTkLabel(
            self.status_bar_row,
            text="Sẵn sàng",
            font=FONT_LABEL(),
            text_color=COLOR_TEXT_MUTED,
            anchor="w"
        )
        self.status_label.pack(side="right", padx=(8, 8))

        # Thanh tiến trình mỏng (~8px) co giãn bên trái
        self.progress = ctk.CTkProgressBar(self.status_bar_row, height=8)
        self.progress.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.progress.set(0)

    def _toggle_log_panel(self):
        """Ẩn/hiện panel log ở thanh trạng thái."""
        if not self._log_expanded:
            self.log_panel.pack(fill="both", expand=False, padx=10, pady=(6, 0), before=self.status_bar_row)
            self.btn_toggle_log.configure(text="▲ Log")
            self._log_expanded = True
        else:
            self.log_panel.pack_forget()
            self.btn_toggle_log.configure(text="▼ Log")
            self._log_expanded = False

    def _switch_tab(self, active_key):
        """Chuyển đổi tab Inspector bên phải."""
        mapping = {
            "video": "🤖 Dịch & AI",
            "subtitles": "🤖 Dịch & AI",
            "audio": "🎙 Giọng & TTS",
            "style": "🎨 Style & Mờ",
            "export": "🚀 Xuất Video",
        }
        tab_name = mapping.get(active_key, active_key)
        if hasattr(self, "inspector_tabs"):
            try:
                self.inspector_tabs.set(tab_name)
            except Exception:
                pass

    def _update_status_icons(self):
        """Cập nhật trạng thái file và warning banner."""
        o_path = self.orig_srt_path.get().strip() if hasattr(self, "orig_srt_path") else ""
        v_path = self.video_path.get().strip() if hasattr(self, "video_path") else ""
        base = os.path.splitext(os.path.basename(v_path))[0].lower() if v_path else ""
        if hasattr(self, "warning_banner") and self.warning_banner.winfo_exists():
            has_orig = False
            if o_path and os.path.isfile(o_path) and o_path.lower().endswith(".srt"):
                has_orig = True
            elif o_path and os.path.isdir(o_path) and base:
                has_orig = any(f.lower().endswith(".srt") and f.lower().startswith(base) for f in os.listdir(o_path))
            if has_orig:
                self.warning_banner.configure(
                    text="✔ Đã có file phụ đề gốc",
                    text_color=COLOR_SUCCESS,
                    fg_color=COLOR_SUCCESS_BG
                )
            else:
                self.warning_banner.configure(
                    text="⚠ Chưa có file phụ đề gốc để dịch",
                    text_color=COLOR_WARNING,
                    fg_color=COLOR_WARNING_BG
                )

    def _set_status_icon(self, key, text, color):
        pass

    # ── Top Bar ──────────────────────────────────────────────────────────────
    def _build_top_bar(self):
        self.top_bar = ctk.CTkFrame(self, height=48, corner_radius=0, fg_color="#18181B")
        self.top_bar.pack(side="top", fill="x", padx=0, pady=0)

        # Brand / Logo
        brand_f = ctk.CTkFrame(self.top_bar, fg_color="transparent")
        brand_f.pack(side="left", padx=(12, 14), pady=6)
        ctk.CTkLabel(
            brand_f,
            text="🎬 Vietsub & Dub AI",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#F3F4F6"
        ).pack(side="left")

        # Video source input box
        vid_box = ctk.CTkFrame(self.top_bar, fg_color="#242427", corner_radius=6)
        vid_box.pack(side="left", padx=0, pady=6)

        ctk.CTkLabel(vid_box, text="Video:", font=FONT_LABEL(), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(8, 6))
        self.top_video_entry = ctk.CTkEntry(
            vid_box, textvariable=self.video_path,
            placeholder_text="Chọn file video nguồn (.mp4, .mkv, .mov)...",
            height=30, width=280
        )
        self.top_video_entry.pack(side="left", padx=(0, 6))

        btn_pick_vid = ctk.CTkButton(
            vid_box, text="📁 Chọn video...",
            command=self.pick_video, height=30, width=105, **OUTLINE_BTN
        )
        btn_pick_vid.pack(side="left", padx=(0, 4))

        btn_download_link = ctk.CTkButton(
            vid_box, text="⬇ Tải từ link...",
            command=self.open_download_dialog, height=30, width=105, **OUTLINE_BTN
        )
        btn_download_link.pack(side="left", padx=(0, 4))

        self.preview_info_lbl = ctk.CTkLabel(
            vid_box, text="", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLOR_ACCENT
        )
        self.preview_info_lbl.pack(side="left", padx=(6, 10))

        # Right actions
        right_actions = ctk.CTkFrame(self.top_bar, fg_color="transparent")
        right_actions.pack(side="right", padx=12, pady=6)

        def _on_preset_picked(val):
            mapping = {
                "📱 TikTok (9:16)": "tiktok",
                "💻 YouTube (16:9)": "youtube",
                "🎬 Điện ảnh (Cinematic)": "cinematic",
                "🎧 Chỉ Thuyết minh": "dub_only",
                "📄 Chỉ Vietsub": "sub_only",
            }
            if val in mapping:
                self._apply_platform_preset(mapping[val])

        self.top_preset_menu = ctk.CTkOptionMenu(
            right_actions,
            values=["⚡ Presets", "📱 TikTok (9:16)", "💻 YouTube (16:9)", "🎬 Điện ảnh (Cinematic)", "🎧 Chỉ Thuyết minh", "📄 Chỉ Vietsub"],
            command=_on_preset_picked,
            height=32, width=150,
            fg_color="#27272A", button_color="#3F3F46"
        )
        self.top_preset_menu.pack(side="left", padx=(0, 10))

        btn_settings = ctk.CTkButton(
            right_actions,
            text="⚙ Cài đặt API",
            command=self.open_settings_modal,
            height=32, width=110,
            **OUTLINE_BTN
        )
        btn_settings.pack(side="left", padx=(0, 10))

        btn_export_top = ctk.CTkButton(
            right_actions,
            text="🚀 Xuất Video",
            command=lambda: self._switch_tab("export"),
            height=32, width=120,
            **PRIMARY_BTN,
            font=ctk.CTkFont(size=13, weight="bold")
        )
        btn_export_top.pack(side="left")

    # ── Cột Trái: Transcript & Subtitle Editor ────────────────────────────────
    def _build_left_column(self):
        col = self.left_col

        hdr = ctk.CTkFrame(col, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=(10, 4))
        ctk.CTkLabel(hdr, text="📝 Lời Thoại & Phụ Đề", font=FONT_SUBHEADING()).pack(side="left")
        self.sub_count_lbl = ctk.CTkLabel(hdr, text="", text_color=COLOR_TEXT_MUTED, font=FONT_CAPTION())
        self.sub_count_lbl.pack(side="right")

        ctrl_row = ctk.CTkFrame(col, fg_color="transparent")
        ctrl_row.pack(fill="x", padx=10, pady=(0, 6))

        def _on_sub_target_change(val):
            self.sub_editor_target.set("orig" if "gốc" in val.lower() else "vi")
            self._load_subtitles_into_editor()
            if getattr(self, "_editor_sub_entries", None):
                self._select_subtitle_by_index(0)

        self.sub_target_seg = ctk.CTkSegmentedButton(
            ctrl_row, values=["Tiếng Việt (.srt)", "File Gốc (.srt)"],
            command=_on_sub_target_change, height=28
        )
        self.sub_target_seg.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.sub_target_seg.set("Tiếng Việt (.srt)")

        def _pick_active_sub_file():
            if self.sub_editor_target.get() == "orig":
                self.pick_orig_srt()
            else:
                self.pick_srt()

        btn_pick_subs = ctk.CTkButton(
            ctrl_row, text="📂 Chọn", command=_pick_active_sub_file,
            width=68, height=28, **OUTLINE_BTN, font=ctk.CTkFont(size=11)
        )
        btn_pick_subs.pack(side="left", padx=(0, 4))

        btn_reload_subs = ctk.CTkButton(
            ctrl_row, text="🔄", command=self._load_subtitles_into_editor,
            width=32, height=28, **OUTLINE_BTN
        )
        btn_reload_subs.pack(side="left")

        actions_row = ctk.CTkFrame(col, fg_color="transparent")
        actions_row.pack(fill="x", padx=10, pady=(0, 6))

        btn_save_subs = ctk.CTkButton(
            actions_row, text="💾 Lưu SRT", command=self._save_subtitles_from_editor,
            height=28, **PRIMARY_BTN, font=ctk.CTkFont(size=12, weight="bold")
        )
        btn_save_subs.pack(side="left", fill="x", expand=True, padx=(0, 4))

        btn_template = ctk.CTkButton(
            actions_row, text="➕ Khung rỗng", command=lambda: self.run_template(btn_template),
            width=85, height=28, **OUTLINE_BTN, font=ctk.CTkFont(size=11)
        )
        btn_template.pack(side="left", padx=(0, 4))
        self._run_buttons.append(btn_template)

        btn_notepad = ctk.CTkButton(
            actions_row, text="📄 Notepad", command=self.open_srt,
            width=70, height=28, **OUTLINE_BTN, font=ctk.CTkFont(size=11)
        )
        btn_notepad.pack(side="left")

        # ── Thanh Dịch Chuyển Timeline Khớp Miệng (Timing Shift Toolbar) ──
        shift_row = ctk.CTkFrame(col, fg_color="transparent")
        shift_row.pack(fill="x", padx=10, pady=(0, 6))

        ctk.CTkLabel(shift_row, text="Khớp miệng:", font=FONT_CAPTION(), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(0, 4))

        btn_shift_m100 = ctk.CTkButton(
            shift_row, text="⏪ -100ms", width=64, height=24, **OUTLINE_BTN, font=ctk.CTkFont(size=10),
            command=lambda: self._shift_subtitles_timing(-100)
        )
        btn_shift_m100.pack(side="left", padx=2)

        btn_shift_p100 = ctk.CTkButton(
            shift_row, text="⏩ +100ms", width=64, height=24, **OUTLINE_BTN, font=ctk.CTkFont(size=10),
            command=lambda: self._shift_subtitles_timing(100)
        )
        btn_shift_p100.pack(side="left", padx=2)

        btn_shift_p150 = ctk.CTkButton(
            shift_row, text="⏩ +150ms", width=64, height=24, **OUTLINE_BTN, font=ctk.CTkFont(size=10),
            command=lambda: self._shift_subtitles_timing(150)
        )
        btn_shift_p150.pack(side="left", padx=2)

        btn_shift_custom = ctk.CTkButton(
            shift_row, text="⏱ Khác...", width=52, height=24, **OUTLINE_BTN, font=ctk.CTkFont(size=10),
            command=self._prompt_shift_timing
        )
        btn_shift_custom.pack(side="left", padx=2)

        # Thanh phân trang (Pagination Toolbar)
        self.sub_page_bar = ctk.CTkFrame(col, fg_color="#202023", corner_radius=6, height=32)
        self.sub_page_bar.pack(fill="x", padx=10, pady=(0, 6))

        self.btn_sub_prev_page = ctk.CTkButton(
            self.sub_page_bar, text="◀", width=28, height=24, **OUTLINE_BTN,
            command=self._sub_prev_page
        )
        self.btn_sub_prev_page.pack(side="left", padx=(4, 2), pady=4)

        self.lbl_sub_page_info = ctk.CTkLabel(
            self.sub_page_bar, text="Trang 1/1", font=FONT_CAPTION(),
            text_color=COLOR_TEXT_MUTED
        )
        self.lbl_sub_page_info.pack(side="left", padx=4, pady=4, expand=True)

        self.btn_sub_next_page = ctk.CTkButton(
            self.sub_page_bar, text="▶", width=28, height=24, **OUTLINE_BTN,
            command=self._sub_next_page
        )
        self.btn_sub_next_page.pack(side="left", padx=(2, 6), pady=4)

        lbl_jump = ctk.CTkLabel(self.sub_page_bar, text="#:", font=FONT_CAPTION(), text_color=COLOR_TEXT_MUTED)
        lbl_jump.pack(side="left", padx=(0, 2), pady=4)

        self.sub_jump_entry = ctk.CTkEntry(
            self.sub_page_bar, width=42, height=24, font=FONT_CAPTION(),
            placeholder_text="1"
        )
        self.sub_jump_entry.pack(side="left", padx=(0, 2), pady=4)
        self.sub_jump_entry.bind("<Return>", lambda e: self._sub_jump_to_number())

        btn_jump_go = ctk.CTkButton(
            self.sub_page_bar, text="Đi", width=30, height=24, **OUTLINE_BTN,
            font=ctk.CTkFont(size=10), command=self._sub_jump_to_number
        )
        btn_jump_go.pack(side="left", padx=(0, 4), pady=4)

        # Scrollable container for subtitle list
        self.sub_editor_scroll = ctk.CTkScrollableFrame(col, fg_color="#18181A")
        self.sub_editor_scroll.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    # ── Cột Giữa: Video Center Canvas & Controls ──────────────────────────────
    def _build_center_column(self):
        col = self.center_col

        pos_hdr = ctk.CTkFrame(col, fg_color="transparent")
        pos_hdr.pack(fill="x", padx=10, pady=(8, 4))

        ctk.CTkLabel(pos_hdr, text="🎬 Khung Xem Trước", font=FONT_SUBHEADING()).pack(side="left", padx=(0, 10))

        self.btn_pos_mode_seg = ctk.CTkSegmentedButton(
            pos_hdr, values=["🔴 Kéo vị trí", "🎬 Render thật"],
            command=self._pos_editor_on_mode_change,
            height=28, width=180
        )
        self.btn_pos_mode_seg.set("🔴 Kéo vị trí")
        self.btn_pos_mode_seg.pack(side="left")

        ctk.CTkLabel(
            pos_hdr,
            text="🔴 Đỏ: Che cũ  ■  🟢 Xanh: Sub mới",
            font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED
        ).pack(side="right")

        self.pos_canvas_pane = ctk.CTkFrame(col, fg_color="#111111", corner_radius=6)
        self.pos_canvas_pane.pack(fill="both", expand=True, padx=8, pady=(2, 4))
        self.pos_canvas_pane.bind("<Configure>", self._pos_editor_on_pane_configure)

        self.pos_editor_placeholder = ctk.CTkLabel(
            self.pos_canvas_pane,
            text="🎥 Chọn video nguồn để xem trước khung hình và kéo-thả vị trí\n(Bấm 'Chọn video...' ở góc trên)",
            font=FONT_LABEL(), text_color=COLOR_TEXT_MUTED, height=260
        )
        self.pos_editor_placeholder.pack(fill="both", expand=True, padx=20, pady=40)

        self.pos_canvas = tk.Canvas(
            self.pos_canvas_pane, width=800, height=450,
            bg="#111111", highlightthickness=1, highlightbackground="#333333"
        )

        pos_ctrl_bar = ctk.CTkFrame(col, fg_color="#1A1A1E", corner_radius=6)
        pos_ctrl_bar.pack(fill="x", padx=8, pady=(4, 8))

        # Row 1: Subtitle navigation & seek
        r1 = ctk.CTkFrame(pos_ctrl_bar, fg_color="transparent")
        r1.pack(fill="x", padx=8, pady=(6, 4))

        btn_prev = ctk.CTkButton(r1, text="⏮ Câu trước", command=self._prev_subtitle, width=88, height=28, **OUTLINE_BTN)
        btn_prev.pack(side="left", padx=(0, 5))

        ctk.CTkLabel(r1, text="⏱ Giây:", font=FONT_LABEL()).pack(side="left", padx=(0, 3))
        seek_entry = ctk.CTkEntry(r1, textvariable=self.pos_editor_seek_var, width=48, height=28)
        seek_entry.pack(side="left", padx=(0, 5))
        seek_entry.bind("<Return>", lambda e: self._pos_editor_refresh_frame())

        btn_next = ctk.CTkButton(r1, text="⏭ Câu sau", command=self._next_subtitle, width=88, height=28, **OUTLINE_BTN)
        btn_next.pack(side="left", padx=(0, 5))

        btn_refresh = ctk.CTkButton(r1, text="🔄 Làm mới", command=self._pos_editor_on_refresh_clicked, width=80, height=28, **OUTLINE_BTN)
        btn_refresh.pack(side="left", padx=(0, 8))

        self.pos_editor_seek_status = ctk.CTkLabel(r1, text="", font=FONT_CAPTION(), text_color=COLOR_TEXT_MUTED)
        self.pos_editor_seek_status.pack(side="left")

        self.pos_editor_info_lbl = ctk.CTkLabel(r1, text="", font=FONT_CAPTION(), text_color=COLOR_TEXT_MUTED, justify="right")
        self.pos_editor_info_lbl.pack(side="right")

        # Row 2: Alignment buttons & Maximize toggle
        r2 = ctk.CTkFrame(pos_ctrl_bar, fg_color="transparent")
        r2.pack(fill="x", padx=8, pady=(0, 6))

        ctk.CTkButton(r2, text="🎯 Căn ngang", command=self._pos_editor_center_x, height=26, width=95, **OUTLINE_BTN).pack(side="left", padx=(0, 5))
        ctk.CTkButton(r2, text="⏬ Lề dưới", command=self._pos_editor_bottom_y, height=26, width=90, **OUTLINE_BTN).pack(side="left", padx=(0, 5))
        ctk.CTkButton(r2, text="➕ Thêm blur", command=lambda: self._add_extra_blur_row(), height=26, width=105, **OUTLINE_BTN).pack(side="left")

        self.btn_pos_editor_max = ctk.CTkButton(
            r2, text="⛶ Phóng to", command=self._pos_editor_toggle_maximize,
            width=90, height=26, **OUTLINE_BTN
        )
        self.btn_pos_editor_max.pack(side="right")

    # ── Cột Phải: Inspector Thuộc Tính (Tabview) ─────────────────────────────
    def _build_right_column(self):
        col = self.right_col

        self.inspector_tabs = ctk.CTkTabview(col, corner_radius=6)
        self.inspector_tabs.pack(fill="both", expand=True, padx=6, pady=4)
        if hasattr(self.inspector_tabs, "_segmented_button"):
            self.inspector_tabs._segmented_button.configure(font=ctk.CTkFont(size=12, weight="bold"))

        tab_style = self.inspector_tabs.add("🎨 Style & Mờ")
        tab_audio = self.inspector_tabs.add("🎙 Giọng & TTS")
        tab_trans = self.inspector_tabs.add("🤖 Dịch & AI")
        tab_export = self.inspector_tabs.add("🚀 Xuất Video")

        self._build_tab_style_content(tab_style)
        self._build_tab_audio_content(tab_audio)
        self._build_tab_translate_content(tab_trans)
        self._build_tab_export_content(tab_export)

    # ── Nội dung Tab 1: Style & Mask ──────────────────────────────────────────
    def _build_tab_style_content(self, parent):
        sf = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        sf.pack(fill="both", expand=True, padx=2, pady=2)

        # Hàng Preset Save / Load
        r_preset_btns = ctk.CTkFrame(sf, fg_color="transparent")
        r_preset_btns.pack(fill="x", pady=(2, 8))
        ctk.CTkLabel(r_preset_btns, text="Cấu hình Preset:", font=FONT_LABEL(), text_color=COLOR_TEXT_MUTED).pack(side="left")
        ctk.CTkButton(r_preset_btns, text="💾 Lưu preset", command=self.save_preset, width=105, height=26, **OUTLINE_BTN).pack(side="right", padx=(4, 0))
        ctk.CTkButton(r_preset_btns, text="📂 Tải preset", command=self.load_preset, width=105, height=26, **OUTLINE_BTN).pack(side="right")

        # Card Quick Presets Nền Tảng (2 hàng cân đối, không bị khuất)
        card_p = ctk.CTkFrame(sf, fg_color="#202023", border_width=1, border_color=COLOR_BORDER, corner_radius=6)
        card_p.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(card_p, text="⚡ Nền Tảng Nhanh", font=FONT_SUBHEADING()).pack(anchor="w", padx=10, pady=(8, 4))

        presets_row1 = [
            ("📱 TikTok 9:16", "tiktok"),
            ("💻 YouTube 16:9", "youtube"),
            ("🎬 Cinematic", "cinematic"),
        ]
        presets_row2 = [
            ("🎧 Thuyết minh", "dub_only"),
            ("📄 Vietsub chuẩn", "sub_only"),
        ]
        p_row1 = ctk.CTkFrame(card_p, fg_color="transparent")
        p_row1.pack(fill="x", padx=8, pady=(0, 4))
        for title, pkey in presets_row1:
            ctk.CTkButton(
                p_row1, text=title,
                command=lambda k=pkey: self._apply_platform_preset(k),
                **OUTLINE_BTN, height=26, font=ctk.CTkFont(size=11)
            ).pack(side="left", padx=2, fill="x", expand=True)

        p_row2 = ctk.CTkFrame(card_p, fg_color="transparent")
        p_row2.pack(fill="x", padx=8, pady=(0, 8))
        for title, pkey in presets_row2:
            ctk.CTkButton(
                p_row2, text=title,
                command=lambda k=pkey: self._apply_platform_preset(k),
                **OUTLINE_BTN, height=26, font=ctk.CTkFont(size=11)
            ).pack(side="left", padx=2, fill="x", expand=True)

        # Card Che / Làm mờ phụ đề gốc
        self.card4a = ctk.CTkFrame(sf, fg_color="#202023", border_width=1, border_color=COLOR_BORDER, corner_radius=6)
        self.card4a.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(self.card4a, text="Che / Làm Mờ Phụ Đề Gốc", font=FONT_SUBHEADING()).pack(anchor="w", padx=10, pady=(8, 4))

        r_m1 = ctk.CTkFrame(self.card4a, fg_color="transparent")
        r_m1.pack(fill="x", padx=10, pady=3)
        ctk.CTkCheckBox(r_m1, text="Bật che sub cũ", variable=self.mask_original).pack(side="left")
        ctk.CTkLabel(r_m1, text="Kiểu:", font=FONT_LABEL()).pack(side="left", padx=(14, 4))
        ctk.CTkComboBox(r_m1, variable=self.mask_style, values=["box", "blur", "both"], width=85, height=INPUT_HEIGHT, state="readonly").pack(side="left")

        r_m2 = ctk.CTkFrame(self.card4a, fg_color="transparent")
        r_m2.pack(fill="x", padx=10, pady=3)
        ctk.CTkLabel(r_m2, text="Độ mờ:", font=FONT_LABEL()).pack(side="left", padx=(0, 4))
        ctk.CTkEntry(r_m2, textvariable=self.mask_blur, width=50, height=INPUT_HEIGHT).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(r_m2, text="Top:", font=FONT_LABEL()).pack(side="left", padx=(0, 4))
        ctk.CTkEntry(r_m2, textvariable=self.mask_top, width=65, height=INPUT_HEIGHT).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(r_m2, text="Bottom:", font=FONT_LABEL()).pack(side="left", padx=(0, 4))
        ctk.CTkEntry(r_m2, textvariable=self.mask_bottom, width=65, height=INPUT_HEIGHT).pack(side="left")

        r_m3 = ctk.CTkFrame(self.card4a, fg_color="transparent")
        r_m3.pack(fill="x", padx=10, pady=3)
        ctk.CTkCheckBox(r_m3, text="Vị trí tự do", variable=self.use_free_pos).pack(side="left", padx=(0, 12))
        ctk.CTkLabel(r_m3, text="X:").pack(side="left", padx=(0, 3))
        ctk.CTkEntry(r_m3, textvariable=self.pos_x, width=60, height=INPUT_HEIGHT).pack(side="left", padx=(0, 12))
        ctk.CTkLabel(r_m3, text="Y:").pack(side="left", padx=(0, 3))
        ctk.CTkEntry(r_m3, textvariable=self.pos_y, width=60, height=INPUT_HEIGHT).pack(side="left")

        btn_mask_prev = ctk.CTkButton(
            self.card4a, text="👁 Xem trước vùng che (xuất ảnh)",
            command=lambda: self.run_mask_preview(btn_mask_prev),
            **OUTLINE_BTN, height=28
        )
        btn_mask_prev.pack(fill="x", padx=10, pady=(6, 10))
        self._run_buttons.append(btn_mask_prev)

        # Card Font & Kiểu Phụ Đề Mới
        self.card4b = ctk.CTkFrame(sf, fg_color="#202023", border_width=1, border_color=COLOR_BORDER, corner_radius=6)
        self.card4b.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(self.card4b, text="Kiểu Dáng & Font Phụ Đề Mới", font=FONT_SUBHEADING()).pack(anchor="w", padx=10, pady=(8, 4))

        self._preset_fonts = [
            "Be Vietnam Pro", "Arial", "Arial Black", "Helvetica", "Verdana", "Tahoma",
            "Trebuchet MS", "Segoe UI", "Calibri", "Roboto", "Open Sans",
            "Noto Sans", "Times New Roman", "Consolas", "Impact",
            "Montserrat", "Inter", "Lato", "Poppins"
        ]
        self._system_fonts_scanned = False

        r_f1 = ctk.CTkFrame(self.card4b, fg_color="transparent")
        r_f1.pack(fill="x", padx=10, pady=3)
        ctk.CTkLabel(r_f1, text="Font:").pack(side="left", padx=(0, 6))
        self.font_combo = ctk.CTkComboBox(r_f1, variable=self.font_name, values=self._preset_fonts, width=175, height=INPUT_HEIGHT)
        self.font_combo.pack(side="left", padx=(0, 6), fill="x", expand=True)
        self.btn_scan_fonts = ctk.CTkButton(r_f1, text="Quét", command=self._scan_system_fonts, width=55, height=INPUT_HEIGHT, **OUTLINE_BTN)
        self.btn_scan_fonts.pack(side="right")

        r_f2 = ctk.CTkFrame(self.card4b, fg_color="transparent")
        r_f2.pack(fill="x", padx=10, pady=3)
        ctk.CTkLabel(r_f2, text="Cỡ:").pack(side="left", padx=(0, 4))
        ctk.CTkEntry(r_f2, textvariable=self.font_size, width=50, height=INPUT_HEIGHT).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(r_f2, text="Vị trí:").pack(side="left", padx=(0, 4))
        ctk.CTkComboBox(r_f2, variable=self.sub_position, values=["bottom", "middle", "top"], width=95, height=INPUT_HEIGHT, state="readonly").pack(side="left", padx=(0, 12))
        ctk.CTkCheckBox(r_f2, text="In đậm", variable=self.sub_bold).pack(side="left")

        r_f3 = ctk.CTkFrame(self.card4b, fg_color="transparent")
        r_f3.pack(fill="x", padx=10, pady=3)
        ctk.CTkLabel(r_f3, text="Màu chữ:").pack(side="left", padx=(0, 4))
        self.font_color_swatch = ctk.CTkLabel(r_f3, text="", fg_color="white", width=24, height=24, corner_radius=3)
        self.font_color_swatch.pack(side="left", padx=(0, 4))
        ctk.CTkButton(r_f3, text="Đổi...", width=58, height=26, command=lambda: self._pick_color(self.font_color, self.font_color_swatch), **OUTLINE_BTN).pack(side="left", padx=(0, 14))

        ctk.CTkLabel(r_f3, text="Viền:").pack(side="left", padx=(0, 4))
        self.outline_color_swatch = ctk.CTkLabel(r_f3, text="", fg_color="black", width=24, height=24, corner_radius=3)
        self.outline_color_swatch.pack(side="left", padx=(0, 4))
        ctk.CTkButton(r_f3, text="Đổi...", width=58, height=26, command=lambda: self._pick_color(self.outline_color, self.outline_color_swatch), **OUTLINE_BTN).pack(side="left")

        r_f4 = ctk.CTkFrame(self.card4b, fg_color="transparent")
        r_f4.pack(fill="x", padx=10, pady=(3, 6))
        ctk.CTkLabel(r_f4, text="Dày viền:").pack(side="left", padx=(0, 4))
        ctk.CTkEntry(r_f4, textvariable=self.outline_width, width=45, height=INPUT_HEIGHT).pack(side="left", padx=(0, 12))
        ctk.CTkCheckBox(r_f4, text="Hộp nền", variable=self.sub_box).pack(side="left", padx=(0, 6))
        self.box_color_swatch = ctk.CTkLabel(r_f4, text="", fg_color="white", width=22, height=22, corner_radius=3)
        self.box_color_swatch.pack(side="left", padx=(0, 4))
        ctk.CTkButton(r_f4, text="Màu", width=48, height=26, command=lambda: self._pick_color(self.box_color, self.box_color_swatch), **OUTLINE_BTN).pack(side="left")

        btn_sub_prev = ctk.CTkButton(
            self.card4b, text="👁 Xem trước kiểu phụ đề (xuất ảnh)",
            command=lambda: self.run_subtitle_preview(btn_sub_prev),
            **OUTLINE_BTN, height=28
        )
        btn_sub_prev.pack(fill="x", padx=10, pady=(4, 10))
        self._run_buttons.append(btn_sub_prev)

        # Card Vùng làm mờ tuỳ chỉnh
        self.card4c = ctk.CTkFrame(sf, fg_color="#202023", border_width=1, border_color=COLOR_BORDER, corner_radius=6)
        self.card4c.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(self.card4c, text="Vùng Làm Mờ Bổ Sung (--extra-blur)", font=FONT_SUBHEADING()).pack(anchor="w", padx=10, pady=(8, 4))
        self._eb_list_frame = ctk.CTkFrame(self.card4c, fg_color="transparent")
        self._eb_list_frame.pack(fill="x", padx=8, pady=(0, 8))

    # ── Nội dung Tab 2: Giọng & Âm Thanh ─────────────────────────────────────
    def _build_tab_audio_content(self, parent):
        sf = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        sf.pack(fill="both", expand=True, padx=2, pady=2)

        # Card Công cụ TTS & Giọng
        card_tts = ctk.CTkFrame(sf, fg_color="#202023", border_width=1, border_color=COLOR_BORDER, corner_radius=6)
        card_tts.pack(fill="x", pady=(2, 10))
        ctk.CTkLabel(card_tts, text="Công Cụ TTS & Giọng Đọc", font=FONT_SUBHEADING()).pack(anchor="w", padx=10, pady=(8, 4))

        r_t1 = ctk.CTkFrame(card_tts, fg_color="transparent")
        r_t1.pack(fill="x", padx=10, pady=3)
        ctk.CTkLabel(r_t1, text="Engine:").pack(side="left", padx=(0, 6))
        engine_combo = ctk.CTkComboBox(r_t1, variable=self.tts_engine, values=["edge", "piper", "capcut"], width=95, height=INPUT_HEIGHT, state="readonly")
        engine_combo.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(r_t1, text="Giọng:").pack(side="left", padx=(0, 6))
        voice_combo = ctk.CTkComboBox(r_t1, variable=self.voice, values=["nu-hoaimy", "nam-namminh"], width=135, height=INPUT_HEIGHT, state="readonly")
        voice_combo.pack(side="left")

        self.btn_preview_voice = ctk.CTkButton(
            r_t1, text="▶", width=30, height=INPUT_HEIGHT,
            command=self.run_preview_voice, **OUTLINE_BTN
        )
        self.btn_preview_voice.pack(side="left", padx=(4, 0))
        self._run_buttons.append(self.btn_preview_voice)

        row_capcut = ctk.CTkFrame(card_tts, fg_color="transparent")
        ctk.CTkLabel(row_capcut, text="Tốc độ CapCut:").pack(side="left", padx=(0, 6))
        _capcut_rate_disp = ctk.CTkLabel(row_capcut, text="1.00", width=36)
        ctk.CTkSlider(row_capcut, from_=0.5, to=2.0, variable=self.capcut_rate, width=120,
                      command=lambda v: _capcut_rate_disp.configure(text=f"{float(v):.2f}")).pack(side="left", padx=4)
        _capcut_rate_disp.pack(side="left")

        def _on_engine_change(choice):
            eng = choice
            voices_list = VOICES.get(eng, VOICES["edge"])
            voice_combo.configure(values=voices_list)
            if voices_list:
                self.voice.set(voices_list[0])
            if eng == "capcut":
                row_capcut.pack(fill="x", padx=10, pady=(0, 6))
            else:
                row_capcut.pack_forget()
            self.after(50, self.refresh_speaker_voice_ui)

        self._engine_combo_callback = _on_engine_change
        engine_combo.configure(command=_on_engine_change)

        r_t2 = ctk.CTkFrame(card_tts, fg_color="transparent")
        r_t2.pack(fill="x", padx=10, pady=(4, 8))
        ctk.CTkCheckBox(
            r_t2, text="Chỉ dùng 1 giọng duy nhất (bỏ qua chia vai)",
            variable=self.single_voice, font=FONT_LABEL()
        ).pack(side="left")

        # Khung phân chia giọng theo vai
        self.frame_speakers = ctk.CTkFrame(card_tts, fg_color="transparent")

        # Card Âm thanh gốc & Trộn âm
        card_mix = ctk.CTkFrame(sf, fg_color="#202023", border_width=1, border_color=COLOR_BORDER, corner_radius=6)
        card_mix.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(card_mix, text="Âm Thanh Gốc & Trộn Âm", font=FONT_SUBHEADING()).pack(anchor="w", padx=10, pady=(8, 4))

        r_m1 = ctk.CTkFrame(card_mix, fg_color="transparent")
        r_m1.pack(fill="x", padx=10, pady=3)
        ctk.CTkLabel(r_m1, text="Âm gốc:").pack(side="left", padx=(0, 6))
        mix_combo = ctk.CTkComboBox(r_m1, variable=self.keep_original, values=["voiceover", "dubbing", "custom"], width=110, height=INPUT_HEIGHT, state="readonly")
        mix_combo.pack(side="left", padx=(0, 6))
        ctk.CTkLabel(r_m1, text="(voiceover / dubbing / custom)", text_color=COLOR_TEXT_MUTED, font=FONT_CAPTION()).pack(side="left")

        row_custom = ctk.CTkFrame(card_mix, fg_color="transparent")
        bg_disp = ctk.CTkLabel(row_custom, text=f"{self.bg_volume.get():.2f}", width=34)
        dub_disp = ctk.CTkLabel(row_custom, text=f"{self.dub_volume.get():.2f}", width=34)

        def _show_custom_row(choice):
            if choice == "custom":
                row_custom.pack(fill="x", padx=10, pady=(0, 8))
            else:
                row_custom.pack_forget()

        mix_combo.configure(command=_show_custom_row)
        self._show_custom_row = _show_custom_row
        ctk.CTkLabel(row_custom, text="Nhạc gốc:").pack(side="left", padx=(0, 4))
        ctk.CTkSlider(row_custom, from_=0.0, to=1.0, variable=self.bg_volume, width=80,
                      command=lambda v: bg_disp.configure(text=f"{float(v):.2f}")).pack(side="left", padx=2)
        bg_disp.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(row_custom, text="Giọng lồng:").pack(side="left", padx=(0, 4))
        ctk.CTkSlider(row_custom, from_=0.0, to=2.0, variable=self.dub_volume, width=80,
                      command=lambda v: dub_disp.configure(text=f"{float(v):.2f}")).pack(side="left", padx=2)
        dub_disp.pack(side="left")

        if self.keep_original.get() == "custom":
            _show_custom_row("custom")

    # ── Nội dung Tab 3: Dịch & Whisper ───────────────────────────────────────
    def _build_tab_translate_content(self, parent):
        sf = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        sf.pack(fill="both", expand=True, padx=2, pady=2)

        # Card Bước 1: Nguồn Phụ Đề Gốc (Whisper âm thanh hoặc RapidOCR hình ảnh)
        card_src = ctk.CTkFrame(sf, fg_color="#202023", border_width=1, border_color=COLOR_BORDER, corner_radius=6)
        card_src.pack(fill="x", pady=(2, 10))
        ctk.CTkLabel(card_src, text="Bước 1: Nguồn Phụ Đề Gốc", font=FONT_SUBHEADING()).pack(anchor="w", padx=10, pady=(8, 4))

        frame_whisper = ctk.CTkFrame(card_src, fg_color="transparent")
        frame_ocr = ctk.CTkFrame(card_src, fg_color="transparent")

        # --- Whisper UI ---
        r_w1 = ctk.CTkFrame(frame_whisper, fg_color="transparent")
        r_w1.pack(fill="x", pady=2)
        ctk.CTkLabel(r_w1, text="Model:").pack(side="left", padx=(0, 6))
        ctk.CTkComboBox(r_w1, variable=self.whisper_model, values=["tiny", "base", "small", "medium", "large-v3"], width=110, height=INPUT_HEIGHT, state="readonly").pack(side="left", padx=(0, 10))

        chk_diarize = ctk.CTkCheckBox(r_w1, text="Tách người nói", variable=self.enable_diarize, font=FONT_LABEL())
        chk_diarize.pack(side="left")

        self.hf_badge = ctk.CTkLabel(frame_whisper, text="", font=FONT_CAPTION())
        self.hf_badge.pack(anchor="w", pady=(2, 2))

        def _update_hf_badge():
            if self.enable_diarize.get():
                if self.hf_token.get().strip():
                    self.hf_badge.configure(text="[Đã có HF Token ✓]", text_color=COLOR_SUCCESS)
                else:
                    self.hf_badge.configure(text="[⚠ Cần HF Token - mở Cài đặt API]", text_color=COLOR_WARNING)
            else:
                self.hf_badge.configure(text="")

        chk_diarize.configure(command=_update_hf_badge)
        self.hf_token.trace_add("write", lambda *args: _update_hf_badge())
        _update_hf_badge()

        # --- RapidOCR UI ---
        ctk.CTkLabel(
            frame_ocr,
            text="ℹ Quét chữ trực tiếp từ video (100% offline, chuẩn cho video ồn/nhạc lớn/sub Douyin, Kuaishou).",
            font=FONT_CAPTION(), text_color=COLOR_TEXT_MUTED, wraplength=340, justify="left"
        ).pack(anchor="w", pady=(0, 4))

        r_ocr_pos = ctk.CTkFrame(frame_ocr, fg_color="transparent")
        r_ocr_pos.pack(fill="x", pady=2)
        ctk.CTkLabel(r_ocr_pos, text="Top:", font=FONT_CAPTION()).pack(side="left", padx=(0, 2))
        ctk.CTkEntry(r_ocr_pos, textvariable=self.mask_top, width=44, height=24, font=FONT_CAPTION()).pack(side="left", padx=(0, 5))
        ctk.CTkLabel(r_ocr_pos, text="Bot:", font=FONT_CAPTION()).pack(side="left", padx=(0, 2))
        ctk.CTkEntry(r_ocr_pos, textvariable=self.mask_bottom, width=44, height=24, font=FONT_CAPTION()).pack(side="left", padx=(0, 5))
        ctk.CTkLabel(r_ocr_pos, text="Left:", font=FONT_CAPTION()).pack(side="left", padx=(0, 2))
        ctk.CTkEntry(r_ocr_pos, textvariable=self.crop_left, width=40, height=24, font=FONT_CAPTION()).pack(side="left", padx=(0, 5))
        ctk.CTkLabel(r_ocr_pos, text="Right:", font=FONT_CAPTION()).pack(side="left", padx=(0, 2))
        ctk.CTkEntry(r_ocr_pos, textvariable=self.crop_right, width=40, height=24, font=FONT_CAPTION()).pack(side="left", padx=(0, 5))
        ctk.CTkLabel(r_ocr_pos, text="FPS:", font=FONT_CAPTION()).pack(side="left", padx=(0, 2))
        ctk.CTkEntry(r_ocr_pos, textvariable=self.ocr_fps, width=36, height=24, font=FONT_CAPTION()).pack(side="left")

        ctk.CTkLabel(
            frame_ocr,
            text="🔗 Vùng quét đồng bộ trực tiếp với khung viền đỏ trên màn hình Canvas (bạn có thể kéo thả để canh chuẩn).",
            font=FONT_CAPTION(), text_color=COLOR_SUCCESS, wraplength=340, justify="left"
        ).pack(anchor="w", pady=(2, 4))

        def _on_source_mode_change(val):
            is_ocr = "ocr" in val.lower() or "sub cứng" in val.lower()
            mode = "ocr" if is_ocr else "whisper"
            self.sub_source_mode.set(mode)
            if mode == "ocr":
                frame_whisper.pack_forget()
                frame_ocr.pack(fill="x", padx=10, pady=(0, 8))
                btn_get_orig.configure(text="👁 Quét phụ đề cứng (RapidOCR)")
                btn_auto_trans.configure(text="🚀 Tự Quét OCR & Dịch AI (A-Z)")
            else:
                frame_ocr.pack_forget()
                frame_whisper.pack(fill="x", padx=10, pady=(0, 8))
                btn_get_orig.configure(text="Chỉ lấy phụ đề GỐC (Whisper)")
                btn_auto_trans.configure(text="🚀 Tự Nhận Diện & Dịch AI (A-Z)")

        seg_source = ctk.CTkSegmentedButton(
            card_src, values=["🎙 Giọng nói (Whisper)", "👁 Sub cứng (RapidOCR)"],
            command=_on_source_mode_change, height=28
        )
        seg_source.pack(fill="x", padx=10, pady=(0, 6))

        # Khởi tạo trạng thái ban đầu cho tab nguồn
        if self.sub_source_mode.get() == "ocr":
            seg_source.set("👁 Sub cứng (RapidOCR)")
            frame_ocr.pack(fill="x", padx=10, pady=(0, 8))
        else:
            seg_source.set("🎙 Giọng nói (Whisper)")
            frame_whisper.pack(fill="x", padx=10, pady=(0, 8))

        # Card Engine Dịch AI
        card_ai = ctk.CTkFrame(sf, fg_color="#202023", border_width=1, border_color=COLOR_BORDER, corner_radius=6)
        card_ai.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(card_ai, text="Engine Dịch AI (Groq / Gemini)", font=FONT_SUBHEADING()).pack(anchor="w", padx=10, pady=(8, 4))

        r_ai1 = ctk.CTkFrame(card_ai, fg_color="transparent")
        r_ai1.pack(fill="x", padx=10, pady=3)

        def _on_engine_change(val):
            eng = "groq" if "groq" in val.lower() else "gemini"
            self.translate_engine.set(eng)
            self._update_ai_status_banner()

        seg_engine = ctk.CTkSegmentedButton(
            r_ai1, values=["Gemini (Google)", "Groq (Llama/Qwen)"],
            command=_on_engine_change, height=28
        )
        seg_engine.pack(side="left", fill="x", expand=True, padx=(0, 6))
        seg_engine.set("Groq (Llama/Qwen)" if self.translate_engine.get() == "groq" else "Gemini (Google)")

        btn_cfg = ctk.CTkButton(r_ai1, text="⚙ Key", command=self.open_settings_modal, width=55, height=28, **OUTLINE_BTN)
        btn_cfg.pack(side="left")

        r_ai2 = ctk.CTkFrame(card_ai, fg_color="transparent")
        r_ai2.pack(fill="x", padx=10, pady=2)
        self.ai_status_banner = ctk.CTkLabel(r_ai2, text="", font=FONT_CAPTION(), anchor="w")
        self.ai_status_banner.pack(side="left", fill="x", expand=True)

        self.btn_quick_quota = ctk.CTkButton(
            r_ai2, text="🔍 Quota", command=lambda: self.run_check_quota(self.btn_quick_quota),
            width=65, height=24, **OUTLINE_BTN, font=FONT_CAPTION()
        )
        self.btn_quick_quota.pack(side="right")
        self._run_buttons.append(self.btn_quick_quota)

        self._update_ai_status_banner()

        # Warning banner
        self.warning_banner = ctk.CTkLabel(
            card_ai, text="⚠ Chưa có file phụ đề gốc", text_color=COLOR_WARNING,
            fg_color=COLOR_WARNING_BG, corner_radius=4, height=26, font=FONT_CAPTION()
        )
        self.warning_banner.pack(fill="x", padx=10, pady=(4, 8))

        # Actions
        btn_auto_trans = ctk.CTkButton(
            card_ai, text="🚀 Tự Quét OCR & Dịch AI (A-Z)" if self.sub_source_mode.get() == "ocr" else "🚀 Tự Nhận Diện & Dịch AI (A-Z)",
            command=lambda: self.run_auto_transcribe(btn_auto_trans),
            **PRIMARY_BTN, font=ctk.CTkFont(size=13, weight="bold"), height=36
        )
        btn_auto_trans.pack(fill="x", padx=10, pady=(0, 6))

        def _handle_get_orig():
            if self.sub_source_mode.get() == "ocr":
                self.run_ocr_only(btn_get_orig)
            else:
                self.run_get_original_only(btn_get_orig)

        btn_get_orig = ctk.CTkButton(
            card_ai, text="👁 Quét phụ đề cứng (RapidOCR)" if self.sub_source_mode.get() == "ocr" else "Chỉ lấy phụ đề GỐC (Whisper)",
            command=_handle_get_orig,
            **OUTLINE_BTN, height=30
        )
        btn_get_orig.pack(fill="x", padx=10, pady=(0, 6))

        btn_trans_only = ctk.CTkButton(
            card_ai, text="Chỉ dịch (AI) từ file GỐC",
            command=lambda: self.run_translate_only(btn_trans_only),
            **OUTLINE_BTN, height=30
        )
        btn_trans_only.pack(fill="x", padx=10, pady=(0, 8))
        self._run_buttons.extend([btn_auto_trans, btn_get_orig, btn_trans_only])

        r_orig = ctk.CTkFrame(card_ai, fg_color="transparent")
        r_orig.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkLabel(r_orig, text="File gốc:", font=FONT_CAPTION()).pack(side="left", padx=(0, 4))
        ctk.CTkEntry(r_orig, textvariable=self.orig_srt_path, height=26, font=FONT_CAPTION()).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkButton(r_orig, text="📂 Chọn", command=self.pick_orig_srt, width=58, height=26, **OUTLINE_BTN).pack(side="left", padx=(0, 4))
        ctk.CTkButton(r_orig, text="Mở", command=self.open_orig_srt, width=45, height=26, **OUTLINE_BTN).pack(side="left")

    # ── Nội dung Tab 4: Xuất Video ───────────────────────────────────────────
    def _build_tab_export_content(self, parent):
        sf = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        sf.pack(fill="both", expand=True, padx=2, pady=2)

        # Post-Job Success Card
        self.post_job_card = ctk.CTkFrame(sf, fg_color="#14532D", border_width=1, border_color=COLOR_SUCCESS, corner_radius=6)
        # Mặc định KHÔNG pack

        pj_top = ctk.CTkFrame(self.post_job_card, fg_color="transparent")
        pj_top.pack(fill="x", padx=10, pady=(8, 2))
        ctk.CTkLabel(pj_top, text="🎉 Xuất Video Hoàn Tất!", font=FONT_SUBHEADING(), text_color="#86EFAC").pack(side="left")

        self.post_job_file_lbl = ctk.CTkLabel(self.post_job_card, text="", font=FONT_CAPTION(), text_color="#E5E7EB", justify="left", anchor="w")
        self.post_job_file_lbl.pack(fill="x", padx=10, pady=(0, 6))

        pj_act = ctk.CTkFrame(self.post_job_card, fg_color="transparent")
        pj_act.pack(fill="x", padx=10, pady=(0, 8))
        ctk.CTkButton(pj_act, text="▶ Xem ngay", command=self._play_completed_video, height=28, **PRIMARY_BTN, font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=(0, 4), fill="x", expand=True)
        ctk.CTkButton(pj_act, text="📁 Thư mục", command=self._open_completed_folder, height=28, **OUTLINE_BTN, font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4), fill="x", expand=True)
        ctk.CTkButton(pj_act, text="📋 Copy path", command=self._copy_completed_path, height=28, **OUTLINE_BTN, font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4), fill="x", expand=True)
        ctk.CTkButton(pj_act, text="📱 Gửi điện thoại", command=self._share_to_phone, height=28, fg_color="#059669", hover_color="#047857", text_color="#FFFFFF", font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", fill="x", expand=True)

        # Card Xuất Video Hoàn Chỉnh
        self.card5a = ctk.CTkFrame(sf, fg_color="#202023", border_width=1, border_color=COLOR_BORDER, corner_radius=6)
        self.card5a.pack(fill="x", pady=(2, 10))
        ctk.CTkLabel(self.card5a, text="Xuất Video Hoàn Chỉnh", font=FONT_SUBHEADING()).pack(anchor="w", padx=10, pady=(8, 4))

        r_o1 = ctk.CTkFrame(self.card5a, fg_color="transparent")
        r_o1.pack(fill="x", padx=10, pady=(0, 8))
        ctk.CTkEntry(r_o1, textvariable=self.output_path, placeholder_text="Nơi lưu file kết quả...", height=INPUT_HEIGHT).pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(r_o1, text="Chọn...", command=self.pick_output, width=70, height=INPUT_HEIGHT, **OUTLINE_BTN).pack(side="left", padx=(0, 4))
        ctk.CTkButton(r_o1, text="📱", command=self._share_to_phone, width=38, height=INPUT_HEIGHT, **OUTLINE_BTN).pack(side="left")

        # Cấu hình Tốc độ & Bộ mã hóa GPU
        r_enc = ctk.CTkFrame(self.card5a, fg_color="transparent")
        r_enc.pack(fill="x", padx=10, pady=(0, 4))
        ctk.CTkLabel(r_enc, text="Bộ mã hóa:", font=FONT_LABEL(), width=85, anchor="w").pack(side="left")
        ctk.CTkComboBox(
            r_enc, variable=self.video_encoder,
            values=[
                "Tự động (GPU QuickSync/MF/NVENC)",
                "Intel QSV (GPU)",
                "Media Foundation (GPU)",
                "NVIDIA NVENC (GPU)",
                "CPU (libx264)"
            ],
            height=INPUT_HEIGHT, state="readonly"
        ).pack(side="left", fill="x", expand=True)

        r_pre = ctk.CTkFrame(self.card5a, fg_color="transparent")
        r_pre.pack(fill="x", padx=10, pady=(0, 6))
        ctk.CTkLabel(r_pre, text="Tốc độ xuất:", font=FONT_LABEL(), width=85, anchor="w").pack(side="left")
        ctk.CTkComboBox(
            r_pre, variable=self.export_preset,
            values=[
                "Rất nhanh (veryfast - Mặc định)",
                "Cực nhanh (ultrafast)",
                "Cân bằng (fast)",
                "Chất lượng cao (medium)"
            ],
            height=INPUT_HEIGHT, state="readonly"
        ).pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            self.card5a,
            text="⚡ Tự động dùng GPU Intel/NVIDIA giúp xuất video nhanh hơn gấp 5 - 7 lần CPU.",
            font=FONT_CAPTION(), text_color=COLOR_SUCCESS
        ).pack(anchor="w", padx=10, pady=(0, 8))

        btn_run_all = ctk.CTkButton(
            self.card5a, text="🚀 CHẠY: Lồng tiếng + Gắn Sub",
            command=lambda: self.run_all(btn_run_all),
            **PRIMARY_BTN, font=ctk.CTkFont(size=14, weight="bold"), height=40
        )
        btn_run_all.pack(fill="x", padx=10, pady=(0, 6))

        btn_run_burn_sub_only = ctk.CTkButton(
            self.card5a, text="🎬 CHỈ GẮN PHỤ ĐỀ (Không lồng tiếng, giữ tiếng gốc)",
            command=lambda: self.run_burn_original_only(btn_run_burn_sub_only),
            fg_color="#0F766E", hover_color="#0D9488", text_color="#FFFFFF",
            font=ctk.CTkFont(size=13, weight="bold"), height=36
        )
        btn_run_burn_sub_only.pack(fill="x", padx=10, pady=(0, 10))
        self._run_buttons.extend([btn_run_all, btn_run_burn_sub_only])

        # Card Chạy Riêng Lẻ
        card_sub_ops = ctk.CTkFrame(sf, fg_color="#202023", border_width=1, border_color=COLOR_BORDER, corner_radius=6)
        card_sub_ops.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(card_sub_ops, text="Chạy Riêng Lẻ Từng Bước", font=FONT_SUBHEADING()).pack(anchor="w", padx=10, pady=(8, 4))

        btn_dub_only = ctk.CTkButton(card_sub_ops, text="Chỉ lồng tiếng (không sub)", command=lambda: self.run_dub_only(btn_dub_only), height=30, **OUTLINE_BTN)
        btn_dub_only.pack(fill="x", padx=10, pady=(0, 6))

        btn_burn_orig = ctk.CTkButton(card_sub_ops, text="Chỉ gắn phụ đề vào video gốc (không dub)", command=lambda: self.run_burn_original_only(btn_burn_orig), height=30, **OUTLINE_BTN)
        btn_burn_orig.pack(fill="x", padx=10, pady=(0, 6))

        btn_burn_only = ctk.CTkButton(card_sub_ops, text="Gắn phụ đề vào video đã lồng tiếng", command=lambda: self.run_burn_only(btn_burn_only), height=30, **OUTLINE_BTN)
        btn_burn_only.pack(fill="x", padx=10, pady=(0, 6))
        self._run_buttons.extend([btn_dub_only, btn_burn_orig, btn_burn_only])

        r_dub = ctk.CTkFrame(card_sub_ops, fg_color="transparent")
        r_dub.pack(fill="x", padx=10, pady=(2, 6))
        ctk.CTkLabel(r_dub, text="Video đã dub:", font=FONT_CAPTION()).pack(side="left", padx=(0, 4))
        ctk.CTkEntry(r_dub, textvariable=self.dubbed_video_path, height=26, font=FONT_CAPTION()).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkButton(r_dub, text="Chọn", command=self.pick_dubbed_video, width=50, height=26, **OUTLINE_BTN).pack(side="left")

        r_job = ctk.CTkFrame(card_sub_ops, fg_color="transparent")
        r_job.pack(fill="x", padx=10, pady=(0, 8))
        ctk.CTkLabel(r_job, text="Thư mục Job:", font=FONT_CAPTION()).pack(side="left", padx=(0, 4))
        ctk.CTkEntry(r_job, textvariable=self.job_output_dir, height=26, font=FONT_CAPTION(), state="readonly").pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkButton(r_job, text="📂", command=self._open_job_output_dir, width=36, height=26, **OUTLINE_BTN).pack(side="left")

    # ── Các hàm Quản lý Preset Cấu Hình JSON ─────────────────────────────────
    def save_preset(self):
        """Lưu toàn bộ cấu hình style/mask/âm thanh vào file JSON."""
        init_dir = self._get_job_initialdir()
        v_path = self.video_path.get().strip() if hasattr(self, "video_path") else ""
        base = os.path.splitext(os.path.basename(v_path))[0] if v_path else "preset"
        initial_filename = f"{base}_preset.json" if v_path else "preset.json"

        path = filedialog.asksaveasfilename(
            initialdir=init_dir,
            initialfile=initial_filename,
            defaultextension=".json",
            filetypes=[("JSON Preset", "*.json"), ("Mọi file", "*.*")],
            title="Lưu preset cấu hình"
        )
        if not path:
            return
        try:
            extra_blurs = []
            for top_v, bot_v, str_v, lft_v, rgt_v, _ in self._extra_blur_rows:
                extra_blurs.append({
                    "top": top_v.get(),
                    "bottom": bot_v.get(),
                    "strength": str_v.get(),
                    "left": lft_v.get(),
                    "right": rgt_v.get()
                })
            
            data = {
                "font_name": self.font_name.get(),
                "font_size": self.font_size.get(),
                "font_color": self.font_color.get(),
                "outline_color": self.outline_color.get(),
                "outline_width": self.outline_width.get(),
                "sub_position": self.sub_position.get(),
                "sub_bold": self.sub_bold.get(),
                "use_free_pos": self.use_free_pos.get(),
                "pos_x": self.pos_x.get(),
                "pos_y": self.pos_y.get(),
                "sub_box": self.sub_box.get(),
                "box_color": self.box_color.get(),
                "mask_original": self.mask_original.get(),
                "mask_style": self.mask_style.get(),
                "mask_top": self.mask_top.get(),
                "mask_bottom": self.mask_bottom.get(),
                "mask_blur": self.mask_blur.get(),
                "keep_original": self.keep_original.get(),
                "bg_volume": self.bg_volume.get(),
                "dub_volume": self.dub_volume.get(),
                "voice": self.voice.get(),
                "single_voice": self.single_voice.get(),
                "enable_diarize": self.enable_diarize.get(),
                "hf_token": self.hf_token.get(),
                "tts_engine": self.tts_engine.get(),
                "capcut_rate": self.capcut_rate.get(),
                "speaker_voices": {spk: var.get() for spk, var in getattr(self, "speaker_voice_vars", {}).items()},
                "extra_blur_rows": extra_blurs
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            messagebox.showinfo("Thành công", f"Đã lưu preset thành công vào:\n{path}")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không lưu được preset: {e}")

    def load_preset(self, preset_path=None):
        """Tải cấu hình từ file JSON."""
        if not preset_path:
            init_dir = self._get_job_initialdir()
            path = filedialog.askopenfilename(
                initialdir=init_dir,
                filetypes=[("JSON Preset", "*.json"), ("Mọi file", "*.*")],
                title="Tải preset cấu hình"
            )
        else:
            path = preset_path

        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            mapping_str = {
                "font_name": self.font_name,
                "font_size": self.font_size,
                "font_color": self.font_color,
                "outline_color": self.outline_color,
                "outline_width": self.outline_width,
                "sub_position": self.sub_position,
                "pos_x": self.pos_x,
                "pos_y": self.pos_y,
                "box_color": self.box_color,
                "mask_style": self.mask_style,
                "mask_top": self.mask_top,
                "mask_bottom": self.mask_bottom,
                "mask_blur": self.mask_blur,
                "keep_original": self.keep_original,
                "voice": self.voice,
                "tts_engine": self.tts_engine,
                "hf_token": self.hf_token,
            }
            mapping_bool = {
                "sub_bold": self.sub_bold,
                "use_free_pos": self.use_free_pos,
                "sub_box": self.sub_box,
                "mask_original": self.mask_original,
                "single_voice": self.single_voice,
                "enable_diarize": self.enable_diarize,
            }
            mapping_double = {
                "bg_volume": self.bg_volume,
                "dub_volume": self.dub_volume,
                "capcut_rate": self.capcut_rate,
            }

            for k, var in mapping_str.items():
                if k in data:
                    var.set(str(data[k]))

            for k, var in mapping_bool.items():
                if k in data:
                    var.set(bool(data[k]))

            for k, var in mapping_double.items():
                if k in data:
                    var.set(float(data[k]))

            if "speaker_voices" in data and isinstance(data["speaker_voices"], dict):
                self._saved_speaker_voices = data["speaker_voices"]
                self.after(50, self.refresh_speaker_voice_ui)

            if hasattr(self, "font_color_swatch"):
                self.font_color_swatch.configure(fg_color=self.font_color.get())
            if hasattr(self, "outline_color_swatch"):
                self.outline_color_swatch.configure(fg_color=self.outline_color.get())
            if hasattr(self, "box_color_swatch"):
                self.box_color_swatch.configure(fg_color=self.box_color.get())

            if "extra_blur_rows" in data:
                for entry in list(self._extra_blur_rows):
                    entry[5].destroy()
                self._extra_blur_rows.clear()
                for eb in data["extra_blur_rows"]:
                    self._add_extra_blur_row(
                        top=str(eb.get("top", "0.0")),
                        bottom=str(eb.get("bottom", "0.15")),
                        strength=str(eb.get("strength", "20")),
                        left=str(eb.get("left", "0.0")),
                        right=str(eb.get("right", "1.0"))
                    )

            if hasattr(self, "_engine_combo_callback"):
                self._engine_combo_callback(self.tts_engine.get())

            messagebox.showinfo("Thành công", "Đã tải preset thành công!")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không đọc được file preset: {e}")

    # ── Các hàm Hỗ Trợ Micro-UX & Post-Job & Preset & Editor ──────────────────
    def open_settings_modal(self):
        """Mở modal cài đặt API & Quota riêng biệt (Mục 3.4)."""
        SettingsDialog(self)

    def open_download_dialog(self):
        """Mở modal tải video từ link (TikTok, Douyin, YouTube...) loại bỏ watermark."""
        DownloadVideoDialog(self)

    def _update_ai_status_banner(self):
        """Cập nhật huy hiệu trạng thái API Key trong Panel Phụ đề (Mục 3.4)."""
        if not hasattr(self, "ai_status_banner") or not self.ai_status_banner.winfo_exists():
            return
        eng = self.translate_engine.get().strip()
        if eng == "groq":
            key = self.groq_api_key.get().strip()
            model = self.groq_model.get().strip()
            if key:
                self.ai_status_banner.configure(
                    text=f"✔ Groq API Key: Đã sẵn sàng ({model})",
                    text_color=COLOR_SUCCESS
                )
            else:
                self.ai_status_banner.configure(
                    text=f"⚠ Groq: Chưa nhập API Key (bấm '⚙ Cấu hình Key...')",
                    text_color=COLOR_WARNING
                )
        else:
            key = self.gemini_api_key.get().strip()
            model = self.gemini_model.get().strip()
            if key:
                self.ai_status_banner.configure(
                    text=f"✔ Gemini API Key: Đã sẵn sàng ({model})",
                    text_color=COLOR_SUCCESS
                )
            else:
                self.ai_status_banner.configure(
                    text=f"⚠ Gemini: Chưa nhập API Key (bấm '⚙ Cấu hình Key...')",
                    text_color=COLOR_WARNING
                )

    def _on_files_dropped(self, files):
        """Xử lý kéo thả file trực tiếp vào app (Drag & Drop - Mục 3.1)."""
        if not files:
            return
        for f in files:
            path = f.decode("utf-8") if isinstance(f, bytes) else str(f)
            if not os.path.isfile(path):
                continue
            ext = os.path.splitext(path)[1].lower()
            if ext in [".mp4", ".mov", ".mkv", ".avi", ".webm", ".flv", ".wmv"]:
                self._current_preview_path = None
                self.video_path.set(path)
                self.status_label.configure(text=f"✔ Đã nhận file video: {os.path.basename(path)}", text_color=COLOR_SUCCESS)
                break
            elif ext == ".srt":
                if ("_goc" in path.lower() or "orig" in path.lower()) and not is_vietnamese_content(path):
                    self.orig_srt_path.set(path)
                    self.sub_editor_target.set("orig")
                    if hasattr(self, "sub_target_seg"):
                        self.sub_target_seg.set("File Gốc (.srt)")
                    self.status_label.configure(text=f"✔ Đã nhận file phụ đề gốc: {os.path.basename(path)}", text_color=COLOR_SUCCESS)
                else:
                    self.srt_path.set(path)
                    self.sub_editor_target.set("vi")
                    if hasattr(self, "sub_target_seg"):
                        self.sub_target_seg.set("Tiếng Việt (.srt)")
                    self.status_label.configure(text=f"✔ Đã nhận file phụ đề: {os.path.basename(path)}", text_color=COLOR_SUCCESS)
                self.after(100, self._load_subtitles_into_editor)
                break
            elif ext == ".json":
                try:
                    with open(path, "r", encoding="utf-8") as jf:
                        json.load(jf)
                    self.load_preset(preset_path=path)
                except Exception:
                    pass
                break

    def _on_close_window(self):
        """Lưu toàn bộ phiên làm việc khi đóng app (Mục 4)."""
        self._save_session_state()
        self.destroy()

    def _save_session_state(self):
        """Lưu trạng thái phiên làm việc hiện tại vào user_settings.json."""
        srt_save = self.srt_path.get().strip()
        if srt_save and ("_original" in srt_save.lower() or "_goc" in srt_save.lower()):
            cand_vi = srt_save.replace("_original.srt", "_vietsub.srt").replace("_goc.srt", "_vietsub.srt")
            srt_save = cand_vi if os.path.isfile(cand_vi) else ""

        state = {
            "last_video_path": "",
            "last_job_output_dir": "",
            "last_srt_path": "",
            "last_orig_srt_path": "",
            "last_output_path": "",
            "last_dubbed_video_path": "",
            "voice": self.voice.get(),
            "single_voice": self.single_voice.get(),
            "tts_engine": self.tts_engine.get(),
            "capcut_rate": self.capcut_rate.get(),
            "sub_source_mode": self.sub_source_mode.get(),
            "ocr_fps": self.ocr_fps.get(),
            "crop_left": self.crop_left.get(),
            "crop_right": self.crop_right.get(),
            "whisper_model": self.whisper_model.get(),
            "enable_diarize": self.enable_diarize.get(),
            "keep_original": self.keep_original.get(),
            "bg_volume": self.bg_volume.get(),
            "dub_volume": self.dub_volume.get(),
            "mask_original": self.mask_original.get(),
            "mask_style": self.mask_style.get(),
            "mask_top": self.mask_top.get(),
            "mask_bottom": self.mask_bottom.get(),
            "mask_blur": self.mask_blur.get(),
            "video_encoder": self.video_encoder.get(),
            "export_preset": self.export_preset.get(),
            "translate_engine": self.translate_engine.get(),
            "gemini_api_key": self.gemini_api_key.get(),
            "gemini_model": self.gemini_model.get(),
            "groq_api_key": self.groq_api_key.get(),
            "groq_model": self.groq_model.get(),
            "hf_token": self.hf_token.get(),
            "font_name": self.font_name.get(),
            "font_size": self.font_size.get(),
            "font_color": self.font_color.get(),
            "outline_color": self.outline_color.get(),
            "outline_width": self.outline_width.get(),
            "sub_position": self.sub_position.get(),
            "sub_bold": self.sub_bold.get(),
            "use_free_pos": self.use_free_pos.get(),
            "pos_x": self.pos_x.get(),
            "pos_y": self.pos_y.get(),
            "sub_box": self.sub_box.get(),
            "box_color": self.box_color.get(),
            "speaker_voices": {spk: var.get() for spk, var in getattr(self, "speaker_voice_vars", {}).items()}
        }
        self._save_app_settings(state)

    def _apply_platform_preset(self, pkey):
        """Áp dụng bộ thông số preset nền tảng thông minh (Mục 4)."""
        if pkey == "tiktok":
            self.font_size.set("20")
            self.sub_bold.set(True)
            self.font_color.set("white")
            self.outline_color.set("black")
            self.outline_width.set("3")
            self.use_free_pos.set(True)
            self.pos_x.set("0.5")
            self.pos_y.set("0.78")
            self.sub_box.set(False)
            self.mask_original.set(True)
            self.mask_style.set("blur")
            self.mask_top.set("0.72")
            self.mask_bottom.set("0.92")
            self.mask_blur.set("25")
            self.status_label.configure(text="✔ Đã áp dụng preset TikTok / Shorts (9:16)", text_color=COLOR_SUCCESS)
        elif pkey == "youtube":
            self.font_size.set("16")
            self.sub_bold.set(False)
            self.font_color.set("white")
            self.outline_color.set("black")
            self.outline_width.set("2")
            self.use_free_pos.set(False)
            self.sub_position.set("bottom")
            self.sub_box.set(False)
            self.mask_original.set(False)
            self.status_label.configure(text="✔ Đã áp dụng preset YouTube Chuẩn (16:9)", text_color=COLOR_SUCCESS)
        elif pkey == "cinematic":
            self.font_size.set("15")
            self.sub_bold.set(False)
            self.font_color.set("#FFE57F")
            self.outline_color.set("#111111")
            self.outline_width.set("2")
            self.use_free_pos.set(True)
            self.pos_x.set("0.5")
            self.pos_y.set("0.90")
            self.sub_box.set(False)
            self.status_label.configure(text="✔ Đã áp dụng preset Điện ảnh (Cinematic)", text_color=COLOR_SUCCESS)
        elif pkey == "dub_only":
            self.keep_original.set("voiceover")
            self.bg_volume.set(0.15)
            self.dub_volume.set(1.0)
            self.status_label.configure(text="✔ Đã áp dụng preset Chỉ Thuyết minh", text_color=COLOR_SUCCESS)
        elif pkey == "sub_only":
            self.keep_original.set("custom")
            self.bg_volume.set(1.0)
            self.dub_volume.set(0.0)
            self.status_label.configure(text="✔ Đã áp dụng preset Chỉ Vietsub (Giữ âm gốc 100%)", text_color=COLOR_SUCCESS)

        if hasattr(self, "font_color_swatch"):
            self.font_color_swatch.configure(fg_color=self.font_color.get())
        if hasattr(self, "outline_color_swatch"):
            self.outline_color_swatch.configure(fg_color=self.outline_color.get())
        if hasattr(self, "_pos_editor_sync_from_vars"):
            self._pos_editor_sync_from_vars()
        if hasattr(self, "_show_custom_row"):
            self._show_custom_row(self.keep_original.get())

    def _show_post_job_success(self, target_file):
        """Hiển thị thẻ thành công nổi bật kèm 3 nút hành động sau khi render xong (Mục 3.3)."""
        if not target_file:
            return
        self._last_completed_file = target_file
        self._switch_tab("export")
        if hasattr(self, "post_job_card"):
            self.post_job_card.pack(fill="x", padx=10, pady=(4, 12), before=self.card5a)
            fname = os.path.basename(target_file)
            self.post_job_file_lbl.configure(text=f"📁 File đã xuất: {fname}\n{target_file}")

    def _play_completed_video(self):
        f = getattr(self, "_last_completed_file", None) or self.output_path.get().strip() or self.dubbed_video_path.get().strip()
        if f and os.path.isfile(f):
            open_with_default_app(f)
        else:
            messagebox.showwarning("File không tồn tại", "Chưa tìm thấy file video kết quả.")

    def _open_completed_folder(self):
        f = getattr(self, "_last_completed_file", None) or self.output_path.get().strip() or self.dubbed_video_path.get().strip()
        if f and os.path.isfile(f):
            if platform.system() == "Windows":
                subprocess.run(["explorer", f"/select,{os.path.normpath(f)}"])
            else:
                open_with_default_app(os.path.dirname(f))
        else:
            fdir = self._get_job_initialdir()
            if fdir and os.path.isdir(fdir):
                open_with_default_app(fdir)

    def _copy_completed_path(self):
        f = getattr(self, "_last_completed_file", None) or self.output_path.get().strip() or self.dubbed_video_path.get().strip()
        if f:
            self.clipboard_clear()
            self.clipboard_append(f)
            self.status_label.configure(text="✔ Đã sao chép đường dẫn file vào clipboard!", text_color=COLOR_SUCCESS)
            messagebox.showinfo("Đã chép", f"Đã sao chép đường dẫn file vào Clipboard:\n{f}")

    def _share_to_phone(self):
        f = getattr(self, "_last_completed_file", None) or self.output_path.get().strip() or self.dubbed_video_path.get().strip() or (self.video_path.get().strip() if hasattr(self, "video_path") else "")
        if f and os.path.isfile(f):
            PhoneShareDialog(self, f)
        else:
            messagebox.showwarning("File không tồn tại", "Chưa tìm thấy file video để gửi sang điện thoại.\nHãy chọn hoặc xuất 1 video trước.")

    def _load_subtitles_into_editor(self, force=False):
        """Nạp danh sách câu phụ đề từ file SRT vào Quick-Editor (có bộ nhớ đệm chống vẽ lại trùng lặp)."""
        if not hasattr(self, "sub_editor_scroll") or not self.sub_editor_scroll.winfo_exists():
            return
        target = self.sub_editor_target.get()
        vid = self.video_path.get().strip() if hasattr(self, "video_path") else ""
        base = os.path.splitext(os.path.basename(vid))[0] if vid else ""

        check_dirs = []
        if hasattr(self, "job_output_dir") and self.job_output_dir.get().strip():
            check_dirs.append(self.job_output_dir.get().strip())
        if vid:
            check_dirs.append(os.path.dirname(vid))

        if target == "vi":
            file_path = self.srt_path.get().strip()
            if file_path and os.path.isdir(file_path):
                check_dirs.insert(0, file_path)
                file_path = ""

            is_orig_misplaced = bool(file_path and ("_original" in file_path.lower() or "_goc" in file_path.lower()) and not is_vietnamese_content(file_path))
            if not file_path or not os.path.isfile(file_path) or is_orig_misplaced:
                found = None
                if not base and self.orig_srt_path.get().strip():
                    o_name = os.path.splitext(os.path.basename(self.orig_srt_path.get().strip()))[0]
                    base = o_name.replace("_original", "").replace("_goc", "")

                for d in check_dirs:
                    if not os.path.isdir(d):
                        continue
                    if base:
                        cand = os.path.join(d, f"{base}_vietsub.srt")
                        if os.path.isfile(cand):
                            found = cand
                            break
                    for f in os.listdir(d):
                        fl = f.lower()
                        if fl.endswith(".srt") and "vietsub" in fl:
                            if not base or fl.startswith(base.lower()):
                                found = os.path.join(d, f)
                                break
                    if found:
                        break

                # Tự động đồng bộ nếu file gốc orig_srt_path đã được người dùng dịch/lưu tiếng Việt vào
                orig_p = self.orig_srt_path.get().strip()
                if orig_p and os.path.isfile(orig_p) and is_vietnamese_content(orig_p):
                    out_d = self._get_job_initialdir() or (check_dirs[0] if (check_dirs and os.path.isdir(check_dirs[0])) else os.path.dirname(orig_p))
                    target_vi = os.path.join(out_d, f"{base}_vietsub.srt") if base else orig_p.replace("_original.srt", "_vietsub.srt").replace("_goc.srt", "_vietsub.srt")
                    if not found or not os.path.exists(found) or (os.path.exists(orig_p) and os.path.getmtime(orig_p) > os.path.getmtime(found)):
                        try:
                            shutil.copyfile(orig_p, target_vi)
                            found = target_vi
                            if hasattr(self, "status_label"):
                                self.status_label.configure(text="✔ Phát hiện tiếng Việt trong file gốc: Đã tự động đồng bộ sang Vietsub!", text_color=COLOR_SUCCESS)
                        except Exception:
                            pass

                if found:
                    file_path = found
                    self.srt_path.set(found)
                elif is_orig_misplaced:
                    file_path = None
        else:
            file_path = self.orig_srt_path.get().strip()
            if file_path and os.path.isdir(file_path):
                check_dirs.insert(0, file_path)
                file_path = ""

            is_vi_misplaced = bool(file_path and "vietsub" in file_path.lower())
            if not file_path or not os.path.isfile(file_path) or is_vi_misplaced:
                found = None
                for d in check_dirs:
                    if not os.path.isdir(d):
                        continue
                    if base:
                        for cand_name in [f"{base}_original.srt", f"{base}_goc.srt"]:
                            cand = os.path.join(d, cand_name)
                            if os.path.isfile(cand):
                                found = cand
                                break
                        if found:
                            break
                    for f in os.listdir(d):
                        fl = f.lower()
                        if fl.endswith(".srt") and ("orig" in fl or "goc" in fl):
                            if not base or fl.startswith(base.lower()):
                                found = os.path.join(d, f)
                                break
                    if found:
                        break

                if found:
                    file_path = found
                    self.orig_srt_path.set(found)
                elif is_vi_misplaced:
                    file_path = None

        if not file_path or not os.path.isfile(file_path):
            self._all_subs_data = []
            self._editor_sub_entries = []
            self._sub_current_page = 0
            self._render_subtitle_page(0, sync=False)
            if hasattr(self, "sub_count_lbl"):
                self.sub_count_lbl.configure(text="")
            self._current_loaded_sub_path = None
            self._current_loaded_sub_mtime = 0
            self._current_loaded_sub_target = None
            return

        try:
            mtime = os.path.getmtime(file_path)
            if (not force and
                getattr(self, "_current_loaded_sub_path", None) == file_path and
                getattr(self, "_current_loaded_sub_mtime", 0) == mtime and
                getattr(self, "_current_loaded_sub_target", None) == target and
                getattr(self, "_all_subs_data", None)):
                return
        except Exception:
            mtime = 0

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            import srt
            subs = list(srt.parse(content))
            from core.burning import sanitize_subtitles
            subs = sanitize_subtitles(subs)
            self._all_subs_data = subs
            self._editor_sub_entries = []
            if hasattr(self, "sub_count_lbl"):
                self.sub_count_lbl.configure(text=f"({len(subs)} câu)")

            self._sub_current_page = 0
            self._render_subtitle_page(0, sync=False)
            self._current_loaded_sub_path = file_path
            self._current_loaded_sub_mtime = mtime
            self._current_loaded_sub_target = target
            if hasattr(self, "status_label"):
                self.status_label.configure(text=f"✔ Đã nạp {len(subs)} câu từ: {os.path.basename(file_path)}", text_color=COLOR_SUCCESS)

        except Exception as e:
            for w in self.sub_editor_scroll.winfo_children():
                w.destroy()
            self._editor_sub_entries = []
            self._current_loaded_sub_path = None
            self._current_loaded_sub_mtime = 0
            self._current_loaded_sub_target = None
            ctk.CTkLabel(self.sub_editor_scroll, text=f"Lỗi đọc file phụ đề: {e}", text_color=COLOR_DANGER).pack(pady=20)
            if hasattr(self, "sub_count_lbl"):
                self.sub_count_lbl.configure(text="(Lỗi)")

    def _sync_current_page_subtitles(self):
        """Đồng bộ nội dung các ô chữ trên trang hiện tại vào mảng _all_subs_data trước khi chuyển trang hoặc lưu."""
        if not getattr(self, "_editor_sub_entries", None) or not getattr(self, "_all_subs_data", None):
            return
        for item in self._editor_sub_entries:
            if len(item) >= 4:
                sub, entry, card, g_idx = item
                if 0 <= g_idx < len(self._all_subs_data):
                    if isinstance(entry, ctk.CTkTextbox):
                        val = entry.get("1.0", "end-1c").strip()
                    else:
                        val = entry.get().strip()
                    self._all_subs_data[g_idx].content = val

    def _render_subtitle_page(self, page_idx=0, sync=True):
        """Hiển thị danh sách câu phụ đề theo từng trang (mỗi trang 50 câu) để triệt tiêu lỗi tràn toạ độ 32k px của Tkinter."""
        if sync:
            self._sync_current_page_subtitles()

        total = len(getattr(self, "_all_subs_data", []))
        page_size = getattr(self, "_sub_page_size", 50)
        total_pages = max(1, (total + page_size - 1) // page_size)
        page_idx = max(0, min(page_idx, total_pages - 1))
        self._sub_current_page = page_idx

        # Cập nhật thanh công cụ phân trang
        if hasattr(self, "lbl_sub_page_info"):
            if total == 0:
                self.lbl_sub_page_info.configure(text="0 câu")
                if hasattr(self, "btn_sub_prev_page"):
                    self.btn_sub_prev_page.configure(state="disabled")
                if hasattr(self, "btn_sub_next_page"):
                    self.btn_sub_next_page.configure(state="disabled")
            else:
                start_disp = page_idx * page_size + 1
                end_disp = min(total, (page_idx + 1) * page_size)
                self.lbl_sub_page_info.configure(
                    text=f"Trang {page_idx + 1}/{total_pages} ({start_disp}➔{end_disp})"
                )
                if hasattr(self, "btn_sub_prev_page"):
                    self.btn_sub_prev_page.configure(state="normal" if page_idx > 0 else "disabled")
                if hasattr(self, "btn_sub_next_page"):
                    self.btn_sub_next_page.configure(state="normal" if page_idx < total_pages - 1 else "disabled")

        for w in self.sub_editor_scroll.winfo_children():
            w.destroy()
        self._editor_sub_entries = []

        if total == 0:
            target = getattr(self, "sub_editor_target", None)
            target_str = target.get() if target else "vi"
            if target_str == "vi":
                empty_msg = "Chưa có file phụ đề tiếng Việt.\nHãy bấm '🌐 Dịch Phụ Đề' hoặc chọn file Vietsub (.srt)."
            else:
                empty_msg = "Chưa có file phụ đề gốc.\nHãy bấm '⚡ Lấy phụ đề gốc' hoặc chọn file gốc (.srt)."
            lbl = ctk.CTkLabel(
                self.sub_editor_scroll,
                text=empty_msg,
                text_color=COLOR_TEXT_MUTED, font=FONT_LABEL()
            )
            lbl.pack(pady=40)
            return

        start_i = page_idx * page_size
        end_i = min(total, start_i + page_size)

        for g_idx in range(start_i, end_i):
            sub = self._all_subs_data[g_idx]
            start_s = sub.start.total_seconds()
            end_s = sub.end.total_seconds()
            start_str = f"{int(start_s//60):02d}:{start_s%60:05.2f}"
            end_str = f"{int(end_s//60):02d}:{end_s%60:05.2f}"

            row = ctk.CTkFrame(self.sub_editor_scroll, fg_color="#202022", corner_radius=6)
            row.pack(fill="x", padx=2, pady=3)

            top_line = ctk.CTkFrame(row, fg_color="transparent")
            top_line.pack(fill="x", padx=6, pady=(4, 2))

            lbl_idx = ctk.CTkLabel(
                top_line,
                text=f"#{sub.index} [{start_str}➔{end_str}]",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=COLOR_ACCENT
            )
            lbl_idx.pack(side="left")

            btn_jump = ctk.CTkButton(
                top_line, text="▶", width=30, height=20,
                font=ctk.CTkFont(size=10), **OUTLINE_BTN,
                command=lambda i=g_idx: self._select_subtitle_by_index(i)
            )
            btn_jump.pack(side="right")

            clean_text = sub.content.strip()
            text_lines = clean_text.splitlines()
            est_lines = 0
            for tl in text_lines:
                est_lines += max(1, (len(tl) + 31) // 32)
            est_lines = max(1, min(est_lines, 5))

            if est_lines == 1:
                box_h = 32
            elif est_lines == 2:
                box_h = 50
            elif est_lines == 3:
                box_h = 68
            else:
                box_h = 86

            txt = ctk.CTkTextbox(
                row,
                height=box_h,
                wrap="word",
                font=ctk.CTkFont(size=12),
                fg_color="#18181A",
                border_width=1,
                border_color="#333336",
                activate_scrollbars=False
            )
            txt.insert("1.0", clean_text)
            txt.pack(fill="x", padx=6, pady=(0, 6))

            row.bind("<Button-1>", lambda e=None, i=g_idx: self._select_subtitle_by_index(i))
            lbl_idx.bind("<Button-1>", lambda e=None, i=g_idx: self._select_subtitle_by_index(i))
            txt.bind("<FocusIn>", lambda e=None, i=g_idx: self._select_subtitle_by_index(i))

            self._editor_sub_entries.append((sub, txt, row, g_idx))

        try:
            self.sub_editor_scroll._parent_canvas.yview_moveto(0.0)
        except Exception:
            pass

    def _sub_prev_page(self):
        if not getattr(self, "_all_subs_data", None):
            return
        if getattr(self, "_sub_current_page", 0) > 0:
            self._render_subtitle_page(self._sub_current_page - 1)

    def _sub_next_page(self):
        if not getattr(self, "_all_subs_data", None):
            return
        total = len(self._all_subs_data)
        page_size = getattr(self, "_sub_page_size", 50)
        total_pages = max(1, (total + page_size - 1) // page_size)
        if getattr(self, "_sub_current_page", 0) < total_pages - 1:
            self._render_subtitle_page(self._sub_current_page + 1)

    def _sub_jump_to_number(self):
        if not hasattr(self, "sub_jump_entry") or not getattr(self, "_all_subs_data", None):
            return
        val = self.sub_jump_entry.get().strip()
        if not val:
            return
        try:
            num = int(val)
            target_idx = -1
            for i, s in enumerate(self._all_subs_data):
                if s.index == num:
                    target_idx = i
                    break
            if target_idx == -1 and 1 <= num <= len(self._all_subs_data):
                target_idx = num - 1
            if target_idx != -1:
                self._select_subtitle_by_index(target_idx)
        except ValueError:
            pass

    def _select_subtitle_by_index(self, idx):
        if not getattr(self, "_all_subs_data", None) or not (0 <= idx < len(self._all_subs_data)):
            return
        self._current_sub_index = idx

        target_page = idx // getattr(self, "_sub_page_size", 50)
        if target_page != getattr(self, "_sub_current_page", 0):
            self._render_subtitle_page(target_page)

        for item in self._editor_sub_entries:
            card = item[2]
            g_i = item[3] if len(item) >= 4 else -1
            if g_i == idx:
                card.configure(fg_color="#1E3A8A", border_width=1, border_color=COLOR_ACCENT)
                try:
                    local_pos = self._editor_sub_entries.index(item)
                    frac = max(0.0, min(1.0, (local_pos - 1) / max(1, len(self._editor_sub_entries))))
                    self.sub_editor_scroll._parent_canvas.yview_moveto(frac)
                except Exception:
                    pass
            else:
                card.configure(fg_color="#202022", border_width=0)

        sub = self._all_subs_data[idx]
        start_s = sub.start.total_seconds()
        self._sub_editor_jump_to_sec(start_s)
        self._pos_editor_sync_from_vars()

    def _prev_subtitle(self):
        if not getattr(self, "_all_subs_data", None):
            return
        idx = max(0, getattr(self, "_current_sub_index", 0) - 1)
        self._select_subtitle_by_index(idx)

    def _next_subtitle(self):
        if not getattr(self, "_all_subs_data", None):
            return
        idx = min(len(self._all_subs_data) - 1, getattr(self, "_current_sub_index", 0) + 1)
        self._select_subtitle_by_index(idx)

    def _save_subtitles_from_editor(self):
        """Lưu toàn bộ thay đổi câu chữ từ Quick-Editor vào file SRT."""
        target = self.sub_editor_target.get()
        file_path = self.orig_srt_path.get().strip() if target == "orig" else self.srt_path.get().strip()
        if not file_path or not getattr(self, "_all_subs_data", None):
            messagebox.showwarning("Không có dữ liệu", "Không có nội dung phụ đề nào để lưu.")
            return

        self._sync_current_page_subtitles()

        try:
            from core.burning import sanitize_subtitles
            self._all_subs_data = sanitize_subtitles(self._all_subs_data)

            import srt
            new_content = srt.compose(self._all_subs_data)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            # Nếu đang ở tab File Gốc nhưng nội dung lại chứa tiếng Việt -> tự động đồng bộ sang Vietsub
            if target == "orig" and is_vietnamese_content(new_content):
                vi_path = self.srt_path.get().strip()
                if not vi_path or "_original" in vi_path.lower() or "_goc" in vi_path.lower():
                    out_d = self._get_job_initialdir() or os.path.dirname(file_path)
                    v_p = self.video_path.get().strip() if hasattr(self, "video_path") else ""
                    base = os.path.splitext(os.path.basename(v_p))[0] if v_p else os.path.splitext(os.path.basename(file_path))[0].replace("_original", "").replace("_goc", "")
                    vi_path = os.path.join(out_d, f"{base}_vietsub.srt")
                    self.srt_path.set(vi_path)
                try:
                    with open(vi_path, "w", encoding="utf-8") as vf:
                        vf.write(new_content)
                except Exception:
                    pass

            fname = os.path.basename(file_path)
            extra_msg = "\n(Phát hiện tiếng Việt: Đã tự động đồng bộ sang file Vietsub để sẵn sàng lồng tiếng!)" if (target == "orig" and is_vietnamese_content(new_content)) else ""
            self.status_label.configure(text=f"✔ Đã lưu {len(self._all_subs_data)} câu vào {fname}", text_color=COLOR_SUCCESS)
            try:
                self._current_loaded_sub_mtime = os.path.getmtime(file_path)
            except Exception:
                pass
            messagebox.showinfo("Đã lưu", f"Đã lưu thành công {len(self._all_subs_data)} câu vào file:\n{file_path}{extra_msg}")
            self.after(50, self.refresh_speaker_voice_ui)
        except Exception as e:
            messagebox.showerror("Lỗi khi lưu", f"Không thể lưu file phụ đề:\n{e}")

    def _shift_subtitles_timing(self, delta_ms: int):
        """Dịch chuyển toàn bộ timeline phụ đề (start & end) thêm delta_ms (+ là trễ hơn để khớp miệng, - là sớm hơn)."""
        target = self.sub_editor_target.get()
        file_path = self.orig_srt_path.get().strip() if target == "orig" else self.srt_path.get().strip()
        if not file_path or not getattr(self, "_all_subs_data", None) or len(self._all_subs_data) == 0:
            messagebox.showwarning("Chưa có phụ đề", "Vui lòng mở hoặc nạp phụ đề trước khi dịch chuyển timeline.")
            return

        self._sync_current_page_subtitles()
        import datetime
        delta = datetime.timedelta(milliseconds=delta_ms)
        for sub in self._all_subs_data:
            new_start = sub.start + delta
            if new_start < datetime.timedelta(0):
                new_start = datetime.timedelta(0)
            new_end = sub.end + delta
            if new_end <= new_start:
                new_end = new_start + datetime.timedelta(milliseconds=500)
            sub.start = new_start
            sub.end = new_end

        try:
            from core.burning import sanitize_subtitles
            self._all_subs_data = sanitize_subtitles(self._all_subs_data)
            import srt
            new_content = srt.compose(self._all_subs_data)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            self._current_loaded_sub_mtime = os.path.getmtime(file_path)
            self._render_current_page_subtitles()
            sign = "+" if delta_ms >= 0 else ""
            fname = os.path.basename(file_path)
            self.status_label.configure(
                text=f"✔ Đã dịch chuyển toàn bộ phụ đề {sign}{delta_ms}ms ({fname})",
                text_color=COLOR_SUCCESS
            )
            messagebox.showinfo(
                "Khớp miệng",
                f"✔ Đã dịch chuyển toàn bộ {len(self._all_subs_data)} câu phụ đề: {sign}{delta_ms}ms!\n\n"
                f"File đã cập nhật: {fname}\n"
                f"(Ví dụ: câu từ 00:01.200 sẽ chuyển thành 00:01.{max(0, 200+delta_ms):03d})"
            )
        except Exception as e:
            messagebox.showerror("Lỗi khi lưu", f"Không thể lưu file phụ đề sau khi dịch timeline:\n{e}")

    def _prompt_shift_timing(self):
        """Hộp thoại nhập số mili-giây tùy ý để dịch chuyển timeline."""
        target = self.sub_editor_target.get()
        file_path = self.orig_srt_path.get().strip() if target == "orig" else self.srt_path.get().strip()
        if not file_path or not getattr(self, "_all_subs_data", None) or len(self._all_subs_data) == 0:
            messagebox.showwarning("Chưa có phụ đề", "Vui lòng mở hoặc nạp phụ đề trước khi dịch chuyển timeline.")
            return

        dialog = ctk.CTkInputDialog(
            text="Nhập số mili-giây (ms) muốn dịch chuyển:\n\n"
                 "• Nhập số dương (VD: 100, 150): để phụ đề xuất hiện TRỄ hơn (khớp miệng).\n"
                 "• Nhập số âm (VD: -100): để phụ đề xuất hiện SỚM hơn.",
            title="Dịch Chuyển Timeline Khớp Miệng"
        )
        val = dialog.get_input()
        if val:
            try:
                ms = int(val.strip().replace("+", ""))
                if ms != 0:
                    self._shift_subtitles_timing(ms)
            except ValueError:
                messagebox.showerror("Sai định dạng", "Vui lòng nhập một số nguyên (ví dụ: 100, 150, -100).")

    def _sub_editor_jump_to_sec(self, sec):
        """Nhảy thời gian xem preview video tới giây của câu phụ đề đó."""
        sec_val = max(0.0, float(sec))
        self.preview_seek_sec.set(f"{sec_val:.1f}")
        self.pos_editor_seek_var.set(f"{sec_val:.1f}")
        v_path = self.video_path.get().strip()
        if v_path and os.path.isfile(v_path):
            if getattr(self, "_pos_editor_mode", "drag") == "real":
                self._pos_editor_render_true_frame()
            elif hasattr(self, "_pos_editor_refresh_frame"):
                self._pos_editor_refresh_frame()
            self.status_label.configure(text=f"▶ Khung tại giây {sec_val:.1f}", text_color=COLOR_ACCENT)

    # ── Các hàm xử lý Vùng Làm Mờ Tuỳ Chỉnh ──────────────────────────────────
    def _add_extra_blur_row(self, top="0.0", bottom="0.15", strength="20", left="0.0", right="1.0"):
        top_var = tk.StringVar(value=top)
        bot_var = tk.StringVar(value=bottom)
        str_var = tk.StringVar(value=strength)
        lft_var = tk.StringVar(value=left)
        rgt_var = tk.StringVar(value=right)

        row = ctk.CTkFrame(self._eb_list_frame)
        row.pack(fill="x", pady=3, padx=2)

        info_lbl = ctk.CTkLabel(row, text="", font=FONT_LABEL())
        info_lbl.pack(side="left", padx=8, pady=4)

        def update_row_lbl(*_):
            info_lbl.configure(
                text=f"Top: {top_var.get()} → Bottom: {bot_var.get()} | Độ mờ: {str_var.get()} | Left: {lft_var.get()} → Right: {rgt_var.get()}"
            )
            self._pos_editor_sync_from_vars()

        for v in [top_var, bot_var, str_var, lft_var, rgt_var]:
            v.trace_add("write", update_row_lbl)

        update_row_lbl()

        entry = (top_var, bot_var, str_var, lft_var, rgt_var, row)
        self._extra_blur_rows.append(entry)

        ctk.CTkButton(row, text="✕", width=28, height=24, **DANGER_BTN,
                      command=lambda e=entry: self._remove_extra_blur_row(e)).pack(side="right", padx=6, pady=4)

        self._pos_editor_sync_from_vars()

    def _remove_extra_blur_row(self, entry):
        if entry in self._extra_blur_rows:
            self._extra_blur_rows.remove(entry)
            entry[5].destroy()
            self._pos_editor_sync_from_vars()

    def _extra_blur_args(self):
        args = []
        for top_v, bot_v, str_v, lft_v, rgt_v, _ in self._extra_blur_rows:
            try:
                t = float(top_v.get()); b = float(bot_v.get()); s = int(str_v.get())
                l = float(lft_v.get()); r = float(rgt_v.get())
                if 0 <= t < b <= 1 and s > 0 and 0 <= l < r <= 1:
                    args += ["--extra-blur", f"{t},{b},{s},{l},{r}"]
                else:
                    self.log_write(f"  ⚠ Bỏ qua vùng blur không hợp lệ: top={t}, bottom={b}, strength={s}\n")
            except ValueError:
                pass
        return args

    def _export_args(self):
        args = []
        enc_map = {
            "Tự động (GPU QuickSync/MF/NVENC)": "auto",
            "Intel QSV (GPU)": "qsv",
            "Media Foundation (GPU)": "mf",
            "NVIDIA NVENC (GPU)": "nvenc",
            "CPU (libx264)": "cpu"
        }
        enc_val = getattr(self, "video_encoder", None)
        if enc_val:
            raw_v = enc_val.get()
            enc = enc_map.get(raw_v, raw_v)
            if enc:
                args += ["--video-encoder", enc]

        preset_map = {
            "Rất nhanh (veryfast - Mặc định)": "veryfast",
            "Cực nhanh (ultrafast)": "ultrafast",
            "Cân bằng (fast)": "fast",
            "Chất lượng cao (medium)": "medium"
        }
        pre_val = getattr(self, "export_preset", None)
        if pre_val:
            raw_p = pre_val.get()
            preset = preset_map.get(raw_p, raw_p)
            if preset:
                args += ["--export-preset", preset]
        return args

    def _pick_color(self, var, swatch_widget):
        initial = var.get() if var.get().startswith("#") else None
        color = colorchooser.askcolor(color=initial, title="Chọn màu")
        if color and color[1]:
            var.set(color[1])
            swatch_widget.configure(fg_color=color[1])

    def _scan_system_fonts(self):
        """Quét font chữ có trên hệ thống và cập nhật danh sách ComboBox."""
        if self._system_fonts_scanned:
            messagebox.showinfo("Font hệ thống", "Đã quét rồi — danh sách font đã được cập nhật trong dropdown.")
            return

        self.btn_scan_fonts.configure(state="disabled", text="⏳ Đang quét...")

        def worker():
            found_fonts = set()
            system = platform.system()
            try:
                if system == "Windows":
                    # Đọc font từ Windows Registry
                    import winreg
                    reg_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"
                    try:
                        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path)
                        i = 0
                        while True:
                            try:
                                name, _, _ = winreg.EnumValue(key, i)
                                # Tên font trong registry dạng "Arial (TrueType)" → lấy phần trước ngoặc
                                clean = name.split("(")[0].strip()
                                if clean:
                                    found_fonts.add(clean)
                                i += 1
                            except OSError:
                                break
                        winreg.CloseKey(key)
                    except OSError:
                        pass
                elif system == "Darwin":
                    # macOS: dùng system_profiler hoặc liệt kê thư mục font
                    font_dirs = [
                        "/System/Library/Fonts",
                        "/Library/Fonts",
                        os.path.expanduser("~/Library/Fonts"),
                    ]
                    for d in font_dirs:
                        if os.path.isdir(d):
                            for f in os.listdir(d):
                                name = os.path.splitext(f)[0]
                                # Bỏ hậu tố style phổ biến
                                for suffix in ["-Regular", "-Bold", "-Italic", "-Light", "-Medium", "-Thin",
                                               "-BoldItalic", "-SemiBold", "-ExtraBold", "-Black"]:
                                    if name.endswith(suffix):
                                        name = name[:-len(suffix)]
                                        break
                                if name:
                                    found_fonts.add(name)
                else:
                    # Linux: dùng fc-list
                    try:
                        result = subprocess.run(
                            ["fc-list", "--format", "%{family}\n"],
                            capture_output=True, encoding="utf-8", errors="replace", timeout=15
                        )
                        for line in result.stdout.strip().splitlines():
                            # fc-list trả về "FontFamily,AltName" → lấy tên đầu
                            name = line.split(",")[0].strip()
                            if name:
                                found_fonts.add(name)
                    except (FileNotFoundError, subprocess.TimeoutExpired):
                        pass
            except Exception:
                pass

            # Merge với preset fonts
            all_fonts = sorted(set(self._preset_fonts) | found_fonts, key=lambda s: s.lower())

            def update_ui():
                try:
                    self._preset_fonts = all_fonts
                    self._system_fonts_scanned = True
                    if hasattr(self, "font_combo") and self.font_combo.winfo_exists():
                        self.font_combo.configure(values=all_fonts)
                    self.btn_scan_fonts.configure(state="normal", text=f"✔ {len(all_fonts)} font")
                    self.log_write(f"  ✔ Đã quét được {len(found_fonts)} font hệ thống (tổng cộng {len(all_fonts)} font trong danh sách)\n")
                except Exception:
                    pass

            self.after(0, update_ui)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def log_write(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if lines:
            last_line = lines[-1]
            if len(last_line) > 80:
                last_line = last_line[:77] + "..."

    # ── Tự động phát hiện & Khởi tạo phiên làm việc ──────────────────────────
    def _auto_detect_job_files(self, video_path):
        """Tự động phát hiện và liên kết các file phụ đề gốc, vietsub ĐÚNG của video này."""
        if not video_path or not os.path.isfile(video_path):
            return
        video_dir = os.path.dirname(video_path)
        base = os.path.splitext(os.path.basename(video_path))[0]
        out_folder = os.path.join(video_dir, f"{base}_output")
        os.makedirs(out_folder, exist_ok=True)

        # Cập nhật thư mục đầu ra và các file xuất theo video này - TẤT CẢ CHUNG 1 FOLDER
        self.job_output_dir.set(out_folder)
        orig_target = os.path.join(out_folder, f"{base}_original.srt")
        vi_target = os.path.join(out_folder, f"{base}_vietsub.srt")
        dub_target = os.path.join(out_folder, f"{base}_dalongtieng.mp4")
        out_target = os.path.join(out_folder, f"{base}_output.mp4")

        self.output_path.set(out_target)
        self.dubbed_video_path.set(dub_target)
        self._last_completed_file = None
        if hasattr(self, "post_job_card") and self.post_job_card.winfo_ismapped():
            self.post_job_card.pack_forget()

        # 1. Tìm file phụ đề gốc (original / goc) - ưu tiên trong out_folder
        orig_found = None
        if os.path.isfile(orig_target):
            orig_found = orig_target
        elif os.path.isfile(os.path.join(out_folder, f"{base}_goc.srt")):
            orig_found = os.path.join(out_folder, f"{base}_goc.srt")
        else:
            # Quét video_dir phòng phiên cũ lưu ở ngoài -> đồng bộ vào out_folder
            for cand_name in [f"{base}_original.srt", f"{base}_goc.srt", f"{base}.srt"]:
                c = os.path.join(video_dir, cand_name)
                if os.path.isfile(c):
                    try:
                        shutil.copyfile(c, orig_target)
                        orig_found = orig_target
                    except Exception:
                        orig_found = c
                    break

        if orig_found:
            self.orig_srt_path.set(orig_found)
        else:
            self.orig_srt_path.set(orig_target)

        # 2. Tìm file phụ đề Vietsub - ưu tiên trong out_folder
        vi_found = None
        if os.path.isfile(vi_target):
            vi_found = vi_target
        elif os.path.isfile(os.path.join(out_folder, f"{base}_vi.srt")):
            vi_found = os.path.join(out_folder, f"{base}_vi.srt")
        else:
            # Quét video_dir phòng phiên cũ lưu ở ngoài -> đồng bộ vào out_folder
            for cand_name in [f"{base}_vietsub.srt", f"{base}_vi.srt"]:
                c = os.path.join(video_dir, cand_name)
                if os.path.isfile(c):
                    try:
                        shutil.copyfile(c, vi_target)
                        vi_found = vi_target
                    except Exception:
                        vi_found = c
                    break

        # Nếu chưa tìm thấy file Vietsub riêng, nhưng file gốc lại chứa tiếng Việt (do dịch ngoài và lưu đè)
        if not vi_found and orig_found and is_vietnamese_content(orig_found):
            try:
                shutil.copyfile(orig_found, vi_target)
                vi_found = vi_target
            except Exception:
                pass

        if vi_found:
            self.srt_path.set(vi_found)
        else:
            self.srt_path.set(vi_target)

        # 3. Chọn tab phụ đề hiển thị
        has_vi = os.path.isfile(self.srt_path.get().strip())
        has_orig = os.path.isfile(self.orig_srt_path.get().strip())

        if has_vi:
            self.sub_editor_target.set("vi")
            if hasattr(self, "sub_target_seg"):
                self.sub_target_seg.set("Tiếng Việt (.srt)")
        elif has_orig:
            self.sub_editor_target.set("orig")
            if hasattr(self, "sub_target_seg"):
                self.sub_target_seg.set("File Gốc (.srt)")
        else:
            self.sub_editor_target.set("vi")
            if hasattr(self, "sub_target_seg"):
                self.sub_target_seg.set("Tiếng Việt (.srt)")

    def _init_session_preview_and_subs(self):
        """Khởi động preview video và nạp phụ đề tự động từ phiên trước (nếu có)."""
        video_p = self.video_path.get().strip()

        # Xử lý trường hợp orig_srt_path là thư mục đã lưu trước đó
        curr_orig = self.orig_srt_path.get().strip()
        if curr_orig and os.path.isdir(curr_orig):
            for f in os.listdir(curr_orig):
                if f.lower().endswith(".srt") and ("orig" in f.lower() or "goc" in f.lower()):
                    self.orig_srt_path.set(os.path.join(curr_orig, f))
                    break
            if os.path.isdir(self.orig_srt_path.get().strip()):
                for f in os.listdir(curr_orig):
                    if f.lower().endswith(".srt"):
                        self.orig_srt_path.set(os.path.join(curr_orig, f))
                        break

        if video_p and os.path.isfile(video_p):
            self._current_preview_path = None
            self._on_video_path_changed()
        else:
            has_vi = self.srt_path.get().strip() and os.path.isfile(self.srt_path.get().strip())
            has_orig = self.orig_srt_path.get().strip() and os.path.isfile(self.orig_srt_path.get().strip())
            if has_vi:
                self.sub_editor_target.set("vi")
                if hasattr(self, "sub_target_seg"):
                    self.sub_target_seg.set("Tiếng Việt (.srt)")
            elif has_orig:
                self.sub_editor_target.set("orig")
                if hasattr(self, "sub_target_seg"):
                    self.sub_target_seg.set("File Gốc (.srt)")

            self._load_subtitles_into_editor()
            if getattr(self, "_editor_sub_entries", None):
                self._select_subtitle_by_index(0)
            self._update_status_icons()

    # ── Các hàm xử lý Preview Thumbnail Video ────────────────────────────────
    def _on_video_path_changed(self):
        path = self.video_path.get().strip()
        if path != getattr(self, "_current_preview_path", None):
            if path and os.path.isfile(path):
                self._current_preview_path = path
                self._auto_detect_job_files(path)
                self._load_video_preview()
                self._load_subtitles_into_editor()
                if getattr(self, "_editor_sub_entries", None):
                    self._select_subtitle_by_index(0)
                else:
                    self.pos_editor_seek_var.set("2")
                    self._pos_editor_refresh_frame()
                self.refresh_speaker_voice_ui()
            else:
                self._clear_video_preview()
                self._pos_editor_on_video_changed()
                self._load_subtitles_into_editor()
                self.refresh_speaker_voice_ui()
        self._update_status_icons()

    def _reload_video_preview(self):
        self._load_video_preview()

    def _clear_video_preview(self):
        self._current_preview_path = None
        self._preview_image = None
        if hasattr(self, "preview_thumb_lbl"):
            self.preview_thumb_lbl.configure(image="", text="")
        if hasattr(self, "preview_info_lbl"):
            self.preview_info_lbl.configure(text="")

    def _load_video_preview(self):
        """Khởi chạy thread trích xuất thông tin & thumbnail video."""
        path = self.video_path.get().strip()
        if not path or not os.path.isfile(path):
            self._clear_video_preview()
            return

        try:
            seek_sec = float(self.preview_seek_sec.get().strip())
            if seek_sec < 0:
                seek_sec = 0.0
        except ValueError:
            seek_sec = 2.0
            self.preview_seek_sec.set("2")

        self._preview_token += 1
        token = self._preview_token

        if hasattr(self, "preview_thumb_lbl"):
            self.preview_thumb_lbl.configure(image="", text="⏳ Đang tải preview...", text_color=COLOR_TEXT_MUTED)
        if hasattr(self, "preview_info_lbl"):
            self.preview_info_lbl.configure(text="")
        if hasattr(self, "btn_refresh_preview"):
            self.btn_refresh_preview.configure(state="disabled")
        if hasattr(self, "preview_seek_entry"):
            self.preview_seek_entry.configure(state="disabled")

        thread = threading.Thread(target=self._worker_extract_preview, args=(path, seek_sec, token), daemon=True)
        thread.start()

    def _worker_extract_preview(self, video_path, seek_sec, token):
        """Worker chạy trong thread phụ: ffprobe info + ffmpeg frame capture."""
        thumb_path = os.path.join(tempfile.gettempdir(), f"_gui_video_thumb_{token}.png")
        try:
            probe = subprocess.run(
                ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height,r_frame_rate:format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1",
                 video_path],
                capture_output=True, encoding="utf-8", errors="replace", timeout=15
            )
            raw_lines = [ln.strip() for ln in probe.stdout.strip().splitlines() if ln.strip()]
            if len(raw_lines) < 2:
                raise RuntimeError("ffprobe không đọc được stream video")

            width = raw_lines[0]
            height = raw_lines[1]
            fps_raw = raw_lines[2] if len(raw_lines) > 2 else ""
            dur_raw = raw_lines[3] if len(raw_lines) > 3 else ""

            if not dur_raw or dur_raw == "N/A":
                dur_probe = subprocess.run(
                    ["ffprobe", "-v", "quiet",
                     "-show_entries", "format=duration",
                     "-of", "default=noprint_wrappers=1:nokey=1",
                     video_path],
                    capture_output=True, encoding="utf-8", errors="replace", timeout=10
                )
                dur_lines = [ln.strip() for ln in dur_probe.stdout.strip().splitlines() if ln.strip()]
                if dur_lines and dur_lines[0] != "N/A":
                    dur_raw = dur_lines[0]

            fps_str = ""
            if fps_raw and fps_raw != "N/A":
                try:
                    if "/" in fps_raw:
                        num, den = fps_raw.split("/")
                        fps_val = float(num) / float(den)
                    else:
                        fps_val = float(fps_raw)
                    if fps_val.is_integer():
                        fps_str = f"{int(fps_val)}fps"
                    else:
                        fps_str = f"{fps_val:.2f}fps"
                except Exception:
                    fps_str = fps_raw

            dur_str = ""
            if dur_raw and dur_raw != "N/A":
                try:
                    dur_sec = float(dur_raw)
                    total_sec = int(dur_sec)
                    hrs = total_sec // 3600
                    mins = (total_sec % 3600) // 60
                    secs = total_sec % 60
                    if hrs > 0:
                        dur_str = f"{hrs:02d}:{mins:02d}:{secs:02d}"
                    else:
                        dur_str = f"{mins:02d}:{secs:02d}"
                except Exception:
                    dur_str = ""

            info_parts = [f"{width}x{height}"]
            if fps_str:
                info_parts.append(fps_str)
            if dur_str:
                info_parts.append(dur_str)

            info_text = "  ·  ".join(info_parts)

            ff_res = subprocess.run(
                ["ffmpeg", "-y", "-ss", str(seek_sec), "-i", video_path,
                 "-vf", "scale=240:135:force_original_aspect_ratio=decrease",
                 "-frames:v", "1", thumb_path],
                capture_output=True, encoding="utf-8", errors="replace", timeout=20
            )

            if not os.path.exists(thumb_path) or os.path.getsize(thumb_path) == 0:
                raise RuntimeError("ffmpeg không tạo được file thumbnail")

            pil_img = Image.open(thumb_path).copy()

            self.run_on_ui_thread(lambda: self._on_preview_success(pil_img, info_text, video_path, token))

        except Exception as e:
            err_msg = str(e)
            self.run_on_ui_thread(lambda m=err_msg: self._on_preview_error(m, token))
        finally:
            if os.path.exists(thumb_path):
                try:
                    os.remove(thumb_path)
                except Exception:
                    pass

    def _on_preview_success(self, pil_img, info_text, video_path, token):
        if token != self._preview_token:
            return
        self._current_preview_path = video_path
        w, h = pil_img.size
        ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(w, h))
        self._preview_image = ctk_img

        if hasattr(self, "preview_thumb_lbl"):
            self.preview_thumb_lbl.configure(image=ctk_img, text="")
        if hasattr(self, "preview_info_lbl"):
            self.preview_info_lbl.configure(text=info_text, text_color="#E5E7EB")
        if hasattr(self, "btn_refresh_preview"):
            self.btn_refresh_preview.configure(state="normal")
        if hasattr(self, "preview_seek_entry"):
            self.preview_seek_entry.configure(state="normal")

    def _on_preview_error(self, err_msg, token):
        if token != self._preview_token:
            return
        self._clear_video_preview()
        if hasattr(self, "preview_thumb_lbl"):
            self.preview_thumb_lbl.configure(image="", text="Không đọc được thông tin video", text_color=COLOR_WARNING)
        if hasattr(self, "btn_refresh_preview"):
            self.btn_refresh_preview.configure(state="normal")
        if hasattr(self, "preview_seek_entry"):
            self.preview_seek_entry.configure(state="normal")

    def _get_job_initialdir(self):
        if hasattr(self, "job_output_dir"):
            d = self.job_output_dir.get().strip()
            if d:
                os.makedirs(d, exist_ok=True)
                return d
        if hasattr(self, "video_path"):
            v = self.video_path.get().strip()
            if v and os.path.exists(v):
                base = os.path.splitext(os.path.basename(v))[0]
                d = os.path.join(os.path.dirname(v), f"{base}_output")
                os.makedirs(d, exist_ok=True)
                return d
        return None

    def _open_job_output_dir(self):
        d = self.job_output_dir.get().strip() if hasattr(self, "job_output_dir") else ""
        if d and os.path.exists(d):
            open_with_default_app(d)
        else:
            messagebox.showwarning("Thư mục chưa tồn tại", "Thư mục job chưa được tạo. Hãy chọn video trước.")

    def pick_video(self):
        init_dir = self._get_job_initialdir()
        path = filedialog.askopenfilename(initialdir=init_dir, filetypes=[("Video", "*.mp4 *.mov *.mkv *.avi"), ("Mọi file", "*.*")])
        if path:
            self._current_preview_path = None
            self.video_path.set(path)

    def pick_srt(self):
        init_dir = self._get_job_initialdir()
        path = filedialog.askopenfilename(initialdir=init_dir, filetypes=[("Phụ đề", "*.srt"), ("Mọi file", "*.*")])
        if path:
            low = os.path.basename(path).lower()
            if ("_original" in low or "_goc" in low) and not is_vietnamese_content(path):
                cand_vi = path.replace("_original.srt", "_vietsub.srt").replace("_goc.srt", "_vietsub.srt")
                if os.path.isfile(cand_vi):
                    self.orig_srt_path.set(path)
                    self.srt_path.set(cand_vi)
                    self.sub_editor_target.set("vi")
                    if hasattr(self, "sub_target_seg"):
                        self.sub_target_seg.set("Tiếng Việt (.srt)")
                    if hasattr(self, "status_label"):
                        self.status_label.configure(text=f"✔ Đã nạp file Vietsub: {os.path.basename(cand_vi)}", text_color=COLOR_SUCCESS)
                else:
                    self.orig_srt_path.set(path)
                    self.sub_editor_target.set("orig")
                    if hasattr(self, "sub_target_seg"):
                        self.sub_target_seg.set("File Gốc (.srt)")
                    if hasattr(self, "status_label"):
                        self.status_label.configure(text=f"✔ Đã nạp file phụ đề gốc: {os.path.basename(path)}", text_color=COLOR_SUCCESS)
            else:
                self.srt_path.set(path)
                self.sub_editor_target.set("vi")
                if hasattr(self, "sub_target_seg"):
                    self.sub_target_seg.set("Tiếng Việt (.srt)")
                if hasattr(self, "status_label"):
                    self.status_label.configure(text=f"✔ Đã nạp file phụ đề: {os.path.basename(path)}", text_color=COLOR_SUCCESS)

            self._load_subtitles_into_editor()
            if getattr(self, "_editor_sub_entries", None):
                self._select_subtitle_by_index(0)
            self._update_status_icons()

    def pick_orig_srt(self):
        init_dir = self._get_job_initialdir()
        path = filedialog.askopenfilename(initialdir=init_dir, filetypes=[("Phụ đề", "*.srt"), ("Mọi file", "*.*")])
        if path:
            low = os.path.basename(path).lower()
            if "vietsub" in low or is_vietnamese_content(path):
                self.srt_path.set(path)
                self.sub_editor_target.set("vi")
                if hasattr(self, "sub_target_seg"):
                    self.sub_target_seg.set("Tiếng Việt (.srt)")
                if hasattr(self, "status_label"):
                    self.status_label.configure(text=f"✔ Đã nạp file Vietsub: {os.path.basename(path)}", text_color=COLOR_SUCCESS)
            else:
                self.orig_srt_path.set(path)
                self.sub_editor_target.set("orig")
                if hasattr(self, "sub_target_seg"):
                    self.sub_target_seg.set("File Gốc (.srt)")
                if hasattr(self, "status_label"):
                    self.status_label.configure(text=f"✔ Đã nạp file phụ đề gốc: {os.path.basename(path)}", text_color=COLOR_SUCCESS)

            self._load_subtitles_into_editor()
            if getattr(self, "_editor_sub_entries", None):
                self._select_subtitle_by_index(0)
            self._update_status_icons()

    def pick_output(self):
        init_dir = self._get_job_initialdir()
        v_path = self.video_path.get().strip() if hasattr(self, "video_path") else ""
        base = os.path.splitext(os.path.basename(v_path))[0] if v_path else "output"
        suggested_name = f"{base}_output.mp4"
        path = filedialog.asksaveasfilename(initialdir=init_dir, initialfile=suggested_name, defaultextension=".mp4", filetypes=[("MP4", "*.mp4")])
        if path:
            self.output_path.set(path)
            new_dir = os.path.dirname(path)
            if hasattr(self, "job_output_dir"):
                self.job_output_dir.set(new_dir)

    def pick_dubbed_video(self):
        init_dir = self._get_job_initialdir()
        path = filedialog.askopenfilename(initialdir=init_dir, filetypes=[("Video", "*.mp4 *.mov *.mkv *.avi"), ("Mọi file", "*.*")])
        if path:
            self.dubbed_video_path.set(path)


    def open_srt(self):
        if not self.srt_path.get() or not os.path.exists(self.srt_path.get()):
            messagebox.showwarning("Chưa có file", "Chưa có file phụ đề để mở. Hãy 'Tạo khung rỗng' hoặc chọn file trước.")
            return
        open_with_default_app(self.srt_path.get())

    def open_orig_srt(self):
        if not self.orig_srt_path.get() or not os.path.exists(self.orig_srt_path.get()):
            messagebox.showwarning("Chưa có file", "Chưa có file phụ đề gốc. Hãy chạy bước nhận diện trước.")
            return
        open_with_default_app(self.orig_srt_path.get())

    # ── Chạy tiến trình Async & Dừng Job ─────────────────────────────────────
    def _set_buttons_state(self, state):
        """Enable hoặc Disable tất cả các nút chạy lệnh."""
        for btn in self._run_buttons:
            try:
                btn.configure(state=state)
            except Exception:
                pass

    def _cancel_job(self):
        """Hủy tiến trình đang chạy."""
        if self._current_proc and self._current_proc.poll() is None:
            try:
                pid = self._current_proc.pid
                if platform.system() == "Windows":
                    subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)
                else:
                    self._current_proc.terminate()
                self.log_write("\n✘ Đã hủy theo yêu cầu người dùng\n")
                self._stop_dot_animation()
                self.status_label.configure(text="✘ Đã hủy job", text_color=COLOR_WARNING)
            except Exception as e:
                self.log_write(f"\n✘ Lỗi khi dừng tiến trình: {e}\n")

    def _start_dot_animation(self, base_text="Đang xử lý"):
        self._stop_dot_animation()
        dot_count = 0

        def animate():
            nonlocal dot_count
            dot_count = (dot_count % 3) + 1
            dots = "." * dot_count
            self.status_label.configure(text=f"{base_text}{dots}")
            self._dot_anim_id = self.after(500, animate)

        animate()

    def _stop_dot_animation(self):
        if self._dot_anim_id is not None:
            try:
                self.after_cancel(self._dot_anim_id)
            except Exception:
                pass
            self._dot_anim_id = None

    def _start_job_ui(self, active_btn=None, active_text="⏳ Đang chạy...", anim_text="Đang xử lý", show_cancel=True):
        """Khởi tạo trạng thái giao diện khi bắt đầu một Job."""
        self._job_running = True
        self._set_buttons_state("disabled")
        self.status_label.configure(text_color=COLOR_TEXT_MUTED)
        self._start_dot_animation(anim_text)
        self._update_status_icons()

        self._active_btn = active_btn
        self._active_btn_orig_text = None
        if active_btn:
            try:
                self._active_btn_orig_text = active_btn.cget("text")
                active_btn.configure(text=active_text)
            except Exception:
                pass

        if show_cancel:
            self.btn_cancel.pack(side="right", padx=(0, 8), before=self.btn_toggle_log)

    def _finish_job_ui(self):
        """Khôi phục trạng thái giao diện khi Job kết thúc."""
        self._stop_dot_animation()
        self._job_running = False
        self._set_buttons_state("normal")
        self.btn_cancel.pack_forget()
        if self._active_btn and self._active_btn_orig_text:
            try:
                self._active_btn.configure(text=self._active_btn_orig_text)
            except Exception:
                pass
        self._active_btn = None
        self._active_btn_orig_text = None
        self._update_status_icons()

    def _run_cmd_async(self, cmd, on_done=None, active_btn=None):
        if self._job_running:
            messagebox.showwarning("Đang chạy", "Đang có tiến trình khác đang chạy. Hãy chờ hoặc bấm Dừng trước.")
            return

        self._start_job_ui(active_btn=active_btn, active_text="⏳ Đang chạy...", anim_text="Đang xử lý", show_cancel=True)

        def worker():
            self.run_on_ui_thread(self._progress_indeterminate)
            self.run_on_ui_thread(lambda: self.log_write(f"\n$ {' '.join(cmd)}\n"))
            try:
                env = os.environ.copy()
                env["PYTHONIOENCODING"] = "utf-8"
                env["PYTHONUNBUFFERED"] = "1"
                if self.hf_token.get().strip():
                    env["HF_TOKEN"] = self.hf_token.get().strip()
                if self.gemini_api_key.get().strip():
                    env["GEMINI_API_KEY"] = self.gemini_api_key.get().strip()
                if self.groq_api_key.get().strip():
                    env["GROQ_API_KEY"] = self.groq_api_key.get().strip()
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         text=True, bufsize=1, encoding="utf-8", errors="replace", env=env)
                self._current_proc = proc
                for line in proc.stdout:
                    self.run_on_ui_thread(lambda l=line: self.log_write(l))
                    m = PROGRESS_RE.search(line)
                    if m:
                        pct = min(int(m.group(1)), 100)
                        self.run_on_ui_thread(lambda p=pct: self._progress_set(p))
                proc.wait()
                ok = proc.returncode == 0
            except Exception as e:
                err_msg = f"\n✘ Lỗi: {e}\n"
                self.run_on_ui_thread(lambda m=err_msg: self.log_write(m))
                ok = False

            self._current_proc = None
            self.run_on_ui_thread(self._progress_reset)
            self.run_on_ui_thread(self._finish_job_ui)
            if on_done:
                self.run_on_ui_thread(lambda: on_done(ok))

        threading.Thread(target=worker, daemon=True).start()

    def _on_job_finished(self):
        self._finish_job_ui()

    def _progress_indeterminate(self):
        self.progress.configure(mode="indeterminate")
        self.progress.start()

    def _progress_set(self, pct):
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.progress.set(pct / 100)

    def _progress_reset(self):
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.progress.set(0)

    def _require_video(self):
        if not self.video_path.get():
            messagebox.showwarning("Thiếu video", "Hãy chọn video trước ở mục 'Video nguồn'.")
            return False
        return True

    # ── Các hàm Thực Thi CLI ──────────────────────────────────────────────────
    def run_template(self, btn=None):
        if not self._require_video():
            return
        out_dir = self._get_job_initialdir() or os.path.dirname(self.video_path.get())
        base = os.path.splitext(os.path.basename(self.video_path.get()))[0]
        if not self.srt_path.get() or os.path.dirname(self.srt_path.get()) != out_dir:
            self.srt_path.set(os.path.join(out_dir, f"{base}_vietsub.srt"))
        cmd = [sys.executable, DUB_TOOL, "template", self.video_path.get(), "-o", self.srt_path.get()]
        def done(ok):
            if ok:
                self.status_label.configure(text="✔ Hoàn tất tạo khung phụ đề", text_color=COLOR_SUCCESS)
                self.sub_editor_target.set("vi")
                if hasattr(self, "sub_target_seg"):
                    self.sub_target_seg.set("Tiếng Việt (.srt)")
                self._load_subtitles_into_editor()
                if self._editor_sub_entries:
                    self._select_subtitle_by_index(0)
                messagebox.showinfo("Xong", "Đã tạo file phụ đề khung rỗng và tự động nạp vào danh sách bên trái!")
            else:
                self.status_label.configure(text="✘ Lỗi khi tạo khung — bấm ▲ để xem", text_color=COLOR_DANGER)
                if not self._log_expanded:
                    self._toggle_log_panel()
                messagebox.showerror("Lỗi", "Tạo khung rỗng thất bại. Xem chi tiết trong Nhật ký.")
        self._run_cmd_async(cmd, on_done=done, active_btn=btn)

    def run_get_original_only(self, btn=None):
        if not self._require_video():
            return
        out_dir = self._get_job_initialdir() or os.path.dirname(self.video_path.get())
        base = os.path.splitext(os.path.basename(self.video_path.get()))[0]
        orig_path = os.path.join(out_dir, f"{base}_original.srt")
        self.orig_srt_path.set(orig_path)
        cmd = [sys.executable, DUB_TOOL, "transcribe", self.video_path.get(),
               "-o", orig_path,
               "--model", self.whisper_model.get()]
        if self.enable_diarize.get():
            cmd.append("--diarize")
            token = self.hf_token.get().strip()
            if token:
                cmd += ["--hf-token", token]
        def done(ok):
            if ok:
                self.status_label.configure(text="✔ Hoàn tất lấy phụ đề gốc", text_color=COLOR_SUCCESS)
                self.orig_srt_path.set(orig_path)
                self.sub_editor_target.set("orig")
                if hasattr(self, "sub_target_seg"):
                    self.sub_target_seg.set("File Gốc (.srt)")
                self._load_subtitles_into_editor()
                if self._editor_sub_entries:
                    self._select_subtitle_by_index(0)
                messagebox.showinfo("Xong",
                    "Đã tạo phụ đề GỐC (chưa dịch) và tự động hiển thị trong danh sách bên trái!\n\n"
                    "Bạn có thể bấm '📄 Notepad' để copy sang Claude nhờ dịch, hoặc dùng nút dịch AI trực tiếp trong app.")
            else:
                self.status_label.configure(text="✘ Lỗi khi lấy phụ đề gốc — bấm ▲ để xem", text_color=COLOR_DANGER)
                if not self._log_expanded:
                    self._toggle_log_panel()
                messagebox.showerror("Lỗi", "Không lấy được phụ đề gốc. Xem chi tiết trong Nhật ký.")
        self._run_cmd_async(cmd, on_done=done, active_btn=btn)

    def run_ocr_only(self, btn=None):
        if not self._require_video():
            return
        out_dir = self._get_job_initialdir() or os.path.dirname(self.video_path.get())
        base = os.path.splitext(os.path.basename(self.video_path.get()))[0]
        orig_path = os.path.join(out_dir, f"{base}_original.srt")
        self.orig_srt_path.set(orig_path)

        try:
            crop_top = float(self.mask_top.get())
        except (ValueError, TypeError):
            crop_top = 0.70
        try:
            crop_bot = float(self.mask_bottom.get())
        except (ValueError, TypeError):
            crop_bot = 0.98
        try:
            crop_left = float(self.crop_left.get())
        except (ValueError, TypeError):
            crop_left = 0.0
        try:
            crop_right = float(self.crop_right.get())
        except (ValueError, TypeError):
            crop_right = 1.0
        try:
            fps = float(self.ocr_fps.get())
        except (ValueError, TypeError):
            fps = 4.0

        cmd = [
            sys.executable, DUB_TOOL, "ocr", self.video_path.get(),
            "-o", orig_path,
            "--crop-top", f"{crop_top:.3f}",
            "--crop-bottom", f"{crop_bot:.3f}",
            "--crop-left", f"{crop_left:.3f}",
            "--crop-right", f"{crop_right:.3f}",
            "--ocr-fps", str(fps),
        ]

        def done(ok):
            if ok:
                self.status_label.configure(text="✔ Hoàn tất quét phụ đề cứng (OCR)", text_color=COLOR_SUCCESS)
                self.orig_srt_path.set(orig_path)
                self.sub_editor_target.set("orig")
                if hasattr(self, "sub_target_seg"):
                    self.sub_target_seg.set("File Gốc (.srt)")
                self._load_subtitles_into_editor()
                if self._editor_sub_entries:
                    self._select_subtitle_by_index(0)
                messagebox.showinfo(
                    "Xong",
                    f"Đã trích xuất xong phụ đề cứng từ video và nạp vào danh sách bên trái!\n\n"
                    f"File lưu tại: {orig_path}\n"
                    "Bây giờ bạn có thể bấm 'Chỉ dịch (AI) từ file GỐC' để dịch sang tiếng Việt."
                )
            else:
                self.status_label.configure(text="✘ Lỗi khi quét phụ đề OCR — bấm ▲ để xem", text_color=COLOR_DANGER)
                if not self._log_expanded:
                    self._toggle_log_panel()
                messagebox.showerror("Lỗi", "Quét phụ đề cứng thất bại. Xem chi tiết trong Nhật ký.")
        self._run_cmd_async(cmd, on_done=done, active_btn=btn)

    def run_auto_transcribe(self, btn=None):
        if not self._require_video():
            return
        engine = self.translate_engine.get()
        if engine == "groq":
            if not self.groq_api_key.get().strip():
                messagebox.showwarning("Thiếu API key",
                    "Hãy nhập Groq API key ở mục Phụ đề trước.\n"
                    "Lấy key miễn phí tại: https://console.groq.com/keys")
                return
        else:
            if not self.gemini_api_key.get().strip():
                messagebox.showwarning("Thiếu API key",
                    "Hãy nhập Gemini API key ở mục Phụ đề trước.\n"
                    "Lấy key miễn phí tại: https://aistudio.google.com/apikey")
                return

        out_dir = self._get_job_initialdir() or os.path.dirname(self.video_path.get())
        base = os.path.splitext(os.path.basename(self.video_path.get()))[0]
        vi_path = os.path.join(out_dir, f"{base}_vietsub.srt")
        orig_path = os.path.join(out_dir, f"{base}_original.srt")
        self.srt_path.set(vi_path)
        self.orig_srt_path.set(orig_path)
        if not self.output_path.get() or os.path.dirname(self.output_path.get()) != out_dir:
            self.output_path.set(os.path.join(out_dir, f"{base}_output.mp4"))
        if not self.dubbed_video_path.get() or os.path.dirname(self.dubbed_video_path.get()) != out_dir:
            self.dubbed_video_path.set(os.path.join(out_dir, f"{base}_dalongtieng.mp4"))

        cmd = [sys.executable, DUB_TOOL, "auto", self.video_path.get(),
               "-o", self.output_path.get(),
               "--script-out", vi_path,
               "--pause-for-edit"]

        is_ocr = self.sub_source_mode.get() == "ocr"
        if is_ocr:
            cmd.append("--ocr")
            try:
                cmd += ["--crop-top", f"{float(self.mask_top.get()):.3f}"]
            except (ValueError, TypeError):
                pass
            try:
                cmd += ["--crop-bottom", f"{float(self.mask_bottom.get()):.3f}"]
            except (ValueError, TypeError):
                pass
            try:
                cmd += ["--crop-left", f"{float(self.crop_left.get()):.3f}"]
            except (ValueError, TypeError):
                pass
            try:
                cmd += ["--crop-right", f"{float(self.crop_right.get()):.3f}"]
            except (ValueError, TypeError):
                pass
            try:
                cmd += ["--ocr-fps", str(float(self.ocr_fps.get()))]
            except (ValueError, TypeError):
                pass
        else:
            cmd += ["--model", self.whisper_model.get()]
            if self.enable_diarize.get():
                cmd.append("--diarize")
                token = self.hf_token.get().strip()
                if token:
                    cmd += ["--hf-token", token]

        cmd += ["--translate-engine", engine]
        if self.gemini_api_key.get().strip():
            cmd += ["--api-key", self.gemini_api_key.get().strip()]
        if self.groq_api_key.get().strip():
            cmd += ["--groq-api-key", self.groq_api_key.get().strip()]
        model = self.groq_model.get().strip() if engine == "groq" else self.gemini_model.get().strip()
        if model:
            cmd += ["--translate-model", model]
        def done(ok):
            if ok:
                self.status_label.configure(text="✔ Hoàn tất nhận diện & dịch", text_color=COLOR_SUCCESS)
                self.srt_path.set(vi_path)
                self.orig_srt_path.set(orig_path)
                self.sub_editor_target.set("vi")
                if hasattr(self, "sub_target_seg"):
                    self.sub_target_seg.set("Tiếng Việt (.srt)")
                self._load_subtitles_into_editor()
                if self._editor_sub_entries:
                    self._select_subtitle_by_index(0)
                messagebox.showinfo("Xong", "Đã nhận diện và dịch xong phụ đề!\nToàn bộ câu thoại đã tự động nạp lên danh sách bên trái để bạn xem và chỉnh sửa.")
            else:
                self.status_label.configure(text="✘ Lỗi nhận diện/dịch — bấm ▲ để xem", text_color=COLOR_DANGER)
                if not self._log_expanded:
                    self._toggle_log_panel()
                messagebox.showerror("Lỗi", "Bước nhận diện/dịch thất bại. Xem chi tiết trong Nhật ký.")
        self._run_cmd_async(cmd, on_done=done, active_btn=btn)

    def run_translate_only(self, btn=None):
        if not self.orig_srt_path.get() or not os.path.exists(self.orig_srt_path.get()):
            messagebox.showwarning("Thiếu file gốc", "Hãy chọn file phụ đề GỐC trước (hoặc chạy bước nhận diện).")
            return
        engine = self.translate_engine.get()
        if engine == "groq":
            if not self.groq_api_key.get().strip():
                messagebox.showwarning("Thiếu API key", "Hãy nhập Groq API key trước.\nLấy key miễn phí tại: https://console.groq.com/keys")
                return
        else:
            if not self.gemini_api_key.get().strip():
                messagebox.showwarning("Thiếu API key", "Hãy nhập Gemini API key trước.\nLấy key miễn phí tại: https://aistudio.google.com/apikey")
                return

        out_dir = self._get_job_initialdir() or os.path.dirname(self.orig_srt_path.get())
        orig_filename = os.path.basename(self.orig_srt_path.get())
        base = os.path.splitext(orig_filename)[0]
        for sfx in ["_original", "_goc"]:
            if base.endswith(sfx):
                base = base[:-len(sfx)]
                break
        vi_path = os.path.join(out_dir, f"{base}_vietsub.srt")
        self.srt_path.set(vi_path)

        cmd = [sys.executable, DUB_TOOL, "translate", self.orig_srt_path.get(),
               "-o", vi_path,
               "--translate-engine", engine]
        if self.gemini_api_key.get().strip():
            cmd += ["--api-key", self.gemini_api_key.get().strip()]
        if self.groq_api_key.get().strip():
            cmd += ["--groq-api-key", self.groq_api_key.get().strip()]
        model = self.groq_model.get().strip() if engine == "groq" else self.gemini_model.get().strip()
        if model:
            cmd += ["--translate-model", model]

        def done(ok):
            if ok:
                engine_name = "Groq" if engine == "groq" else "Gemini"
                self.status_label.configure(text=f"✔ Hoàn tất dịch bằng {engine_name}", text_color=COLOR_SUCCESS)
                self.srt_path.set(vi_path)
                self.sub_editor_target.set("vi")
                if hasattr(self, "sub_target_seg"):
                    self.sub_target_seg.set("Tiếng Việt (.srt)")
                self._load_subtitles_into_editor()
                if self._editor_sub_entries:
                    self._select_subtitle_by_index(0)
                messagebox.showinfo("Xong", f"Đã dịch xong bằng {engine_name}!\nToàn bộ câu thoại đã tự động nạp lên danh sách bên trái để bạn xem và chỉnh sửa.")
            else:
                self.status_label.configure(text="✘ Lỗi dịch — bấm ▲ để xem", text_color=COLOR_DANGER)
                if not self._log_expanded:
                    self._toggle_log_panel()
                messagebox.showerror("Lỗi", "Dịch thất bại. Xem chi tiết trong Nhật ký.")
        self._run_cmd_async(cmd, on_done=done, active_btn=btn)

    def run_check_quota(self, btn=None):
        engine = self.translate_engine.get()
        if engine == "groq":
            key = self.groq_api_key.get().strip()
            model = self.groq_model.get().strip() or "qwen/qwen3.8-27b"
            engine_name = "Groq"
            key_url = "https://console.groq.com/keys"
        else:
            key = self.gemini_api_key.get().strip()
            model = self.gemini_model.get().strip() or "gemini-3.6-flash"
            engine_name = "Gemini"
            key_url = "https://aistudio.google.com/apikey"

        if not key:
            messagebox.showwarning(
                "Thiếu API Key",
                f"Hãy nhập {engine_name} API key ở mục Phụ đề trước khi kiểm tra.\n"
                f"Lấy key miễn phí tại: {key_url}"
            )
            return

        if self._job_running:
            messagebox.showwarning("Đang bận", "Đang có tiến trình khác chạy. Vui lòng chờ hoặc dừng trước.")
            return

        self._start_job_ui(active_btn=btn, active_text="⏳ Đang kiểm tra...", anim_text=f"Đang kiểm tra quota {engine_name}", show_cancel=False)

        def worker():
            from core.translate import check_gemini_quota, check_groq_quota
            self.log_write(f"\n→ Đang kiểm tra {engine_name} API key (model: {model})...\n")
            if engine == "groq":
                is_ok, msg = check_groq_quota(key, model)
            else:
                is_ok, msg = check_gemini_quota(key, model)

            def finish():
                self._finish_job_ui()
                self.log_write(f"{msg}\n")
                if is_ok:
                    self.status_label.configure(text=f"✔ {engine_name} API Key hợp lệ & còn quota", text_color=COLOR_SUCCESS)
                    messagebox.showinfo("Kết quả kiểm tra Quota", msg)
                else:
                    self.status_label.configure(text=f"✘ {engine_name} API Key hết quota / lỗi", text_color=COLOR_DANGER)
                    if not self._log_expanded:
                        self._toggle_log_panel()
                    messagebox.showwarning("Kết quả kiểm tra Quota", msg)

            self.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    def _load_app_settings(self):
        """Đọc cài đặt người dùng đã lưu từ file user_settings.json."""
        try:
            cfg_path = os.path.join(SCRIPT_DIR, "user_settings.json")
            if os.path.exists(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load user_settings.json: {e}")
        return {}

    def _save_app_settings(self, updates: dict):
        """Cập nhật và lưu vào file user_settings.json."""
        try:
            cfg_path = os.path.join(SCRIPT_DIR, "user_settings.json")
            current = self._load_app_settings()
            current.update(updates)
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(current, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Error saving user_settings.json: {e}")
            return False

    def save_hf_token(self):
        tok = self.hf_token.get().strip()
        if not tok:
            messagebox.showwarning("Chưa nhập token", "Vui lòng nhập HuggingFace Token trước khi lưu.")
            return
        ok = self._save_app_settings({"hf_token": tok, "enable_diarize": self.enable_diarize.get()})
        if ok:
            os.environ["HF_TOKEN"] = tok
            self.status_label.configure(text="✔ Đã lưu HuggingFace Token", text_color=COLOR_SUCCESS)
            messagebox.showinfo("Đã lưu token", "Đã lưu HuggingFace Token thành công!\nTừ giờ khi mở lại app, token sẽ tự động được nạp.")
        else:
            messagebox.showerror("Lỗi", "Không thể lưu token vào file cài đặt.")

    def save_api_key(self):
        engine = self.translate_engine.get()
        updates = {"translate_engine": engine}
        if engine == "groq":
            key = self.groq_api_key.get().strip()
            if not key:
                messagebox.showwarning("Chưa nhập API Key", "Vui lòng nhập Groq API Key trước khi lưu.")
                return
            updates["groq_api_key"] = key
            updates["groq_model"] = self.groq_model.get().strip()
            os.environ["GROQ_API_KEY"] = key
            name = "Groq"
        else:
            key = self.gemini_api_key.get().strip()
            if not key:
                messagebox.showwarning("Chưa nhập API Key", "Vui lòng nhập Gemini API Key trước khi lưu.")
                return
            updates["gemini_api_key"] = key
            updates["gemini_model"] = self.gemini_model.get().strip()
            os.environ["GEMINI_API_KEY"] = key
            name = "Gemini"

        ok = self._save_app_settings(updates)
        if ok:
            self.status_label.configure(text=f"✔ Đã lưu {name} API Key", text_color=COLOR_SUCCESS)
            messagebox.showinfo("Đã lưu API Key", f"Đã lưu {name} API Key thành công!\nTừ giờ khi mở lại app, key sẽ tự động được nạp.")
        else:
            messagebox.showerror("Lỗi", "Không thể lưu API Key vào file cài đặt.")

    def save_gemini_key(self):
        self.save_api_key()

    def _build_speaker_voice_args(self):
        """Thu thập các tham số --speaker-voices và --merge-speakers từ UI."""
        args = []
        if self.single_voice.get():
            return args

        spk_voices = []
        merge_spks = []
        for spk, var in getattr(self, "speaker_voice_vars", {}).items():
            val = var.get().strip()
            if val.startswith("Gộp vào "):
                target = val.replace("Gộp vào ", "").strip()
                if target:
                    merge_spks.append(f"{spk}:{target}")
            elif val and val != "Mặc định (theo AI)":
                spk_voices.append(f"{spk}:{val}")

        if spk_voices:
            args.extend(["--speaker-voices", ",".join(spk_voices)])
        if merge_spks:
            args.extend(["--merge-speakers", ",".join(merge_spks)])
        return args

    def _preview_speaker_voice(self, spk, btn=None):
        if spk not in getattr(self, "speaker_voice_vars", {}):
            return
        val = self.speaker_voice_vars[spk].get().strip()
        self.run_preview_voice(specific_voice=val, btn=btn)

    def refresh_speaker_voice_ui(self, force=False):
        """Tự động quét file phụ đề .srt để hiển thị danh sách nhân vật và chọn giọng riêng (có bộ nhớ đệm)."""
        if not hasattr(self, "frame_speakers"):
            return

        # Nếu đang bật chế độ 1 giọng duy nhất thì ẩn phần phân giọng
        if self.single_voice.get():
            self.frame_speakers.pack_forget()
            self._current_spk_ui_file = None
            self._current_spk_ui_mtime = 0
            return

        srt_file = self.srt_path.get().strip()
        if not srt_file or not os.path.exists(srt_file):
            self.frame_speakers.pack_forget()
            self._current_spk_ui_file = None
            self._current_spk_ui_mtime = 0
            return

        try:
            mtime = os.path.getmtime(srt_file)
            if (not force and
                getattr(self, "_current_spk_ui_file", None) == srt_file and
                getattr(self, "_current_spk_ui_mtime", 0) == mtime):
                return
        except Exception:
            mtime = 0

        # Quét danh sách người nói từ file SRT
        detected_speakers = []
        try:
            from core.utils import extract_speaker_label
            with open(srt_file, "r", encoding="utf-8") as f:
                import srt
                subs = list(srt.parse(f.read()))
            for s in subs:
                lbl = extract_speaker_label(s.content)
                if lbl and lbl not in detected_speakers:
                    detected_speakers.append(lbl)
        except Exception:
            pass

        if not detected_speakers:
            self.frame_speakers.pack_forget()
            self._current_spk_ui_file = srt_file
            self._current_spk_ui_mtime = mtime
            return

        self._current_spk_ui_file = srt_file
        self._current_spk_ui_mtime = mtime

        # Có người nói -> hiển thị frame gán giọng
        self.frame_speakers.pack(fill="x", padx=14, pady=(5, 12), after=self.row_single)

        # Xóa các widget cũ trong frame
        for widget in self.frame_speakers.winfo_children():
            widget.destroy()

        # Kiểm tra xem có file debug diarization không để nạp vai
        role_map = {}
        try:
            from core.diarize import load_role_map_from_debug_file
            role_map = load_role_map_from_debug_file(srt_file) or {}
        except Exception:
            pass

        role_labels = {
            "main": "Vai chính",
            "female_secondary": "Nữ phụ",
            "male_secondary": "Nam phụ"
        }

        header = ctk.CTkFrame(self.frame_speakers, fg_color="transparent")
        header.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(
            header,
            text=f"👥 Phân gán giọng cho từng nhân vật (tìm thấy {len(detected_speakers)} người nói):",
            font=FONT_LABEL(),
            text_color=COLOR_ACCENT
        ).pack(side="left")

        eng = self.tts_engine.get().strip()
        voices_list = VOICES.get(eng, VOICES["edge"])

        for spk in detected_speakers:
            role_info = ""
            if spk in role_map:
                r_text = role_labels.get(role_map[spk], role_map[spk])
                role_info = f" ({r_text})"

            # Danh sách lựa chọn cho dropdown
            choices = ["Mặc định (theo AI)"] + list(voices_list) + [f"Gộp vào {other}" for other in detected_speakers if other != spk]

            if spk not in self.speaker_voice_vars:
                default_val = "Mặc định (theo AI)"
                if hasattr(self, "_saved_speaker_voices") and spk in self._saved_speaker_voices:
                    saved_val = self._saved_speaker_voices[spk]
                    if saved_val in choices:
                        default_val = saved_val
                self.speaker_voice_vars[spk] = tk.StringVar(value=default_val)
            else:
                current_val = self.speaker_voice_vars[spk].get()
                if current_val not in choices:
                    self.speaker_voice_vars[spk].set("Mặc định (theo AI)")

            row_spk = ctk.CTkFrame(self.frame_speakers, fg_color="transparent")
            row_spk.pack(fill="x", pady=2)

            ctk.CTkLabel(
                row_spk,
                text=f"• {spk}{role_info}:",
                font=FONT_LABEL(),
                width=160,
                anchor="w"
            ).pack(side="left", padx=(0, 8))

            combo = ctk.CTkComboBox(
                row_spk,
                variable=self.speaker_voice_vars[spk],
                values=choices,
                width=190,
                height=INPUT_HEIGHT,
                state="readonly"
            )
            combo.pack(side="left", padx=(0, 6))

            btn_play = ctk.CTkButton(
                row_spk,
                text="▶",
                width=32,
                height=INPUT_HEIGHT,
                **OUTLINE_BTN
            )
            btn_play.configure(command=lambda s=spk, b=btn_play: self._preview_speaker_voice(s, b))
            btn_play.pack(side="left")
            self._run_buttons.append(btn_play)

    def _audio_mix_args(self):
        if self.keep_original.get() == "custom":
            return ["--bg-volume", f"{self.bg_volume.get():.3f}",
                    "--dub-volume", f"{self.dub_volume.get():.3f}"]
        return ["--mix-preset", self.keep_original.get()]

    def run_dub_only(self, btn=None):
        if not self._require_video():
            return
        if not self.srt_path.get() or not os.path.exists(self.srt_path.get()):
            messagebox.showwarning("Thiếu phụ đề", "Hãy tạo/chọn file phụ đề .srt trước.")
            return
        out_dir = self._get_job_initialdir() or os.path.dirname(self.video_path.get())
        base = os.path.splitext(os.path.basename(self.video_path.get()))[0]
        if not self.dubbed_video_path.get() or os.path.dirname(self.dubbed_video_path.get()) != out_dir:
            self.dubbed_video_path.set(os.path.join(out_dir, f"{base}_dalongtieng.mp4"))
        cmd = [sys.executable, DUB_TOOL, "dub", self.video_path.get(), self.srt_path.get(),
               "-o", self.dubbed_video_path.get(),
               "--voice", self.voice.get(),
               "--tts-engine", self.tts_engine.get()]
        if self.single_voice.get():
            cmd.append("--single-voice")
        else:
            cmd.extend(self._build_speaker_voice_args())
        if self.tts_engine.get() == "capcut":
            cmd += ["--capcut-rate", f"{self.capcut_rate.get():.2f}"]
        cmd += self._audio_mix_args() + self._extra_blur_args()
        def done(ok):
            if ok:
                self._load_subtitles_into_editor()
                self.status_label.configure(text="✔ Hoàn tất lồng tiếng & Fit timeline phụ đề", text_color=COLOR_SUCCESS)
                self._show_post_job_success(self.dubbed_video_path.get().strip())
                messagebox.showinfo("Xong",
                    f"Đã lồng tiếng xong:\n{self.dubbed_video_path.get()}\n\n"
                    "✔ Timeline phụ đề đã được tự động fit khớp 100% với giọng đọc!\n"
                    "Nghe thử file này trước, ưng ý thì bấm 'Chỉ gắn phụ đề "
                    "vào video đã lồng tiếng' để ra video hoàn chỉnh.")
            else:
                self.status_label.configure(text="✘ Lỗi lồng tiếng — bấm ▲ để xem", text_color=COLOR_DANGER)
                if not self._log_expanded:
                    self._toggle_log_panel()
                messagebox.showerror("Lỗi", "Lồng tiếng thất bại. Xem chi tiết trong Nhật ký.")
        self._run_cmd_async(cmd, on_done=done, active_btn=btn)


    def _validate_numeric_inputs(self):
        """Validate numeric StringVars before building command. Returns True if valid, False otherwise."""
        # 1. Font size
        try:
            val = float(self.font_size.get())
            if val <= 0:
                raise ValueError()
        except ValueError:
            messagebox.showerror("Lỗi nhập liệu", "Cỡ chữ (font_size) phải là số dương lớn hơn 0.")
            return False

        # 2. Outline width
        try:
            val = float(self.outline_width.get())
            if val < 0:
                raise ValueError()
        except ValueError:
            messagebox.showerror("Lỗi nhập liệu", "Độ dày viền (outline_width) phải là số không âm (>= 0).")
            return False

        # 3. Mask parameters (nếu bật)
        if self.mask_original.get():
            try:
                blur_val = float(self.mask_blur.get())
                if blur_val <= 0:
                    raise ValueError()
            except ValueError:
                messagebox.showerror("Lỗi nhập liệu", "Độ mờ vùng che (mask_blur) phải là số dương lớn hơn 0.")
                return False

            try:
                top_val = float(self.mask_top.get())
                bot_val = float(self.mask_bottom.get())
                if not (0 <= top_val < bot_val <= 1):
                    messagebox.showerror("Lỗi nhập liệu", "Vị trí mask_top / mask_bottom phải từ 0.0 đến 1.0 và Top < Bottom.")
                    return False
            except ValueError:
                messagebox.showerror("Lỗi nhập liệu", "Vị trí mask_top / mask_bottom phải là số thực.")
                return False

        # 4. Free position parameters (nếu bật)
        if self.use_free_pos.get():
            try:
                px = float(self.pos_x.get())
                py = float(self.pos_y.get())
                if not (0 <= px <= 1 and 0 <= py <= 1):
                    messagebox.showerror("Lỗi nhập liệu", "Vị trí tự do X, Y (pos_x, pos_y) phải từ 0.0 đến 1.0.")
                    return False
            except ValueError:
                messagebox.showerror("Lỗi nhập liệu", "Vị trí tự do X, Y (pos_x, pos_y) phải là số thực hợp lệ.")
                return False

        return True

    def run_burn_original_only(self, btn=None):
        """Chỉ gắn phụ đề vào video gốc, giữ nguyên 100% âm thanh gốc (không lồng tiếng)."""
        if not self._require_video():
            return
        if not self.srt_path.get() or not os.path.exists(self.srt_path.get()):
            messagebox.showwarning("Thiếu phụ đề", "Hãy tạo hoặc chọn file phụ đề .srt trước.")
            return

        out_dir = self._get_job_initialdir() or os.path.dirname(self.video_path.get())
        base = os.path.splitext(os.path.basename(self.video_path.get()))[0]
        curr_out = self.output_path.get().strip()
        if not curr_out or os.path.dirname(curr_out) != out_dir or curr_out.endswith("_output.mp4"):
            self.output_path.set(os.path.join(out_dir, f"{base}_vietsub.mp4"))

        if not self._validate_numeric_inputs():
            return

        cmd = [sys.executable, DUB_TOOL, "burn", self.video_path.get(), self.srt_path.get(),
               "-o", self.output_path.get(),
               "--font-name", self.font_name.get(),
               "--font-size", self.font_size.get(),
               "--font-color", self.font_color.get(),
               "--outline-color", self.outline_color.get(),
               "--outline-width", self.outline_width.get(),
               "--position", self.sub_position.get()]
        if self.sub_bold.get():
            cmd.append("--bold")
        if self.mask_original.get():
            cmd += ["--mask-original", "--mask-style", self.mask_style.get(),
                    "--mask-blur", self.mask_blur.get(),
                    "--mask-top", self.mask_top.get(), "--mask-bottom", self.mask_bottom.get()]
        if self.sub_box.get():
            cmd += ["--box", "--box-color", self.box_color.get()]
        if self.use_free_pos.get():
            cmd += ["--pos-x", self.pos_x.get(), "--pos-y", self.pos_y.get()]
        cmd += self._extra_blur_args() + self._export_args()

        def done(ok):
            if ok:
                self.status_label.configure(text="✔ Hoàn tất gắn phụ đề vào video gốc (không lồng tiếng)", text_color=COLOR_SUCCESS)
                self._show_post_job_success(self.output_path.get().strip())
                messagebox.showinfo(
                    "Hoàn tất",
                    f"Đã gắn phụ đề vào video gốc thành công:\n{self.output_path.get()}\n\n"
                    "✔ Âm thanh gốc của video được giữ nguyên 100% (không lồng tiếng AI)."
                )
            else:
                self.status_label.configure(text="✘ Lỗi gắn phụ đề — bấm ▲ để xem", text_color=COLOR_DANGER)
                if not self._log_expanded:
                    self._toggle_log_panel()
                messagebox.showerror("Lỗi", "Gắn phụ đề thất bại. Xem chi tiết trong Nhật ký.")

        self._run_cmd_async(cmd, on_done=done, active_btn=btn)

    def run_burn_only(self, btn=None):
        """Gắn phụ đề vào video đã lồng tiếng."""
        dub_path = self.dubbed_video_path.get().strip()
        if not dub_path or not os.path.exists(dub_path):
            if self.video_path.get() and os.path.exists(self.video_path.get()):
                ans = messagebox.askyesno(
                    "Chưa có video đã lồng tiếng",
                    "Chưa tìm thấy file video đã lồng tiếng.\n\n"
                    "Bạn có muốn gắn phụ đề trực tiếp vào VIDEO GỐC (giữ nguyên âm thanh gốc, không lồng tiếng) không?"
                )
                if ans:
                    return self.run_burn_original_only(btn=btn)
                return
            messagebox.showwarning("Thiếu video đã lồng tiếng",
                "Hãy chạy 'Chỉ lồng tiếng' trước, hoặc chọn file video đã lồng tiếng sẵn.")
            return
        if not self.srt_path.get() or not os.path.exists(self.srt_path.get()):
            messagebox.showwarning("Thiếu phụ đề", "Hãy tạo/chọn file phụ đề .srt trước.")
            return
        out_dir = self._get_job_initialdir() or (os.path.dirname(self.dubbed_video_path.get()) if self.dubbed_video_path.get() else ".")
        base = os.path.splitext(os.path.basename(self.dubbed_video_path.get() or (self.video_path.get() if hasattr(self, "video_path") else "")))[0].replace("_dalongtieng", "") or "output"
        if not self.output_path.get() or os.path.dirname(self.output_path.get()) != out_dir:
            self.output_path.set(os.path.join(out_dir, f"{base}_output.mp4"))
        if not self._validate_numeric_inputs():
            return
        cmd = [sys.executable, DUB_TOOL, "burn", self.dubbed_video_path.get(), self.srt_path.get(),
               "-o", self.output_path.get(),
               "--font-name", self.font_name.get(),
               "--font-size", self.font_size.get(),
               "--font-color", self.font_color.get(),
               "--outline-color", self.outline_color.get(),
               "--outline-width", self.outline_width.get(),
               "--position", self.sub_position.get()]
        if self.sub_bold.get():
            cmd.append("--bold")
        if self.mask_original.get():
            cmd += ["--mask-original", "--mask-style", self.mask_style.get(),
                    "--mask-blur", self.mask_blur.get(),
                    "--mask-top", self.mask_top.get(), "--mask-bottom", self.mask_bottom.get()]
        if self.sub_box.get():
            cmd += ["--box", "--box-color", self.box_color.get()]
        if self.use_free_pos.get():
            cmd += ["--pos-x", self.pos_x.get(), "--pos-y", self.pos_y.get()]
        cmd += self._extra_blur_args() + self._export_args()
        def done(ok):
            if ok:
                self.status_label.configure(text="✔ Hoàn tất gắn phụ đề", text_color=COLOR_SUCCESS)
                self._show_post_job_success(self.output_path.get().strip())
                messagebox.showinfo("Hoàn tất", f"Đã tạo xong video:\n{self.output_path.get()}")
            else:
                self.status_label.configure(text="✘ Lỗi gắn phụ đề — bấm ▲ để xem", text_color=COLOR_DANGER)
                if not self._log_expanded:
                    self._toggle_log_panel()
                messagebox.showerror("Lỗi", "Gắn phụ đề thất bại. Xem chi tiết trong Nhật ký.")
        self._run_cmd_async(cmd, on_done=done, active_btn=btn)

    def run_all(self, btn=None):
        if not self._require_video():
            return
        if not self.srt_path.get() or not os.path.exists(self.srt_path.get()):
            messagebox.showwarning("Thiếu phụ đề", "Hãy tạo/chọn file phụ đề .srt trước.")
            return
        out_dir = self._get_job_initialdir() or os.path.dirname(self.video_path.get())
        base = os.path.splitext(os.path.basename(self.video_path.get()))[0]
        if not self.output_path.get() or os.path.dirname(self.output_path.get()) != out_dir:
            self.output_path.set(os.path.join(out_dir, f"{base}_output.mp4"))
        if not self.dubbed_video_path.get() or os.path.dirname(self.dubbed_video_path.get()) != out_dir:
            self.dubbed_video_path.set(os.path.join(out_dir, f"{base}_dalongtieng.mp4"))
        if not self._validate_numeric_inputs():
            return
        cmd = [sys.executable, DUB_TOOL, "all", self.video_path.get(), self.srt_path.get(),
               "-o", self.output_path.get(),
               "--voice", self.voice.get(),
               "--tts-engine", self.tts_engine.get()]
        if self.single_voice.get():
            cmd.append("--single-voice")
        else:
            cmd.extend(self._build_speaker_voice_args())
        if self.tts_engine.get() == "capcut":
            cmd += ["--capcut-rate", f"{self.capcut_rate.get():.2f}"]
        cmd += self._audio_mix_args() + [
               "--font-name", self.font_name.get(),
               "--font-size", self.font_size.get(),
               "--font-color", self.font_color.get(),
               "--outline-color", self.outline_color.get(),
               "--outline-width", self.outline_width.get(),
               "--position", self.sub_position.get()]
        if self.sub_bold.get():
            cmd.append("--bold")
        if self.mask_original.get():
            cmd += ["--mask-original", "--mask-style", self.mask_style.get(),
                    "--mask-blur", self.mask_blur.get(),
                    "--mask-top", self.mask_top.get(), "--mask-bottom", self.mask_bottom.get()]
        if self.sub_box.get():
            cmd += ["--box", "--box-color", self.box_color.get()]
        if self.use_free_pos.get():
            cmd += ["--pos-x", self.pos_x.get(), "--pos-y", self.pos_y.get()]
        cmd += self._extra_blur_args() + self._export_args()
        def done(ok):
            if ok:
                self._load_subtitles_into_editor()
                self.status_label.configure(text="✔ Hoàn tất xuất video (Phụ đề đã fit timeline)", text_color=COLOR_SUCCESS)
                self._show_post_job_success(self.output_path.get().strip())
                messagebox.showinfo("Hoàn tất", f"Đã tạo xong video:\n{self.output_path.get()}\n\n✔ Phụ đề đã được tự động đồng bộ khít 100% với giọng lồng tiếng.")
            else:
                self.status_label.configure(text="✘ Lỗi xuất video — bấm ▲ để xem", text_color=COLOR_DANGER)
                if not self._log_expanded:
                    self._toggle_log_panel()
                messagebox.showerror("Lỗi", "Có lỗi khi xuất video. Xem chi tiết trong Nhật ký.")
        self._run_cmd_async(cmd, on_done=done, active_btn=btn)

    def run_mask_preview(self, btn=None):
        if not self._require_video():
            return
        if self.mask_original.get() and not self._validate_numeric_inputs():
            return
        out_dir = self._get_job_initialdir() or os.path.dirname(self.video_path.get()) or "."
        preview_img = os.path.join(out_dir, "_mask_preview.jpg")

        cmd = [sys.executable, DUB_TOOL, "burn", self.video_path.get(), "-",
               "-o", preview_img, "--preview-only",
               "--mask-original", "--mask-style", self.mask_style.get(),
               "--mask-blur", self.mask_blur.get(),
               "--mask-top", self.mask_top.get(), "--mask-bottom", self.mask_bottom.get()]
        cmd += self._extra_blur_args()
        def done(ok):
            if ok and os.path.exists(preview_img):
                self.status_label.configure(text="✔ Hoàn tất xem trước", text_color=COLOR_SUCCESS)
                open_with_default_app(preview_img)
            elif ok:
                self.status_label.configure(text="✔ Hoàn tất xuất ảnh", text_color=COLOR_SUCCESS)
                messagebox.showinfo("Xong", "Đã xuất ảnh xem trước.")
            else:
                self.status_label.configure(text="✘ Lỗi xem trước — bấm ▲ để xem", text_color=COLOR_DANGER)
                if not self._log_expanded:
                    self._toggle_log_panel()
                messagebox.showerror("Lỗi", "Xuất ảnh xem trước thất bại. Xem chi tiết trong Nhật ký.")
        self._run_cmd_async(cmd, on_done=done, active_btn=btn)

    def run_subtitle_preview(self, btn=None):
        if not self._require_video():
            return
        if not self._validate_numeric_inputs():
            return
        out_dir = self._get_job_initialdir() or os.path.dirname(self.video_path.get()) or "."
        preview_img = os.path.join(out_dir, "_subtitle_preview.jpg")

        seek_sec = 3.0
        if hasattr(self, "pos_editor_seek_var"):
            try:
                seek_sec = float(self.pos_editor_seek_var.get() or 3.0)
            except ValueError:
                seek_sec = 3.0

        sub_text = "Phụ đề mẫu tiếng Việt"
        if getattr(self, "_all_subs_data", None) and self._all_subs_data:
            idx = max(0, min(getattr(self, "_current_sub_index", 0), len(self._all_subs_data) - 1))
            sub_text = self._all_subs_data[idx].content.strip() or sub_text

        import tempfile
        fd, tmp_srt = tempfile.mkstemp(suffix="_preview.srt")
        os.close(fd)
        start_t = max(0.0, seek_sec - 0.5)
        end_t = seek_sec + 3.0
        with open(tmp_srt, "w", encoding="utf-8") as f:
            f.write(f"1\n00:00:{start_t:06.3f} --> 00:00:{end_t:06.3f}\n{sub_text}\n".replace(".", ","))

        cmd = [sys.executable, DUB_TOOL, "burn", self.video_path.get(), tmp_srt,
               "-o", preview_img, "--preview",
               "--preview-time", str(seek_sec),
               "--font-name", self.font_name.get(),
               "--font-size", self.font_size.get(),
               "--font-color", self.font_color.get(),
               "--outline-color", self.outline_color.get(),
               "--outline-width", self.outline_width.get(),
               "--position", self.sub_position.get()]
        if self.sub_bold.get():
            cmd.append("--bold")
        if self.sub_box.get():
            cmd += ["--box", "--box-color", self.box_color.get()]
        if self.use_free_pos.get():
            cmd += ["--pos-x", self.pos_x.get(), "--pos-y", self.pos_y.get()]
        if self.mask_original.get():
            cmd += ["--mask-original", "--mask-style", self.mask_style.get(),
                    "--mask-blur", self.mask_blur.get(),
                    "--mask-top", self.mask_top.get(), "--mask-bottom", self.mask_bottom.get()]
        cmd += self._extra_blur_args()

        def done(ok):
            try:
                if os.path.exists(tmp_srt):
                    os.remove(tmp_srt)
            except Exception:
                pass
            if ok and os.path.exists(preview_img):
                self.status_label.configure(text="✔ Hoàn tất xem trước kiểu phụ đề", text_color=COLOR_SUCCESS)
                open_with_default_app(preview_img)
            elif ok:
                self.status_label.configure(text="✔ Hoàn tất xuất ảnh xem trước", text_color=COLOR_SUCCESS)
                messagebox.showinfo("Xong", "Đã xuất ảnh xem trước phụ đề.")
            else:
                self.status_label.configure(text="✘ Lỗi xem trước phụ đề — bấm ▲ để xem", text_color=COLOR_DANGER)
                if not self._log_expanded:
                    self._toggle_log_panel()
                messagebox.showerror("Lỗi", "Xuất ảnh xem trước phụ đề thất bại. Xem chi tiết trong Nhật ký.")
        self._run_cmd_async(cmd, on_done=done, active_btn=btn)

    # ── Trình Chỉnh Vị Trí Trực Quan Nhúng (Embedded Position Editor) ───────
    def _pos_editor_on_pane_configure(self, event):
        if event.width <= 50 or event.height <= 50:
            return
        self._pos_editor_recalc_canvas_size(event.width, event.height)

    def _pos_editor_recalc_canvas_size(self, container_w=None, container_h=None):
        if container_w is None:
            if hasattr(self, "pos_canvas_pane") and self.pos_canvas_pane.winfo_exists():
                container_w = self.pos_canvas_pane.winfo_width()
            else:
                container_w = 600

        if container_h is None:
            if hasattr(self, "pos_canvas_pane") and self.pos_canvas_pane.winfo_exists():
                container_h = self.pos_canvas_pane.winfo_height()
            else:
                container_h = 450

        avail_w = max(180, container_w - 16)
        avail_h = max(120, container_h - 16)

        vid_w = getattr(self, "_pos_editor_vid_w", 1280)
        vid_h = getattr(self, "_pos_editor_vid_h", 720)
        aspect = vid_w / max(1, vid_h)

        cw = avail_w
        ch = int(cw / aspect)
        if ch > avail_h:
            ch = avail_h
            cw = int(ch * aspect)

        cw = max(160, cw)
        ch = max(90, ch)

        curr_cw = getattr(self, "_pos_editor_canvas_w", 533)
        curr_ch = getattr(self, "_pos_editor_canvas_h", 300)

        if abs(cw - curr_cw) >= 2 or abs(ch - curr_ch) >= 2:
            self._pos_editor_canvas_w = cw
            self._pos_editor_canvas_h = ch
            self._pos_editor_update_canvas_display()

    def _pos_editor_update_canvas_display(self):
        if not hasattr(self, "pos_canvas") or not self.pos_canvas.winfo_exists():
            return

        cw = getattr(self, "_pos_editor_canvas_w", 533)
        ch = getattr(self, "_pos_editor_canvas_h", 300)

        self.pos_canvas.configure(width=cw, height=ch)

        is_real = getattr(self, "_pos_editor_mode", "drag") == "real" and getattr(self, "_pos_editor_true_pil_frame", None) is not None
        active_pil = self._pos_editor_true_pil_frame if is_real else getattr(self, "_pos_editor_raw_pil_frame", None)

        if active_pil is not None:
            try:
                resized = active_pil.resize((cw, ch), Image.Resampling.LANCZOS)
                self._pos_canvas_photo = ImageTk.PhotoImage(resized)
                if hasattr(self, "_pos_editor_img_id"):
                    self.pos_canvas.itemconfig(self._pos_editor_img_id, image=self._pos_canvas_photo)
            except Exception as e:
                pass

        if hasattr(self, "_pos_center_guide_line"):
            self.pos_canvas.coords(self._pos_center_guide_line, cw / 2, 0, cw / 2, ch)

        self._pos_editor_sync_from_vars()

    def _pos_editor_toggle_maximize(self):
        self._pos_editor_maximized = not getattr(self, "_pos_editor_maximized", False)

        if self._pos_editor_maximized:
            if hasattr(self, "left_col") and self.left_col.winfo_ismapped():
                self.left_col.pack_forget()
            if hasattr(self, "right_col") and self.right_col.winfo_ismapped():
                self.right_col.pack_forget()
            if hasattr(self, "btn_pos_editor_max"):
                self.btn_pos_editor_max.configure(text="⛶ Thu nhỏ")
        else:
            if hasattr(self, "center_col") and self.center_col.winfo_ismapped():
                self.center_col.pack_forget()
            if hasattr(self, "left_col"):
                self.left_col.pack(side="left", fill="y", padx=(0, 6), pady=0)
            if hasattr(self, "right_col"):
                self.right_col.pack(side="right", fill="y", padx=(6, 0), pady=0)
            if hasattr(self, "center_col"):
                self.center_col.pack(side="left", fill="both", expand=True, padx=0, pady=0)
            if hasattr(self, "btn_pos_editor_max"):
                self.btn_pos_editor_max.configure(text="⛶ Phóng to")

        self.update_idletasks()
        if hasattr(self, "pos_canvas_pane") and self.pos_canvas_pane.winfo_exists():
            self._pos_editor_recalc_canvas_size(
                self.pos_canvas_pane.winfo_width(),
                self.pos_canvas_pane.winfo_height()
            )

        self.update_idletasks()
        if hasattr(self, "pos_canvas_pane") and self.pos_canvas_pane.winfo_exists():
            self._pos_editor_recalc_canvas_size(self.pos_canvas_pane.winfo_width())

    def _pos_editor_on_video_changed(self):
        path = self.video_path.get().strip()
        if path and os.path.isfile(path):
            self._pos_editor_true_pil_frame = None
            self._pos_editor_mode = "drag"
            if hasattr(self, "btn_pos_mode_seg"):
                self.btn_pos_mode_seg.set("🔴 Kéo vị trí")
            self._pos_editor_refresh_frame()
        else:
            self._pos_editor_raw_pil_frame = None
            self._pos_editor_true_pil_frame = None
            if hasattr(self, "pos_canvas") and self.pos_canvas.winfo_exists():
                self.pos_canvas.pack_forget()
            if hasattr(self, "pos_editor_placeholder") and self.pos_editor_placeholder.winfo_exists():
                self.pos_editor_placeholder.pack(fill="both", expand=True, padx=20, pady=30)
            if hasattr(self, "pos_editor_seek_status"):
                self.pos_editor_seek_status.configure(text="")

    def _pos_editor_refresh_frame(self):
        video_path = self.video_path.get().strip()
        if not video_path or not os.path.isfile(video_path):
            return

        try:
            seek_sec = float(self.pos_editor_seek_var.get().strip())
            if seek_sec < 0:
                seek_sec = 0.0
        except ValueError:
            seek_sec = 3.0
            self.pos_editor_seek_var.set("3")

        # Debounce: Nếu một tiến trình capture đang chạy, lưu lại giây cần seek để chạy ngay sau khi xong
        if getattr(self, "_pos_editor_worker_busy", False):
            self._pos_editor_pending_seek = seek_sec
            return

        self._pos_editor_worker_busy = True
        self.pos_editor_seek_status.configure(text="⏳ Đang tải preview...", text_color=COLOR_TEXT_MUTED)
        self._pos_editor_token = getattr(self, "_pos_editor_token", 0) + 1
        cur_token = self._pos_editor_token

        def worker():
            try:
                probe = subprocess.run(
                    ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
                     "-show_entries", "stream=width,height",
                     "-of", "default=noprint_wrappers=1:nokey=1",
                     video_path],
                    capture_output=True, encoding="utf-8", errors="replace", timeout=15
                )
                nums = [ln.strip() for ln in probe.stdout.strip().splitlines() if ln.strip().isdigit()]
                if len(nums) >= 2:
                    self._pos_editor_vid_w, self._pos_editor_vid_h = int(nums[0]), int(nums[1])
                else:
                    self._pos_editor_vid_w, self._pos_editor_vid_h = 1280, 720

                scale_vf = "scale=960:-1:force_original_aspect_ratio=decrease"

                frame_png = os.path.join(tempfile.gettempdir(), f"_pos_canvas_frame_{cur_token}.png")
                subprocess.run(
                    ["ffmpeg", "-y", "-ss", str(seek_sec), "-i", video_path,
                     "-vf", scale_vf,
                     "-frames:v", "1", frame_png],
                    capture_output=True, encoding="utf-8", errors="replace", timeout=30
                )
                if os.path.exists(frame_png):
                    raw_pil = Image.open(frame_png).copy()
                    try:
                        os.remove(frame_png)
                    except Exception:
                        pass
                    if cur_token != getattr(self, "_pos_editor_token", 0):
                        return
                    self._pos_editor_raw_pil_frame = raw_pil

                    def update_ui():
                        if cur_token != getattr(self, "_pos_editor_token", 0):
                            return
                        try:
                            if hasattr(self, "pos_editor_placeholder") and self.pos_editor_placeholder.winfo_ismapped():
                                self.pos_editor_placeholder.pack_forget()
                            self.pos_canvas.pack(fill="both", expand=True)

                            if not getattr(self, "_pos_editor_items_created", False):
                                self._pos_editor_init_canvas_items()

                            self._pos_editor_recalc_canvas_size()
                            self._pos_editor_update_canvas_display()
                            self.pos_editor_seek_status.configure(text=f"✔ Khung {seek_sec:.1f}s", text_color=COLOR_SUCCESS)
                        except Exception as e:
                            self.pos_editor_seek_status.configure(text=f"✘ Lỗi UI: {e}", text_color=COLOR_DANGER)
                    self.run_on_ui_thread(update_ui)
                else:
                    self.run_on_ui_thread(lambda: self.pos_editor_seek_status.configure(text="✘ Lỗi ffmpeg", text_color=COLOR_DANGER))

            except Exception as e:
                err_str = str(e)
                self.run_on_ui_thread(lambda m=err_str: self.pos_editor_seek_status.configure(text=f"✘ Lỗi: {m}", text_color=COLOR_DANGER))
            finally:
                self._pos_editor_worker_busy = False
                pend = getattr(self, "_pos_editor_pending_seek", None)
                if pend is not None:
                    self._pos_editor_pending_seek = None
                    self.run_on_ui_thread(lambda p=pend: (self.pos_editor_seek_var.set(f"{p:.1f}"), self._pos_editor_refresh_frame()))

        threading.Thread(target=worker, daemon=True).start()


    def _pos_editor_init_canvas_items(self):
        cw, ch = self._pos_editor_canvas_w, self._pos_editor_canvas_h

        self._pos_editor_img_id = self.pos_canvas.create_image(0, 0, anchor="nw")
        self._pos_mask_rect = self.pos_canvas.create_rectangle(0, 0, 0, 0, fill="red", stipple="gray25", outline="")
        self._pos_top_line = self.pos_canvas.create_line(0, 0, 0, 0, fill="red", width=3)
        self._pos_bottom_line = self.pos_canvas.create_line(0, 0, 0, 0, fill="red", width=3)

        self._pos_center_guide_line = self.pos_canvas.create_line(
            cw / 2, 0, cw / 2, ch, fill="#29b6f6", width=2, dash=(6, 4), state="hidden"
        )

        self._pos_sub_box = self.pos_canvas.create_rectangle(0, 0, 0, 0, outline="#00c853", width=2)
        # 8 shadow items cho viền nét tròn chuẩn như FreeType/libass
        self._pos_sub_shadows = [
            self.pos_canvas.create_text(0, 0, text="", fill="black", font=(FONT_FAMILY, 14, "bold"))
            for _ in range(8)
        ]
        self._pos_sub_label = self.pos_canvas.create_text(0, 0, text="Vùng phụ đề", fill="white", font=(FONT_FAMILY, 14, "bold"))

        self.pos_canvas.bind("<ButtonPress-1>", self._pos_editor_on_press)
        self.pos_canvas.bind("<B1-Motion>", self._pos_editor_on_drag)
        self.pos_canvas.bind("<ButtonRelease-1>", self._pos_editor_on_release)

        self._pos_editor_eb_canvas_items = []
        self._pos_editor_items_created = True

    def _pos_editor_on_mode_change(self, val):
        """Chuyển đổi giữa chế độ Kéo thả tương tác và Render thật 100% từ FFmpeg."""
        if "Render thật" in val:
            self._pos_editor_mode = "real"
            self._pos_editor_render_true_frame()
        else:
            self._pos_editor_mode = "drag"
            self._pos_editor_update_canvas_display()
            self._pos_editor_sync_from_vars()

    def _pos_editor_on_refresh_clicked(self):
        """Bấm nút Làm mới: tự nhận diện mode đang chọn để làm mới tương ứng."""
        if getattr(self, "_pos_editor_mode", "drag") == "real":
            self._pos_editor_render_true_frame()
        else:
            self._pos_editor_refresh_frame()

    def _pos_editor_render_true_frame(self):
        """Render 1 khung hình thật 100% bằng FFmpeg/libass kèm font, cỡ, viền, vị trí và vùng làm mờ lên Canvas."""
        video_path = self.video_path.get().strip()
        if not video_path or not os.path.isfile(video_path):
            if hasattr(self, "pos_editor_seek_status"):
                self.pos_editor_seek_status.configure(text="⚠ Chưa có video", text_color=COLOR_WARNING)
            return

        try:
            seek_sec = float(self.pos_editor_seek_var.get().strip())
            if seek_sec < 0:
                seek_sec = 0.0
        except ValueError:
            seek_sec = 3.0
            self.pos_editor_seek_var.set("3")

        if getattr(self, "_pos_editor_true_worker_busy", False):
            return

        self._pos_editor_true_worker_busy = True
        if hasattr(self, "pos_editor_seek_status"):
            self.pos_editor_seek_status.configure(text="⏳ Đang render thật...", text_color=COLOR_TEXT_MUTED)

        self._pos_editor_token = getattr(self, "_pos_editor_token", 0) + 1
        cur_token = self._pos_editor_token

        # Thu thập phụ đề hiện tại
        sub_text = "Phụ đề mẫu tiếng Việt"
        if getattr(self, "_all_subs_data", None) and self._all_subs_data:
            idx = max(0, min(getattr(self, "_current_sub_index", 0), len(self._all_subs_data) - 1))
            cur_content = self._all_subs_data[idx].content.strip()
            if cur_content:
                sub_text = cur_content

        f_name = self.font_name.get() or FONT_FAMILY
        try:
            f_size = float(self.font_size.get() or 20)
        except ValueError:
            f_size = 20.0
        f_col = self.font_color.get() or "white"
        o_col = self.outline_color.get() or "black"
        try:
            o_w = float(self.outline_width.get() or 2)
        except ValueError:
            o_w = 2.0
        pos = self.sub_position.get() or "bottom"
        is_bold = self.sub_bold.get()
        use_box = self.sub_box.get()
        box_col = self.box_color.get() or "black"
        use_free = self.use_free_pos.get()
        try:
            px = float(self.pos_x.get() or 0.5)
            py = float(self.pos_y.get() or 0.85)
        except ValueError:
            px, py = 0.5, 0.85

        mask_on = self.mask_original.get()
        mask_st = self.mask_style.get() or "blur"
        try:
            m_blur = float(self.mask_blur.get() or 25)
            m_top = float(self.mask_top.get() or 0.75)
            m_bot = float(self.mask_bottom.get() or 0.97)
        except ValueError:
            m_blur, m_top, m_bot = 25.0, 0.75, 0.97

        eb_args = self._extra_blur_args()

        def worker():
            tmp_srt = os.path.join(tempfile.gettempdir(), f"_temp_preview_{cur_token}.srt")
            out_jpg = os.path.join(tempfile.gettempdir(), f"_pos_true_frame_{cur_token}.jpg")
            try:
                start_t = max(0.0, seek_sec - 0.5)
                end_t = seek_sec + 3.0
                with open(tmp_srt, "w", encoding="utf-8") as f:
                    f.write(f"1\n00:00:{start_t:06.3f} --> 00:00:{end_t:06.3f}\n{sub_text}\n".replace(".", ","))

                cmd = [
                    sys.executable, DUB_TOOL, "burn", video_path, tmp_srt,
                    "-o", out_jpg, "--preview", "--preview-time", str(seek_sec),
                    "--font-name", f_name,
                    "--font-size", str(f_size),
                    "--font-color", f_col,
                    "--outline-color", o_col,
                    "--outline-width", str(o_w),
                    "--position", pos
                ]
                if is_bold:
                    cmd.append("--bold")
                if use_box:
                    cmd += ["--box", "--box-color", box_col]
                if use_free:
                    cmd += ["--pos-x", str(px), "--pos-y", str(py)]
                if mask_on:
                    cmd += ["--mask-original", "--mask-style", mask_st,
                            "--mask-blur", str(m_blur),
                            "--mask-top", str(m_top), "--mask-bottom", str(m_bot)]
                cmd += eb_args

                subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", timeout=30)

                if cur_token != getattr(self, "_pos_editor_token", 0):
                    return

                if os.path.exists(out_jpg):
                    true_pil = Image.open(out_jpg).copy()
                    try:
                        os.remove(out_jpg)
                    except Exception:
                        pass
                    self._pos_editor_true_pil_frame = true_pil
                    self._pos_editor_mode = "real"

                    def update_ui():
                        if cur_token != getattr(self, "_pos_editor_token", 0):
                            return
                        if hasattr(self, "pos_editor_placeholder") and self.pos_editor_placeholder.winfo_ismapped():
                            self.pos_editor_placeholder.pack_forget()
                        self.pos_canvas.pack(fill="both", expand=True)
                        if not getattr(self, "_pos_editor_items_created", False):
                            self._pos_editor_init_canvas_items()

                        self._pos_editor_update_canvas_display()
                        self._pos_editor_sync_from_vars()
                        if hasattr(self, "btn_pos_mode_seg"):
                            self.btn_pos_mode_seg.set("🎬 Render thật")
                        if hasattr(self, "pos_editor_seek_status"):
                            self.pos_editor_seek_status.configure(text=f"✔ Khung thật {seek_sec:.1f}s", text_color=COLOR_SUCCESS)

                    self.run_on_ui_thread(update_ui)
                else:
                    self.run_on_ui_thread(lambda: self.pos_editor_seek_status.configure(text="✘ Lỗi render thật", text_color=COLOR_DANGER))
            except Exception as e:
                err_msg = str(e)
                self.run_on_ui_thread(lambda m=err_msg: self.pos_editor_seek_status.configure(text=f"✘ Lỗi: {m}", text_color=COLOR_DANGER))
            finally:
                self._pos_editor_true_worker_busy = False
                try:
                    if os.path.exists(tmp_srt):
                        os.remove(tmp_srt)
                except Exception:
                    pass

        threading.Thread(target=worker, daemon=True).start()

    def _pos_editor_sync_from_vars(self):
        if not getattr(self, "_pos_editor_items_created", False) or not hasattr(self, "pos_canvas") or not self.pos_canvas.winfo_exists():
            return

        cw, ch = self._pos_editor_canvas_w, self._pos_editor_canvas_h
        is_real = getattr(self, "_pos_editor_mode", "drag") == "real" and getattr(self, "_pos_editor_true_pil_frame", None) is not None

        if is_real:
            # Khi đang xem khung render thật 100%, ẩn toàn bộ các đường nét mô phỏng kéo thả
            self.pos_canvas.itemconfig(self._pos_mask_rect, state="hidden")
            self.pos_canvas.itemconfig(self._pos_top_line, state="hidden")
            self.pos_canvas.itemconfig(self._pos_bottom_line, state="hidden")
            self.pos_canvas.itemconfig(self._pos_sub_box, state="hidden")
            self.pos_canvas.itemconfig(self._pos_sub_label, state="hidden")
            for s_id in getattr(self, "_pos_sub_shadows", []):
                self.pos_canvas.itemconfig(s_id, state="hidden")
            if hasattr(self, "_pos_editor_eb_canvas_items"):
                for item_dict in self._pos_editor_eb_canvas_items:
                    for cid in item_dict.values():
                        if cid:
                            self.pos_canvas.delete(cid)
                self._pos_editor_eb_canvas_items = []

            if hasattr(self, "pos_editor_info_lbl"):
                f_name = self.font_name.get() or FONT_FAMILY
                try:
                    f_val = float(self.font_size.get() or 20)
                except ValueError:
                    f_val = 20.0
                self.pos_editor_info_lbl.configure(text=f"🎬 Khung thật 100% (FFmpeg)\nCỡ: {f_val:g}pt | Font: {f_name}")
            return

        # ── Chế độ Kéo thả (Interactive Drag Mode) ──
        try:
            mt = float(self.mask_top.get() or 0.75)
            mb = float(self.mask_bottom.get() or 0.97)
        except ValueError:
            mt, mb = 0.75, 0.97

        try:
            cl = float(self.crop_left.get() or 0.0)
            cr = float(self.crop_right.get() or 1.0)
        except ValueError:
            cl, cr = 0.0, 1.0

        try:
            px = float(self.pos_x.get() or 0.5)
            py = float(self.pos_y.get() or 0.85)
        except ValueError:
            px, py = 0.5, 0.85

        self.pos_canvas.itemconfig(self._pos_mask_rect, state="normal")
        self.pos_canvas.itemconfig(self._pos_top_line, state="normal")
        self.pos_canvas.itemconfig(self._pos_bottom_line, state="normal")
        self.pos_canvas.coords(self._pos_mask_rect, cl * cw, mt * ch, cr * cw, mb * ch)
        self.pos_canvas.coords(self._pos_top_line, cl * cw, mt * ch, cr * cw, mt * ch)
        self.pos_canvas.coords(self._pos_bottom_line, cl * cw, mb * ch, cr * cw, mb * ch)

        # Lấy câu phụ đề mẫu hoặc câu đang chọn ở editor
        sample_text = "Phụ đề mẫu tiếng Việt"
        if getattr(self, "_all_subs_data", None) and self._all_subs_data:
            idx = max(0, min(getattr(self, "_current_sub_index", 0), len(self._all_subs_data) - 1))
            cur_txt = self._all_subs_data[idx].content.strip()
            if cur_txt:
                sample_text = cur_txt

        try:
            fs_val = float(self.font_size.get() or 20)
        except ValueError:
            fs_val = 20.0

        # Dùng số âm -canvas_fs để Tkinter gán chuẩn theo PIXEL màn hình thay vì point (pt)
        # Tỷ lệ: fs_val trên màn hình 288p chuẩn của libass
        canvas_fs = max(8, int(round(fs_val * (ch / 288.0))))

        f_family = self.font_name.get() or FONT_FAMILY
        f_weight = "bold" if self.sub_bold.get() else "normal"
        c_font = (f_family, -canvas_fs, f_weight)

        font_col = self.font_color.get() or "white"
        outline_col = self.outline_color.get() or "black"
        use_box = self.sub_box.get()
        box_col = self.box_color.get() or "black"

        cx, cy = px * cw, py * ch
        max_wrap_w = max(100, int(cw * 0.82))

        try:
            ow_val = float(self.outline_width.get() or 2)
        except ValueError:
            ow_val = 2.0
        canvas_ow = max(1.0, ow_val * (ch / 288.0))

        # 8 hướng bóng viền để mô phỏng viền bo tròn của FreeType / ASS
        offsets = [
            (-canvas_ow, 0), (canvas_ow, 0), (0, -canvas_ow), (0, canvas_ow),
            (-canvas_ow * 0.7, -canvas_ow * 0.7), (canvas_ow * 0.7, -canvas_ow * 0.7),
            (-canvas_ow * 0.7, canvas_ow * 0.7), (canvas_ow * 0.7, canvas_ow * 0.7)
        ]
        shadows = getattr(self, "_pos_sub_shadows", [])
        for i, s_id in enumerate(shadows):
            if not use_box and outline_col and i < len(offsets):
                ox, oy = offsets[i]
                self.pos_canvas.itemconfig(
                    s_id, text=sample_text, font=c_font, fill=outline_col,
                    width=max_wrap_w, justify="center", state="normal"
                )
                self.pos_canvas.coords(s_id, cx + ox, cy + oy)
            else:
                self.pos_canvas.itemconfig(s_id, state="hidden")

        # Cập nhật chữ chính
        self.pos_canvas.itemconfig(
            self._pos_sub_label, text=sample_text, font=c_font, fill=font_col,
            width=max_wrap_w, justify="center", state="normal"
        )
        self.pos_canvas.coords(self._pos_sub_label, cx, cy)

        # Bounding box chuẩn xác ôm sát chữ
        bbox = self.pos_canvas.bbox(self._pos_sub_label)
        if bbox:
            pad_x = max(8, int(round(canvas_fs * 0.35)))
            pad_y = max(4, int(round(canvas_fs * 0.2)))
            bx1, by1, bx2, by2 = bbox[0] - pad_x, bbox[1] - pad_y, bbox[2] + pad_x, bbox[3] + pad_y
        else:
            box_w = cw * 0.7
            box_h = canvas_fs * 1.8
            bx1, by1, bx2, by2 = cx - box_w / 2, cy - box_h / 2, cx + box_w / 2, cy + box_h / 2

        self.pos_canvas.coords(self._pos_sub_box, bx1, by1, bx2, by2)
        if use_box:
            self.pos_canvas.itemconfig(self._pos_sub_box, fill=box_col, outline="#00c853", width=2, dash=(), state="normal")
        else:
            self.pos_canvas.itemconfig(self._pos_sub_box, fill="", outline="#00c853", width=2, dash=(4, 3), state="normal")

        if hasattr(self, "_pos_editor_eb_canvas_items"):
            for item_dict in self._pos_editor_eb_canvas_items:
                for cid in item_dict.values():
                    if cid:
                        self.pos_canvas.delete(cid)
        self._pos_editor_eb_canvas_items = []

        COLORS_EB = ["#ff8c00", "#ff4500", "#ff1493", "#9400d3", "#00bcd4"]
        for i, (top_v, bot_v, str_v, lft_v, rgt_v, _) in enumerate(self._extra_blur_rows):
            try:
                t = float(top_v.get()); b = float(bot_v.get())
                l = float(lft_v.get()); r = float(rgt_v.get())
            except ValueError:
                t, b, l, r = 0.0, 0.15, 0.0, 1.0
            col = COLORS_EB[i % len(COLORS_EB)]
            lx, rx = l * cw, r * cw
            ty, by = t * ch, b * ch
            r_id = self.pos_canvas.create_rectangle(lx, ty, rx, by, fill=col, stipple="gray50", outline="")
            tl_id = self.pos_canvas.create_line(lx, ty, rx, ty, fill=col, width=3, dash=(6, 3))
            bl_id = self.pos_canvas.create_line(lx, by, rx, by, fill=col, width=3, dash=(6, 3))
            ll_id = self.pos_canvas.create_line(lx, ty, lx, by, fill=col, width=3, dash=(4, 4))
            rl_id = self.pos_canvas.create_line(rx, ty, rx, by, fill=col, width=3, dash=(4, 4))
            self._pos_editor_eb_canvas_items.append({
                "rect": r_id, "top": tl_id, "bot": bl_id, "left": ll_id, "right": rl_id
            })

        self.pos_canvas.tag_raise(self._pos_sub_box)
        if hasattr(self, "_pos_sub_shadows"):
            for s_id in self._pos_sub_shadows:
                self.pos_canvas.tag_raise(s_id)
        self.pos_canvas.tag_raise(self._pos_sub_label)
        self.pos_canvas.tag_raise(self._pos_top_line)
        self.pos_canvas.tag_raise(self._pos_bottom_line)
        self.pos_canvas.tag_raise(self._pos_center_guide_line)

        info_txt = f"Mask: {mt:.3f} → {mb:.3f}\nSub: X={px:.3f}, Y={py:.3f}\nCỡ chữ: {fs_val:g}pt"
        if hasattr(self, "pos_editor_info_lbl"):
            self.pos_editor_info_lbl.configure(text=info_txt)

    def _pos_editor_on_press(self, event):
        # Nếu đang ở chế độ xem render thật, khi người dùng click vào canvas để kéo thả thì tự động chuyển về chế độ kéo thả
        if getattr(self, "_pos_editor_mode", "drag") == "real":
            self._pos_editor_mode = "drag"
            if hasattr(self, "btn_pos_mode_seg"):
                self.btn_pos_mode_seg.set("🔴 Kéo vị trí")
            self._pos_editor_update_canvas_display()
            self._pos_editor_sync_from_vars()
        HIT = 10
        cw, ch = self._pos_editor_canvas_w, self._pos_editor_canvas_h

        for i, (top_v, bot_v, str_v, lft_v, rgt_v, _) in enumerate(self._extra_blur_rows):
            try:
                t = float(top_v.get()); b = float(bot_v.get())
                l = float(lft_v.get()); r = float(rgt_v.get())
            except ValueError:
                continue
            ty, by = t * ch, b * ch
            lx, rx = l * cw, r * cw
            if abs(event.y - ty) < HIT and lx - HIT <= event.x <= rx + HIT:
                self._pos_editor_dragging = ("eb_top", i)
                return
            if abs(event.y - by) < HIT and lx - HIT <= event.x <= rx + HIT:
                self._pos_editor_dragging = ("eb_bot", i)
                return
            if abs(event.x - lx) < HIT and ty - HIT <= event.y <= by + HIT:
                self._pos_editor_dragging = ("eb_left", i)
                return
            if abs(event.x - rx) < HIT and ty - HIT <= event.y <= by + HIT:
                self._pos_editor_dragging = ("eb_right", i)
                return

        try:
            mt = float(self.mask_top.get() or 0.75)
            mb = float(self.mask_bottom.get() or 0.97)
        except ValueError:
            mt, mb = 0.75, 0.97

        if abs(event.y - mt * ch) < HIT:
            self._pos_editor_dragging = "top"
            return
        if abs(event.y - mb * ch) < HIT:
            self._pos_editor_dragging = "bottom"
            return

        if self.use_free_pos.get():
            coords = self.pos_canvas.coords(self._pos_sub_box)
            if coords and len(coords) == 4:
                if coords[0] - 5 <= event.x <= coords[2] + 5 and coords[1] - 5 <= event.y <= coords[3] + 5:
                    self._pos_editor_dragging = "sub"
                    return

    def _pos_editor_on_drag(self, event):
        cw, ch = self._pos_editor_canvas_w, self._pos_editor_canvas_h
        d = self._pos_editor_dragging
        if not d:
            return

        if d == "top":
            mb = float(self.mask_bottom.get() or 0.97)
            val = max(0.0, min(event.y / ch, mb - 0.02))
            self.mask_top.set(f"{val:.3f}")
        elif d == "bottom":
            mt = float(self.mask_top.get() or 0.75)
            val = min(1.0, max(event.y / ch, mt + 0.02))
            self.mask_bottom.set(f"{val:.3f}")
        elif d == "sub":
            raw_x = max(0.0, min(event.x / cw, 1.0))
            if abs(raw_x - 0.5) < 0.025 or abs(event.x - cw / 2) < 12:
                self.pos_x.set("0.500")
                if hasattr(self, "_pos_center_guide_line"):
                    self.pos_canvas.itemconfig(self._pos_center_guide_line, state="normal")
            else:
                self.pos_x.set(f"{raw_x:.3f}")
                if hasattr(self, "_pos_center_guide_line"):
                    self.pos_canvas.itemconfig(self._pos_center_guide_line, state="hidden")
            raw_y = max(0.0, min(event.y / ch, 1.0))
            self.pos_y.set(f"{raw_y:.3f}")
        elif isinstance(d, tuple):
            mode, idx = d
            eb_list = self._extra_blur_rows
            if 0 <= idx < len(eb_list):
                top_v, bot_v, str_v, lft_v, rgt_v, _ = eb_list[idx]
                if mode == "eb_top":
                    b_val = float(bot_v.get() or 0.15)
                    top_v.set(f"{max(0.0, min(event.y / ch, b_val - 0.02)):.3f}")
                elif mode == "eb_bot":
                    t_val = float(top_v.get() or 0.0)
                    bot_v.set(f"{min(1.0, max(event.y / ch, t_val + 0.02)):.3f}")
                elif mode == "eb_left":
                    r_val = float(rgt_v.get() or 1.0)
                    lft_v.set(f"{max(0.0, min(event.x / cw, r_val - 0.02)):.3f}")
                elif mode == "eb_right":
                    l_val = float(lft_v.get() or 0.0)
                    rgt_v.set(f"{min(1.0, max(event.x / cw, l_val + 0.02)):.3f}")

        self._pos_editor_sync_from_vars()

    def _pos_editor_on_release(self, event):
        self._pos_editor_dragging = None
        if hasattr(self, "_pos_center_guide_line") and hasattr(self, "pos_canvas") and self.pos_canvas.winfo_exists():
            self.pos_canvas.itemconfig(self._pos_center_guide_line, state="hidden")

    def _pos_editor_center_x(self):
        self.pos_x.set("0.500")
        if hasattr(self, "_pos_center_guide_line") and hasattr(self, "pos_canvas") and self.pos_canvas.winfo_exists():
            self.pos_canvas.itemconfig(self._pos_center_guide_line, state="normal")
            self.after(1000, lambda: self.pos_canvas.itemconfig(self._pos_center_guide_line, state="hidden"))
        self._pos_editor_sync_from_vars()

    def _pos_editor_center_y(self):
        self.pos_y.set("0.500")
        self._pos_editor_sync_from_vars()

    def _pos_editor_bottom_y(self):
        self.pos_y.set("0.850")
        self._pos_editor_sync_from_vars()

    def run_preview_voice(self, specific_voice=None, btn=None):
        """Nghe thử giọng đọc mẫu bằng engine + voice đang chọn."""
        engine = self.tts_engine.get().strip()
        voice = (specific_voice or self.voice.get()).strip()
        rate_val = self.capcut_rate.get()
        target_btn = btn or self.btn_preview_voice

        if voice == "Mặc định (theo AI)":
            voice = self.voice.get().strip()
        elif voice.startswith("Gộp vào "):
            target_spk = voice.replace("Gộp vào ", "").strip()
            if target_spk in getattr(self, "speaker_voice_vars", {}):
                resolved = self.speaker_voice_vars[target_spk].get().strip()
                voice = self.voice.get().strip() if (resolved == "Mặc định (theo AI)" or resolved.startswith("Gộp vào ")) else resolved
            else:
                voice = self.voice.get().strip()

        if not voice:
            messagebox.showwarning("Chưa chọn giọng", "Vui lòng chọn giọng đọc trước khi nghe thử.")
            return

        if self._job_running:
            messagebox.showwarning("Đang chạy", "Đang có tiến trình khác đang chạy. Vui lòng chờ.")
            return

        safe_voice = re.sub(r'[^\w\-]', '_', voice)
        cache_filename = f"preview_{engine}_{safe_voice}.wav"
        cache_filepath = os.path.join(tempfile.gettempdir(), cache_filename)

        if target_btn:
            target_btn.configure(text="⏳", state="disabled")

        def reset_btn():
            try:
                if target_btn:
                    target_btn.configure(text="▶", state="normal")
            except Exception:
                pass

        def worker():
            try:
                if not (os.path.exists(cache_filepath) and os.path.getsize(cache_filepath) > 0):
                    self.log_write(f"→ Đang tạo mẫu thử giọng ({engine} / {voice})...\n")
                    script_dir_repr = repr(os.path.abspath(SCRIPT_DIR))
                    voice_repr = repr(voice)
                    engine_repr = repr(engine)
                    cache_filepath_repr = repr(cache_filepath)

                    py_code = (
                        f"import sys; sys.path.insert(0, {script_dir_repr}); "
                        f"from core.tts import generate_voice_preview; "
                        f"generate_voice_preview({engine_repr}, {voice_repr}, {cache_filepath_repr}, {rate_val})"
                    )
                    cmd = [sys.executable, "-c", py_code]
                    env = os.environ.copy()
                    env["PYTHONIOENCODING"] = "utf-8"
                    env["PYTHONUNBUFFERED"] = "1"

                    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=60)

                    if proc.returncode != 0 or not os.path.exists(cache_filepath):
                        err_msg = proc.stderr.strip() or proc.stdout.strip() or "Không tạo được file audio thử giọng."
                        self.log_write(f"✘ Lỗi tạo mẫu thử giọng: {err_msg}\n")
                        self.after(0, lambda: messagebox.showerror("Lỗi thử giọng", f"Không thể tạo giọng đọc mẫu:\n{err_msg}"))
                        self.after(0, reset_btn)
                        return

                self.log_write(f"▶ Đang phát giọng đọc mẫu: {engine} / {voice}\n")
                play_audio_file(cache_filepath)

            except Exception as e:
                self.log_write(f"✘ Lỗi khi thử giọng: {e}\n")
                self.after(0, lambda: messagebox.showerror("Lỗi thử giọng", f"Có lỗi xảy ra khi nghe thử giọng:\n{e}"))
            finally:
                self.after(0, reset_btn)

        threading.Thread(target=worker, daemon=True).start()



if __name__ == "__main__":
    app = DubToolGUI()
    app.mainloop()
