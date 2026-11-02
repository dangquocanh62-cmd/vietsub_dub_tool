"""
MODULE TẢI VIDEO TỪ LINK (DOUYIN, TIKTOK, YOUTUBE, FACEBOOK...)
TỰ ĐỘNG LOẠI BỎ WATERMARK (LOGO DOUYIN / TIKTOK)
"""

import os
import re
import sys
import time
import json
import base64
import urllib.parse
from typing import Callable, Optional, Tuple

import requests
from bs4 import BeautifulSoup


def extract_url(text: str) -> Optional[str]:
    """
    Trích xuất đường link http(s) từ chuỗi văn bản bất kỳ
    (hỗ trợ trường hợp người dùng copy nguyên đoạn văn bản chia sẻ từ app Douyin/TikTok).
    """
    if not text:
        return None
    # Tìm link http:// hoặc https://
    match = re.search(r'https?://[^\s<>"]+', text.strip())
    if match:
        url = match.group(0)
        # Loại bỏ các ký tự dấu câu thừa ở cuối nếu có (.,;:?!)
        url = re.sub(r'[.,;:!?]+$', '', url)
        return url
    return None


def resolve_redirects(url: str) -> str:
    """
    Theo dõi và giải mã link rút gọn (v.douyin.com, vt.tiktok.com, youtu.be, bit.ly...)
    thành URL đích thực tế.
    """
    if not url:
        return url
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
            )
        }
        res = requests.get(url, headers=headers, allow_redirects=True, timeout=10)
        return res.url
    except Exception:
        return url


def sanitize_filename(name: str, max_length: int = 80) -> str:
    """Loại bỏ ký tự không hợp lệ trên Windows và giới hạn độ dài tên file."""
    if not name:
        return f"video_{int(time.time())}"
    # Thay thế các ký tự cấm: \ / : * ? " < > |
    clean = re.sub(r'[\\/*?:"<>|]', '_', name)
    clean = re.sub(r'\s+', ' ', clean).strip()
    if len(clean) > max_length:
        clean = clean[:max_length].rstrip()
    return clean or f"video_{int(time.time())}"


def _get_default_download_dir() -> str:
    """Trả về thư mục Downloads của người dùng, hoặc thư mục downloads trong project."""
    user_dl = os.path.join(os.path.expanduser("~"), "Downloads")
    if os.path.isdir(user_dl):
        return user_dl
    cwd_dl = os.path.abspath("downloads")
    os.makedirs(cwd_dl, exist_ok=True)
    return cwd_dl


def _download_stream(
    stream_url: str,
    output_path: str,
    progress_cb: Optional[Callable[[str, float], None]] = None,
    headers: Optional[dict] = None,
    session: Optional[requests.Session] = None,
) -> str:
    """Tải file theo stream với báo cáo tiến trình thực tế theo MB & %."""
    h = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.douyin.com/"
    }
    if headers:
        h.update(headers)

    requester = session if session is not None else requests
    res = requester.get(stream_url, headers=h, stream=True, timeout=60)
    res.raise_for_status()

    total_bytes = int(res.headers.get("content-length", 0))
    downloaded = 0
    chunk_size = 1024 * 1024  # 1 MB

    start_time = time.time()
    last_cb_time = 0.0

    with open(output_path, "wb") as f:
        for chunk in res.iter_content(chunk_size=chunk_size):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                now = time.time()
                if progress_cb and (now - last_cb_time >= 0.2 or downloaded == total_bytes):
                    last_cb_time = now
                    elapsed = max(0.001, now - start_time)
                    speed_mb = (downloaded / (1024 * 1024)) / elapsed
                    if total_bytes > 0:
                        pct = min(0.99, downloaded / total_bytes)
                        mb_cur = downloaded / (1024 * 1024)
                        mb_tot = total_bytes / (1024 * 1024)
                        progress_cb(f"Đang tải video: {mb_cur:.1f}MB / {mb_tot:.1f}MB ({int(pct * 100)}%) - {speed_mb:.1f}MB/s", pct)
                    else:
                        mb_cur = downloaded / (1024 * 1024)
                        progress_cb(f"Đang tải video: {mb_cur:.1f}MB ({speed_mb:.1f}MB/s)...", 0.5)

    return output_path


def _download_snapdouyin(
    url: str,
    output_dir: str,
    progress_cb: Optional[Callable[[str, float], None]] = None
) -> Tuple[str, str]:
    """
    Sử dụng SnapDouyin Engine chuyên bóc tách luồng HD không Watermark / Logo cho Douyin.
    """
    if progress_cb:
        progress_cb("Đang kết nối tới SnapDouyin (bóc tách video không logo)...", 0.05)

    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://snapdouyin.app/vi/",
        "Origin": "https://snapdouyin.app",
    }
    r = session.get("https://snapdouyin.app/vi/", headers=headers, timeout=12)
    if r.status_code != 200:
        raise RuntimeError(f"SnapDouyin gateway HTTP {r.status_code}")

    soup = BeautifulSoup(r.text, "html.parser")
    token_elem = soup.find(id="token")
    if not token_elem:
        raise RuntimeError("Không tìm thấy session token trên SnapDouyin")
    token = token_elem.get("value")

    salt = "aio-dl"
    h = base64.b64encode(url.encode()).decode() + str(len(url) + 1000) + base64.b64encode(salt.encode()).decode()

    if progress_cb:
        progress_cb("Đang giải mã liên kết video Douyin gốc...", 0.1)

    resp = session.post(
        "https://snapdouyin.app/wp-json/mx-downloader/video-data/",
        headers=headers,
        data={"url": url, "token": token, "hash": h},
        timeout=18
    )
    if resp.status_code != 200:
        raise RuntimeError(f"SnapDouyin API HTTP {resp.status_code}")

    data = resp.json()
    err = data.get("error")
    if err:
        raise RuntimeError(f"SnapDouyin báo lỗi: {err}")

    medias = data.get("medias", [])
    if not medias:
        raise RuntimeError("SnapDouyin không tìm thấy luồng tải video hợp lệ")

    # Ưu tiên chất lượng cao nhất không watermark (hd ⭐ hoặc hd hoặc sd)
    target_media = None
    for m in medias:
        q = str(m.get("quality", "")).lower()
        if "watermark" not in q and m.get("videoAvailable", True):
            target_media = m
            break
    if not target_media:
        target_media = medias[0]

    dl_url = target_media.get("url")
    if not dl_url:
        raise RuntimeError("Không tìm thấy đường link tải video từ SnapDouyin")

    raw_title = data.get("title") or f"douyin_{int(time.time())}"
    safe_name = sanitize_filename(raw_title)
    video_id = str(int(time.time()))[-6:]
    filename = f"{safe_name}_{video_id}.mp4"
    out_file = os.path.join(output_dir, filename)

    if progress_cb:
        q_label = str(target_media.get("quality", "HD")).replace("⭐", "gốc")
        sz_label = target_media.get("formattedSize", "")
        progress_cb(f"Bắt đầu tải video không watermark ({q_label} {sz_label})...", 0.15)

    stream_headers = {
        "Referer": "https://snapdouyin.app/",
        "User-Agent": headers["User-Agent"]
    }
    _download_stream(dl_url, out_file, progress_cb=progress_cb, headers=stream_headers, session=session)

    if progress_cb:
        progress_cb("Hoàn tất tải video không watermark!", 1.0)

    return out_file, raw_title


def _download_tikwm(
    url: str,
    output_dir: str,
    progress_cb: Optional[Callable[[str, float], None]] = None
) -> Tuple[str, str]:
    """
    Sử dụng TikWM API để lấy link video sạch (loại bỏ Watermark) cho TikTok và Douyin.
    """
    if progress_cb:
        progress_cb("Đang phân tích link TikWM (loại bỏ watermark)...", 0.05)

    api_url = "https://www.tikwm.com/api/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    resp = requests.get(
        api_url,
        params={"url": url, "hd": 1},
        headers=headers,
        timeout=15
    )
    if resp.status_code != 200:
        raise RuntimeError(f"TikWM API HTTP {resp.status_code}")

    res_json = resp.json()
    if res_json.get("code") != 0:
        msg = res_json.get("msg", "Lỗi lấy dữ liệu từ TikWM")
        raise RuntimeError(f"TikWM: {msg}")

    data = res_json.get("data", {})
    play_url = data.get("hdplay") or data.get("play")
    if not play_url:
        raise RuntimeError("TikWM không tìm thấy link video không watermark")

    if play_url.startswith("/"):
        play_url = f"https://www.tikwm.com{play_url}"

    title = data.get("title") or f"video_{int(time.time())}"
    safe_name = sanitize_filename(title)
    video_id = data.get("id", str(int(time.time())))
    filename = f"{safe_name}_{video_id[-6:]}.mp4"
    out_file = os.path.join(output_dir, filename)

    if progress_cb:
        progress_cb("Bắt đầu tải luồng video không watermark...", 0.1)

    _download_stream(play_url, out_file, progress_cb=progress_cb)

    if progress_cb:
        progress_cb("Hoàn tất tải video không watermark!", 1.0)

    return out_file, title


def _download_ytdlp(
    url: str,
    output_dir: str,
    progress_cb: Optional[Callable[[str, float], None]] = None
) -> Tuple[str, str]:
    """
    Sử dụng yt-dlp để tải video chất lượng tốt nhất và sạch watermark từ đa nền tảng
    (YouTube, Facebook, Bilibili, Kuaishou, Twitter/X, TikTok...).
    """
    try:
        import yt_dlp
    except ImportError:
        raise RuntimeError("Chưa cài đặt thư viện yt-dlp. Vui lòng chạy: pip install yt-dlp")

    if progress_cb:
        progress_cb("Đang phân tích link bằng yt-dlp...", 0.05)

    title_holder = {"title": "video", "filepath": None}

    def hook(d):
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            if total > 0:
                pct = min(0.99, downloaded / total)
                mb_cur = downloaded / (1024 * 1024)
                mb_tot = total / (1024 * 1024)
                speed = d.get("speed") or 0
                speed_str = f" - {speed / (1024 * 1024):.1f} MB/s" if speed else ""
                if progress_cb:
                    progress_cb(f"Đang tải: {mb_cur:.1f}MB / {mb_tot:.1f}MB ({int(pct * 100)}%){speed_str}", pct)
            else:
                mb_cur = downloaded / (1024 * 1024)
                if progress_cb:
                    progress_cb(f"Đang tải: {mb_cur:.1f}MB...", 0.5)
        elif d.get("status") == "finished":
            if progress_cb:
                progress_cb("Đang hoàn thiện file video...", 0.98)

    out_template = os.path.join(output_dir, "%(title).80s_%(id)s.%(ext)s")
    ydl_opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best",
        "outtmpl": out_template,
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [hook],
        "postprocessors": [{
            "key": "FFmpegVideoConvertor",
            "preferedformat": "mp4",
        }]
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if not info:
            raise RuntimeError("yt-dlp không trích xuất được thông tin video.")

        title_holder["title"] = info.get("title", "video")

        requested_downloads = info.get("requested_downloads")
        if requested_downloads and len(requested_downloads) > 0:
            target_path = requested_downloads[0].get("filepath")
            if target_path and os.path.exists(target_path):
                title_holder["filepath"] = target_path

        if not title_holder["filepath"]:
            cand = ydl.prepare_filename(info)
            cand_mp4 = os.path.splitext(cand)[0] + ".mp4"
            if os.path.exists(cand_mp4):
                title_holder["filepath"] = cand_mp4
            elif os.path.exists(cand):
                title_holder["filepath"] = cand
            else:
                files = [os.path.join(output_dir, f) for f in os.listdir(output_dir) if f.endswith(".mp4")]
                if files:
                    files.sort(key=os.path.getmtime, reverse=True)
                    title_holder["filepath"] = files[0]

    final_path = title_holder["filepath"]
    if not final_path or not os.path.exists(final_path):
        raise RuntimeError("Không tìm thấy file video sau khi tải hoàn tất.")

    if progress_cb:
        progress_cb("Hoàn tất tải video!", 1.0)

    return final_path, title_holder["title"]


def download_clean_video(
    url_or_text: str,
    output_dir: Optional[str] = None,
    progress_cb: Optional[Callable[[str, float], None]] = None,
    prefer_no_watermark: bool = True
) -> Tuple[str, str]:
    """
    Tải video sạch (loại bỏ watermark) từ link Douyin, TikTok, YouTube, Facebook, Kuaishou...
    Tự động giải mã link rút gọn và chọn phương thức tối ưu nhất cho từng nền tảng.
    """
    raw_url = extract_url(url_or_text)
    if not raw_url:
        raise ValueError("Không tìm thấy đường link URL hợp lệ trong nội dung đã nhập!")

    if not output_dir:
        output_dir = _get_default_download_dir()
    os.makedirs(output_dir, exist_ok=True)

    # Giải mã link rút gọn (v.douyin.com, vt.tiktok.com, youtu.be...)
    if progress_cb:
        progress_cb("Đang phân tích và mở rộng liên kết video...", 0.03)
    url = resolve_redirects(raw_url)

    is_douyin = any(k in url.lower() for k in ["douyin.com", "iesdouyin.com"])
    is_tiktok = "tiktok.com" in url.lower()

    # Link trực tiếp file video (.mp4, .mov, .mkv...)
    parsed_path = urllib.parse.urlparse(url).path.lower()
    is_direct_video = any(parsed_path.endswith(ext) for ext in [".mp4", ".mov", ".mkv", ".webm", ".flv", ".ts"])
    if is_direct_video:
        filename = os.path.basename(parsed_path) or f"video_{int(time.time())}.mp4"
        if not filename.endswith(".mp4"):
            filename += ".mp4"
        out_file = os.path.join(output_dir, filename)
        if progress_cb:
            progress_cb(f"Đang tải trực tiếp file video: {filename}...", 0.1)
        _download_stream(url, out_file, progress_cb=progress_cb)
        if progress_cb:
            progress_cb("Hoàn tất tải video!", 1.0)
        return out_file, os.path.splitext(filename)[0]

    errors = []

    # 1. ĐỐI VỚI DOUYIN: Ưu tiên SnapDouyin Engine (chuyên bóc watermark Douyin HD sạch sẽ)
    if is_douyin and prefer_no_watermark:
        try:
            return _download_snapdouyin(url, output_dir, progress_cb)
        except Exception as e:
            errors.append(f"SnapDouyin: {e}")
            if progress_cb:
                progress_cb(f"SnapDouyin gặp sự cố ({e}), chuyển sang phương thức dự phòng...", 0.1)

    # 2. ĐỐI VỚI TIKTOK (hoặc Douyin dự phòng): Thử TikWM Engine
    if (is_tiktok or is_douyin) and prefer_no_watermark:
        try:
            return _download_tikwm(url, output_dir, progress_cb)
        except Exception as e:
            errors.append(f"TikWM: {e}")
            if progress_cb:
                progress_cb(f"TikWM gặp sự cố ({e}), chuyển sang yt-dlp...", 0.15)

    # 3. PHƯƠNG THỨC ĐA NĂNG TOÀN DIỆN: yt-dlp (YouTube, Facebook, Bilibili, TikTok, Douyin...)
    try:
        return _download_ytdlp(url, output_dir, progress_cb)
    except Exception as e:
        errors.append(f"yt-dlp: {e}")

    # Nếu tất cả các phương thức đều thất bại
    err_report = "\n".join(f"- {er}" for er in errors)
    raise RuntimeError(f"Tải video thất bại qua các phương thức:\n{err_report}")


def cmd_download(args):
    """Lệnh CLI: tải video từ link."""
    raw_url = getattr(args, "url", None)
    if not raw_url:
        print("❌ Lỗi: Bạn cần cung cấp đường link video cần tải.")
        return 1

    def progress_cb(msg, pct):
        bar_len = 25
        filled = int(bar_len * pct)
        bar = "█" * filled + "░" * (bar_len - filled)
        sys.stdout.write(f"\r[{bar}] {int(pct * 100):3d}% | {msg[:55]:<55}")
        sys.stdout.flush()

    out_arg = getattr(args, "output", None)
    out_dir = None
    target_file = None

    if out_arg:
        if os.path.isdir(out_arg):
            out_dir = out_arg
        else:
            out_dir = os.path.dirname(os.path.abspath(out_arg))
            target_file = out_arg

    no_wm = not getattr(args, "keep_watermark", False)
    print(f"→ Đang bắt đầu tải video từ link: {raw_url}")
    print(f"→ Chế độ loại bỏ watermark: {'BẬT (sạch logo)' if no_wm else 'TẮT (giữ logo)'}")

    try:
        saved_path, title = download_clean_video(
            raw_url,
            output_dir=out_dir,
            progress_cb=progress_cb,
            prefer_no_watermark=no_wm
        )
        print()  # xuống dòng mới sau progress bar

        if target_file and os.path.abspath(saved_path) != os.path.abspath(target_file):
            import shutil
            os.makedirs(os.path.dirname(os.path.abspath(target_file)), exist_ok=True)
            shutil.move(saved_path, target_file)
            saved_path = target_file

        print(f"\n✔ Đã tải video thành công!")
        print(f"  Tiêu đề: {title}")
        print(f"  Lưu tại: {saved_path}")
        return 0
    except Exception as e:
        print()
        print(f"\n❌ Lỗi khi tải video: {e}")
        return 1
