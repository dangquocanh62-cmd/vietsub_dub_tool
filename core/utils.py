"""
TIỆN ÍCH CHUNG CHO DUB TOOL
"""

import hashlib
import os
import subprocess
import sys
from tqdm import tqdm

# Ép stdout/stderr dùng UTF-8, tránh lỗi UnicodeEncodeError trên Windows
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass


def run(cmd):
    """Chạy 1 lệnh shell, in lỗi rõ ràng nếu thất bại."""
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace"
    )
    if result.returncode != 0:
        print("LỖI khi chạy lệnh:", " ".join(cmd))
        print(result.stderr[-2000:])
        sys.exit(1)
    return result


def run_ffmpeg_with_progress(cmd, total_sec=None, desc="Đang xuất video"):
    """Chạy FFmpeg kèm hiển thị tiến độ thời gian thực (%, thời gian, fps, tốc độ).
    
    Tương thích với GUI regex và terminal, ném ngoại lệ rõ ràng nếu gặp lỗi.
    Sử dụng luồng đọc ngầm (background thread) cho stderr để chống nghẽn pipe buffer (deadlock).
    """
    import threading
    import collections

    cmd_with_prog = list(cmd)
    if "-progress" not in cmd_with_prog:
        cmd_with_prog.extend(["-progress", "pipe:1", "-nostats"])

    proc = subprocess.Popen(
        cmd_with_prog,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        universal_newlines=True
    )

    stderr_lines = collections.deque(maxlen=100)

    def _drain_stderr():
        try:
            for eline in proc.stderr:
                stderr_lines.append(eline)
        except Exception:
            pass

    err_thread = threading.Thread(target=_drain_stderr, daemon=True)
    err_thread.start()

    cur_sec = 0.0
    speed = "N/A"
    fps = "N/A"

    for line in proc.stdout:
        line = line.strip()
        if line.startswith("out_time_us="):
            us_str = line.split("=", 1)[1]
            if us_str.isdigit():
                cur_sec = int(us_str) / 1_000_000.0
        elif line.startswith("speed="):
            speed = line.split("=", 1)[1].strip()
        elif line.startswith("fps="):
            fps = line.split("=", 1)[1].strip()
        elif line.startswith("progress="):
            if total_sec and total_sec > 0:
                pct = min(100.0, max(0.0, (cur_sec / total_sec) * 100.0))
                msg = f"\r  ⏳ {desc}: {int(pct):3d}%| [{cur_sec:5.1f}s / {total_sec:5.1f}s] (fps: {fps}, speed: {speed})"
            else:
                msg = f"\r  ⏳ {desc}: [{cur_sec:5.1f}s] (fps: {fps}, speed: {speed})"
            sys.stdout.write(msg)
            sys.stdout.flush()

    err_thread.join(timeout=3)
    proc.wait()
    sys.stdout.write("\n")
    sys.stdout.flush()

    if proc.returncode != 0:
        stderr_out = "".join(stderr_lines)
        raise RuntimeError(f"FFmpeg thất bại (mã lỗi {proc.returncode}):\n{stderr_out[-2000:]}")
    return proc



def get_video_duration(video_path: str) -> float:
    out = run([
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "csv=p=0", video_path
    ])
    return float(out.stdout.strip())


def get_video_duration_seconds(video_path: str) -> float:
    out = run([
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "csv=p=0", video_path
    ])
    return float(out.stdout.strip().splitlines()[0])


def get_video_dimensions(video_path: str):
    out = run([
        "ffprobe", "-v", "quiet", "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "default=noprint_wrappers=1:nokey=1", video_path
    ])
    nums = [ln.strip() for ln in out.stdout.strip().splitlines() if ln.strip().isdigit()]
    if len(nums) < 2:
        raise RuntimeError(
            f"ffprobe không trả về đủ kích thước video cho: {video_path}\n"
            f"stdout thô: {out.stdout!r}"
        )
    return int(nums[0]), int(nums[1])


def is_video_hdr(video_path: str) -> bool:
    """Kiểm tra video có phải là HDR (BT.2020, HLG arib-std-b67, PQ smpte2084, 10-bit) hay không."""
    if not video_path or not os.path.isfile(video_path):
        return False
    try:
        cmd = [
            "ffprobe", "-v", "quiet", "-select_streams", "v:0",
            "-show_entries", "stream=pix_fmt,color_space,color_transfer,color_primaries",
            "-of", "default=noprint_wrappers=1:nokey=0",
            video_path
        ]
        out = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=10)
        lines = out.stdout.lower()
        if any(hdr_kw in lines for hdr_kw in ["bt2020", "arib-std-b67", "smpte2084", "10le", "10be", "12le", "12be"]):
            return True
    except Exception:
        pass
    return False



def _safe_blur_radius(video_path: str, top: float, bottom: float, requested: int, left: float = 0.0, right: float = 1.0) -> int:
    """boxblur của ffmpeg giới hạn bán kính blur theo kích thước THẬT của
    vùng bị crop (cả chiều rộng lẫn chiều cao, đặc biệt mặt phẳng màu chroma bị giảm 1 nửa kích thước do
    định dạng yuv420p). Tự động hạ bán kính xuống mức an toàn tương ứng."""
    try:
        w, h = get_video_dimensions(video_path)
    except Exception:
        return requested
    crop_h = max(int(round(h * abs(bottom - top))), 2)
    crop_w = max(int(round(w * abs(right - left))), 2)
    min_dim = min(crop_h, crop_w)
    chroma_px = max(min_dim // 2, 2)
    safe_max = max(0, chroma_px // 2 - 1)
    if requested > safe_max:
        print(f"  ⚠ Độ mờ yêu cầu ({requested}) quá lớn so với kích thước vùng che "
              f"(~{crop_w}x{crop_h}px) — tự động giảm xuống {safe_max} để tránh lỗi ffmpeg.")
        return safe_max
    return max(0, requested)


def _escape_ffmpeg_path(path: str) -> str:
    """Chuẩn hóa đường dẫn để nhúng vào filter_complex của ffmpeg."""
    p = path.replace("\\", "/")
    p = p.replace(":", "\\:")
    p = p.replace(" ", "\\ ")
    return p


def td_to_ms(td) -> int:
    return int(td.total_seconds() * 1000)


def _looks_non_vietnamese(text: str) -> bool:
    """Ước lượng nhanh: văn bản có nhiều ký tự CJK không?"""
    if not text:
        return False
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff" or "\u3040" <= ch <= "\u30ff" or "\uac00" <= ch <= "\ud7a3")
    return cjk / max(len(text), 1) > 0.2


def _cache_key(text: str, voice: str) -> str:
    return hashlib.sha1(f"{voice}::{text}".encode("utf-8")).hexdigest()[:16]


def get_cache_dir(script_path: str) -> str:
    """Thư mục lưu lại các câu đã lồng tiếng thành công, đặt cạnh file .srt."""
    base = os.path.splitext(os.path.basename(script_path))[0]
    parent = os.path.dirname(os.path.abspath(script_path)) or "."
    d = os.path.join(parent, f".dubcache_{base}")
    os.makedirs(d, exist_ok=True)
    return d


def _download_with_progress(url: str, dest_path: str, label: str):
    """Tải 1 file có hiện % tiến trình."""
    import urllib.request
    last_pct_shown = -10

    def _hook(block_num, block_size, total_size):
        nonlocal last_pct_shown
        if total_size <= 0:
            return
        pct = min(int(block_num * block_size * 100 / total_size), 100)
        if pct >= last_pct_shown + 10 or pct == 100:
            tqdm.write(f"    {label}: {pct}%")
            last_pct_shown = pct

    tmp_path = dest_path + ".part"
    urllib.request.urlretrieve(url, tmp_path, reporthook=_hook)
    os.replace(tmp_path, dest_path)


def _to_ass_color(color_str: str) -> str:
    """Chuyển màu sang định dạng ASS/libass (&HAABBGGRR)."""
    _named = {
        "white": "&H00FFFFFF", "black": "&H00000000", "yellow": "&H0000FFFF",
        "red": "&H000000FF", "green": "&H0000FF00", "blue": "&H00FF0000",
        "cyan": "&H00FFFF00", "magenta": "&H00FF00FF", "orange": "&H000080FF",
        "gray": "&H00808080", "grey": "&H00808080", "transparent": "&H00000000",
    }
    s = color_str.strip().lower()
    if s in _named:
        return _named[s]
    s_orig = color_str.strip()
    if s_orig.startswith("#") and len(s_orig) in (7, 9):
        r = s_orig[1:3]; g = s_orig[3:5]; b = s_orig[5:7]
        a = s_orig[7:9] if len(s_orig) == 9 else "00"
        return f"&H{a}{b}{g}{r}".upper()
    return color_str


def strip_speaker_tag(text: str) -> str:
    """Loại bỏ tag speaker khỏi text phụ đề, trả về text gốc sạch.

    Hàm này là điểm DUY NHẤT để strip tag — mọi module khác (translate,
    tts, gui hiển thị) phải dùng hàm này thay vì tự regex.

    Xử lý các dạng:
        "[Người 1] Xin chào"              -> "Xin chào"
        "[?] Xin chào"                     -> "Xin chào"
        "[Người 2] Xin chào [⚠ SPEAKER KHÔNG CHẮC]" -> "Xin chào"
    """
    import re
    # Bỏ prefix [Người X] hoặc [?]
    text = re.sub(r'^\[(?:Người\s*\d+|\?)\]\s*', '', text)
    # Bỏ hậu tố [⚠ SPEAKER KHÔNG CHẮC]
    text = re.sub(r'\s*\[⚠\s*SPEAKER KHÔNG CHẮC\]\s*$', '', text)
    return text.strip()


def extract_speaker_label(text: str):
    """Trích xuất nhãn người nói từ text phụ đề nếu có (ví dụ: 'Người 1', 'Người 2').

    Nếu là '[?]' hoặc không có tag người nói, trả về None.
    Xử lý các dạng:
        "[Người 1] Xin chào"              -> "Người 1"
        "[Người 2] Xin chào [⚠ ...]"       -> "Người 2"
        "[?] Xin chào"                     -> None
        "Xin chào"                         -> None
    """
    import re
    if not text:
        return None
    m = re.match(r'^\[(Người\s*\d+)\]', text.strip())
    if m:
        return m.group(1).strip()
    return None

