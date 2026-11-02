"""
MÁY CHỦ CHIA SẺ VIDEO NỘI BỘ (LAN) QUA MÃ QR
Cho phép điện thoại (iOS / Android) tải nhanh video từ máy tính qua mạng Wi-Fi nội bộ.
"""

import os
import socket
import threading
import mimetypes
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from PIL import Image

try:
    import qrcode
    HAS_QRCODE = True
except Exception:
    HAS_QRCODE = False

try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except Exception:
    HAS_CV2 = False


def get_local_ip() -> str:
    """Lấy địa chỉ IP mạng nội bộ (LAN) của máy tính."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Không cần kết nối internet thực sự, socket UDP chỉ định tuyến theo bảng routing
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def generate_qr_image(data: str, size: int = 260) -> Image.Image:
    """Tạo ảnh PIL chứa mã QR từ đường dẫn (URL)."""
    if HAS_QRCODE:
        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=10,
                border=2,
            )
            qr.add_data(data)
            qr.make(fit=True)
            pil_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
            return pil_img.resize((size, size), Image.Resampling.NEAREST)
        except Exception:
            pass

    if HAS_CV2:
        try:
            encoder = cv2.QRCodeEncoder.create()
            mat = encoder.encode(data)
            # Thêm viền trắng (quiet zone)
            border = 3
            mat_bordered = cv2.copyMakeBorder(
                mat, border, border, border, border, cv2.BORDER_CONSTANT, value=255
            )
            # Phóng to ảnh giữ nguyên độ sắc nét
            resized = cv2.resize(mat_bordered, (size, size), interpolation=cv2.INTER_NEAREST)
            return Image.fromarray(resized).convert("RGB")
        except Exception:
            pass

    # Fallback nếu không có cả 2: Tạo ảnh trống thông báo
    fallback = Image.new("RGB", (size, size), color=(255, 255, 255))
    return fallback


def _render_mobile_page(filename: str, file_size_bytes: int) -> str:
    """Tạo giao diện trang tải video thân thiện với điện thoại di động (Dark Theme)."""
    size_mb = file_size_bytes / (1024 * 1024)
    size_str = f"{size_mb:.1f} MB" if size_mb < 1024 else f"{size_mb / 1024:.2f} GB"

    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Tải Video - Vietsub Tool</title>
    <style>
        :root {{
            --bg-color: #0F172A;
            --card-bg: #1E293B;
            --primary: #10B981;
            --primary-hover: #059669;
            --text-main: #F8FAFC;
            --text-muted: #94A3B8;
            --border: #334155;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background-color: var(--bg-color);
            color: var(--text-main);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            padding: 16px;
        }}
        .card {{
            background-color: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 20px;
            padding: 24px;
            width: 100%;
            max-width: 460px;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.5);
            text-align: center;
        }}
        .badge {{
            display: inline-block;
            background-color: rgba(16, 185, 129, 0.15);
            color: #34D399;
            padding: 6px 14px;
            border-radius: 9999px;
            font-size: 13px;
            font-weight: 600;
            margin-bottom: 14px;
        }}
        h1 {{
            font-size: 18px;
            font-weight: 700;
            margin-bottom: 6px;
            word-break: break-word;
            line-height: 1.4;
        }}
        .file-info {{
            font-size: 13px;
            color: var(--text-muted);
            margin-bottom: 18px;
        }}
        .video-container {{
            width: 100%;
            border-radius: 12px;
            overflow: hidden;
            background-color: #000;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.3);
        }}
        video {{
            width: 100%;
            max-height: 320px;
            display: block;
        }}
        .btn-download {{
            display: block;
            width: 100%;
            background-color: var(--primary);
            color: #FFFFFF;
            text-decoration: none;
            font-size: 16px;
            font-weight: 700;
            padding: 15px;
            border-radius: 14px;
            box-shadow: 0 10px 15px -3px rgba(16, 185, 129, 0.4);
            transition: all 0.2s ease;
            margin-bottom: 16px;
        }}
        .btn-download:active {{
            transform: scale(0.98);
            background-color: var(--primary-hover);
        }}
        .tips {{
            background-color: rgba(255, 255, 255, 0.04);
            border-radius: 12px;
            padding: 12px 14px;
            text-align: left;
            font-size: 12px;
            color: var(--text-muted);
            line-height: 1.6;
        }}
        .tips strong {{
            color: #CBD5E1;
        }}
    </style>
</head>
<body>
    <div class="card">
        <div class="badge">🎬 Vietsub & Dub Tool</div>
        <h1>{filename}</h1>
        <div class="file-info">Dung lượng: <strong>{size_str}</strong> • Định dạng: MP4</div>
        
        <div class="video-container">
            <video controls playsinline preload="metadata">
                <source src="/stream" type="video/mp4">
                Trình duyệt của bạn không hỗ trợ phát trực tiếp video.
            </video>
        </div>

        <a href="/download" download="{filename}" class="btn-download">
            ⬇️ TẢI VIDEO VỀ ĐIỆN THOẠI
        </a>

        <div class="tips">
            💡 <strong>Mẹo lưu vào Thư viện ảnh:</strong><br>
            • <b>iPhone (Safari):</b> Bấm "Tải về" ➔ Mở mục Tải về ➔ Bấm nút Chia sẻ ➔ Chọn <b>"Lưu video"</b>.<br>
            • <b>Android (Chrome):</b> Bấm nút tải trên hoặc bấm icon 3 chấm ở góc video ➔ Chọn <b>"Tải xuống"</b>.
        </div>
    </div>
</body>
</html>
"""


class VideoShareHTTPHandler(BaseHTTPRequestHandler):
    """Xử lý yêu cầu HTTP với hỗ trợ HTTP 206 Partial Content (tua video và download cho Safari/Chrome)."""

    def log_message(self, format, *args):
        # Tắt in log ra console để tránh làm rối log của app
        pass

    def do_GET(self):
        video_path = getattr(self.server, "video_path", None)
        if not video_path or not os.path.isfile(video_path):
            self.send_error(404, "File video không tồn tại")
            return

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self._serve_html_page(video_path)
        elif path == "/stream" or path == "/download":
            as_attachment = (path == "/download")
            self._serve_video_file(video_path, as_attachment=as_attachment)
        else:
            self.send_error(404, "Không tìm thấy trang")

    def _serve_html_page(self, video_path: str):
        filename = os.path.basename(video_path)
        file_size = os.path.getsize(video_path)
        html_content = _render_mobile_page(filename, file_size).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html_content)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(html_content)

        # Cập nhật trạng thái
        cb = getattr(self.server, "on_activity_callback", None)
        if cb:
            cb("📱 Điện thoại đã kết nối trang tải!")

    def _serve_video_file(self, video_path: str, as_attachment: bool = False):
        try:
            file_size = os.path.getsize(video_path)
            range_header = self.headers.get("Range", None)
            mime_type = mimetypes.guess_type(video_path)[0] or "video/mp4"
            filename = os.path.basename(video_path)

            cb = getattr(self.server, "on_activity_callback", None)
            if cb:
                act = "📥 Đang tải video..." if as_attachment else "▶ Đang phát video..."
                cb(act)

            if range_header:
                # Xử lý HTTP Range (ví dụ: 'bytes=0-1024')
                range_match = range_header.strip().lower()
                if range_match.startswith("bytes="):
                    parts = range_match[6:].split("-")
                    start = int(parts[0]) if parts[0] else 0
                    end = int(parts[1]) if parts[1] else file_size - 1
                    if end >= file_size:
                        end = file_size - 1
                    content_length = (end - start) + 1

                    self.send_response(206)
                    self.send_header("Content-Type", mime_type)
                    self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                    self.send_header("Content-Length", str(content_length))
                    self.send_header("Accept-Ranges", "bytes")
                    if as_attachment:
                        quoted_fname = urllib.parse.quote(filename)
                        self.send_header("Content-Disposition", f'attachment; filename="{filename}"; filename*=UTF-8\'\'{quoted_fname}')
                    self.end_headers()

                    with open(video_path, "rb") as f:
                        f.seek(start)
                        remaining = content_length
                        chunk_size = 64 * 1024
                        while remaining > 0:
                            read_len = min(chunk_size, remaining)
                            data = f.read(read_len)
                            if not data:
                                break
                            self.wfile.write(data)
                            remaining -= len(data)
                    return

            # Phản hồi 200 thông thường
            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(file_size))
            self.send_header("Accept-Ranges", "bytes")
            if as_attachment:
                quoted_fname = urllib.parse.quote(filename)
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"; filename*=UTF-8\'\'{quoted_fname}')
            self.end_headers()

            with open(video_path, "rb") as f:
                chunk_size = 64 * 1024
                while True:
                    data = f.read(chunk_size)
                    if not data:
                        break
                    self.wfile.write(data)

        except (ConnectionResetError, BrokenPipeError):
            # Khách hàng ngắt kết nối (tua hoặc hủy tải)
            pass
        except Exception as e:
            try:
                self.send_error(500, f"Lỗi đọc file: {e}")
            except Exception:
                pass


class ShareServer:
    """Quản lý vòng đời của máy chủ HTTP chia sẻ video."""

    def __init__(self, video_path: str, port: int = 0, on_activity=None):
        self.video_path = video_path
        self.on_activity = on_activity
        self.ip = get_local_ip()
        self.server = None
        self.thread = None
        self.port = port
        self.url = ""

    def start(self) -> str:
        """Khởi động máy chủ trong thread nền và trả về đường dẫn URL."""
        # port = 0: hệ điều hành tự cấp 1 cổng trống an toàn, tránh xung đột
        self.server = HTTPServer(("0.0.0.0", self.port), VideoShareHTTPHandler)
        self.server.video_path = self.video_path
        self.server.on_activity_callback = self.on_activity
        actual_port = self.server.server_port
        self.port = actual_port
        self.url = f"http://{self.ip}:{actual_port}"

        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self.url

    def stop(self):
        """Tắt máy chủ và giải phóng socket."""
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception:
                pass
            self.server = None
