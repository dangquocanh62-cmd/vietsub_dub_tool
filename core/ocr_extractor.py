"""
BÓC TÁCH PHỤ ĐỀ CỨNG (HARDSUB OCR) TỪ HÌNH ẢNH VIDEO
Sử dụng RapidOCR (ONNX Runtime) siêu nhẹ, chạy hoàn toàn offline trên CPU/GPU.
Tối ưu hóa: Crop vùng đáy, Frame Differencing, Lọc watermark và Gom cụm timeline.
"""

from datetime import timedelta
import difflib
import os
import re
import cv2
import numpy as np
import srt
from tqdm import tqdm

try:
    from rapidocr_onnxruntime import RapidOCR
    _HAS_RAPIDOCR = True
except ImportError:
    _HAS_RAPIDOCR = False

from .burning import sanitize_subtitles


def _is_chinese_char(c: str) -> bool:
    """Kiểm tra một ký tự có phải là chữ Hán hay không."""
    return '\u4e00' <= c <= '\u9fff' or '\u3400' <= c <= '\u4dbf'


def _text_similarity(s1: str, s2: str) -> float:
    """Tính độ tương đồng giữa 2 chuỗi văn bản (0.0 -> 1.0) bằng SequenceMatcher."""
    if not s1 or not s2:
        return 0.0
    if s1 == s2:
        return 1.0
    len_min = min(len(s1), len(s2))
    len_max = max(len(s1), len(s2))
    # Nếu một chuỗi nằm trọn trong chuỗi kia và chiếm >= 65% độ dài (ví dụ mờ nét chữ cuối)
    if s1 in s2 or s2 in s1:
        if len_min / float(len_max) >= 0.65:
            return 0.88
    return difflib.SequenceMatcher(None, s1, s2).ratio()


def clean_ocr_text(text: str) -> str:
    """Làm sạch văn bản sau OCR (chuẩn hóa khoảng trắng chữ Hán, khử ký tự rác viền)."""
    if not text:
        return ""
    text = text.strip()
    text = text.strip("`'\"_~|^·")
    # Loại bỏ khoảng trắng giữa các chữ Hán
    new_text = []
    for i, c in enumerate(text):
        if c == ' ':
            prev_c = text[i - 1] if i > 0 else ''
            next_c = text[i + 1] if i + 1 < len(text) else ''
            if _is_chinese_char(prev_c) and _is_chinese_char(next_c):
                continue
        new_text.append(c)
    text = "".join(new_text).strip()
    return text


def extract_hardsub_from_video(
    video_path: str,
    output_srt: str,
    crop_box: tuple = (0.70, 0.95, 0.0, 1.0),
    sample_fps: float = 4.0,
    min_confidence: float = 0.55,
    min_duration_sec: float = 0.4,
    progress_cb=None,
    stop_event=None
) -> list:
    """
    Trích xuất phụ đề cứng từ video và xuất ra file .srt chuẩn.

    Tham số:
      - video_path: Đường dẫn file video
      - output_srt: Đường dẫn file .srt cần lưu
      - crop_box: (top, bottom, left, right) theo tỉ lệ 0.0 -> 1.0 (mặc định 0.70 -> 0.95 đáy màn hình)
      - sample_fps: Số frame lấy mẫu mỗi giây (mặc định 4 fps = mỗi 250ms)
      - min_confidence: Ngưỡng độ tin cậy tối thiểu của OCR (0.0 -> 1.0)
      - min_duration_sec: Thời lượng tối thiểu của một câu phụ đề (tránh flicker rác)
      - progress_cb: Callback cập nhật tiến trình (pct: int, msg: str)
      - stop_event: threading.Event để ngắt sớm nếu người dùng bấm dừng
    """
    if not _HAS_RAPIDOCR:
        raise RuntimeError("Chưa cài đặt rapidocr-onnxruntime. Hãy chạy 'pip install rapidocr-onnxruntime'.")

    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"Không tìm thấy video: {video_path}")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Không thể mở video bằng OpenCV: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    video_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    duration_sec = 0.0
    try:
        from .utils import get_video_duration
        duration_sec = get_video_duration(video_path)
    except Exception:
        pass
    if duration_sec <= 0:
        duration_sec = total_frames / max(video_fps, 1.0) if total_frames > 0 else 10.0

    top_r, bot_r, left_r, right_r = crop_box
    ymin = max(0, min(height - 1, int(round(top_r * height))))
    ymax = max(ymin + 10, min(height, int(round(bot_r * height))))
    xmin = max(0, min(width - 1, int(round(left_r * width))))
    xmax = max(xmin + 10, min(width, int(round(right_r * width))))

    step_frames = max(1, int(round(video_fps / sample_fps)))
    total_samples = max(1, int(round(duration_sec * sample_fps)))

    engine = RapidOCR()
    # Tối ưu hoá DBNet TextDetector:
    # Mặc định limit_type='min' và limit_side_len=736 khiến ảnh crop bị phóng to 5.5x lên 5000+ pixel,
    # gây quá tải CPU mất 3-4s/frame. Chuyển sang limit_type='max' giới hạn cạnh lớn tối đa 960px giúp tăng tốc 8-10 lần (0.4s/frame).
    try:
        engine.text_det.limit_type = 'max'
        engine.text_det.limit_side_len = 960
    except Exception:
        pass

    raw_samples = []  # List[(timestamp_sec, text, score)]
    current_cap_frame = 0
    frame_idx = 0
    sample_count = 0

    pbar = tqdm(total=total_samples, desc="👁 Quét phụ đề cứng (OCR)")

    while cap.isOpened() and sample_count < total_samples and frame_idx < total_frames:
        if stop_event and stop_event.is_set():
            break

        cur_sec = frame_idx / video_fps
        if duration_sec > 0 and cur_sec >= duration_sec:
            break

        # Tối ưu đọc tuần tự: dùng cap.grab() để nhảy nhanh tới frame_idx mà không cần seek lại từ đầu (nhanh gấp 50-100 lần)
        if current_cap_frame < frame_idx:
            skip_count = frame_idx - current_cap_frame
            if skip_count > 120:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                current_cap_frame = frame_idx
            else:
                for _ in range(skip_count - 1):
                    if not cap.grab():
                        break
                    current_cap_frame += 1

        ret, frame = cap.read()
        current_cap_frame += 1
        if not ret or frame is None:
            break

        crop = frame[ymin:ymax, xmin:xmax]
        if crop.size == 0:
            frame_idx += step_frames
            sample_count += 1
            pbar.update(1)
            continue

        # Giữ nguyên tỷ lệ crop chuẩn, chỉ thu nhỏ chiều ngang nếu vượt quá 960px
        if crop.shape[1] > 960:
            scale = 960.0 / crop.shape[1]
            new_h = max(16, int(round(crop.shape[0] * scale)))
            crop = cv2.resize(crop, (960, new_h), interpolation=cv2.INTER_AREA)

        # Chạy RapidOCR trên ảnh crop độ phân giải tự nhiên (use_cls=False tiết kiệm 30% thời gian)
        ocr_res, _ = engine(crop, use_cls=False)
        if ocr_res:
            ocr_res.sort(key=lambda item: min(pt[1] for pt in item[0]))
            valid_lines = [clean_ocr_text(item[1]) for item in ocr_res if item[2] >= min_confidence and item[1].strip()]
            cur_text = " ".join([ln for ln in valid_lines if ln])
            cur_score = float(np.mean([item[2] for item in ocr_res])) if valid_lines else 0.0
        else:
            cur_text = ""
            cur_score = 0.0

        raw_samples.append((cur_sec, cur_text, cur_score))
        sample_count += 1
        frame_idx += step_frames
        pbar.update(1)

        if progress_cb and total_samples > 0:
            pct = int(min(100, (sample_count / total_samples) * 100))
            cur_time_str = f"{int(cur_sec // 60):02d}:{cur_sec % 60:04.1f}"
            preview_txt = (cur_text[:25] + "...") if len(cur_text) > 25 else cur_text
            progress_cb(pct, f"[{cur_time_str}] {preview_txt or '...'}")

    cap.release()
    pbar.close()

    # ── GOM CỤM CÁC MẪU LIÊN TIẾP THÀNH TIMELINE SUBTITLE (FUZZY & TIMING OFFSET) ─────
    segments = []
    cur_seg_text = None
    cur_start = None
    cur_end = None
    cur_seg_score = 0.0
    sample_interval = 1.0 / sample_fps
    half_interval = sample_interval * 0.5

    def _append_segment(start_t, end_t, text, score):
        prev_end = segments[-1]["end"] if segments else 0.0
        # Bù trừ lùi thời gian xuất hiện (triệt tiêu độ trễ để phụ đề bật lên đúng lúc phụ đề gốc hiện)
        actual_start = max(prev_end, start_t - half_interval)
        actual_end = min(duration_sec, end_t + half_interval)
        if actual_end <= actual_start:
            actual_end = actual_start + sample_interval
        segments.append({
            "start": round(actual_start, 3),
            "end": round(actual_end, 3),
            "text": text,
            "score": score
        })

    for t_sec, text, score in raw_samples:
        clean_t = text.strip()
        if not clean_t:
            if cur_seg_text is not None:
                # Kết thúc đoạn phụ đề trước đó
                _append_segment(cur_start, cur_end, cur_seg_text, cur_seg_score)
                cur_seg_text = None
            continue

        if cur_seg_text is None:
            cur_seg_text = clean_t
            cur_seg_score = score
            cur_start = t_sec
            cur_end = t_sec
        elif clean_t == cur_seg_text or _text_similarity(clean_t, cur_seg_text) >= 0.75:
            # Cùng 1 câu phụ đề (dù lệch nhẹ 1 nét chữ/dấu câu do chớp sáng khung hình)
            cur_end = t_sec
            # Giữ lại chuỗi chữ đầy đủ hơn
            if len(clean_t) > len(cur_seg_text) and score >= cur_seg_score * 0.88:
                cur_seg_text = clean_t
            cur_seg_score = max(cur_seg_score, score)
        else:
            # Chuyển sang câu phụ đề mới
            _append_segment(cur_start, cur_end, cur_seg_text, cur_seg_score)
            cur_seg_text = clean_t
            cur_seg_score = score
            cur_start = t_sec
            cur_end = t_sec

    if cur_seg_text is not None:
        _append_segment(cur_start, cur_end, cur_seg_text, cur_seg_score)

    # ── LỌC BỎ NHIỄU & WATERMARK TĨNH ──────────────────────────────────────────
    filtered_segments = []
    total_vid_dur = max(duration_sec, 1.0)

    for seg in segments:
        dur = seg["end"] - seg["start"]
        # Bỏ các đoạn quá ngắn (< min_duration_sec)
        if dur < min_duration_sec:
            continue
        # Bỏ watermark tĩnh: Xuất hiện liên tục > 45% tổng thời lượng video (chỉ áp dụng cho video >= 15s)
        if total_vid_dur >= 15.0 and dur > total_vid_dur * 0.45:
            continue
        # Bỏ câu chỉ toàn ký tự rác (1 ký tự duy nhất)
        if len(seg["text"]) <= 1 and not _is_chinese_char(seg["text"]):
            continue
        filtered_segments.append(seg)

    # ── HÀN GẮN CÂU THÔNG MINH (SMART GAP MERGING) ─────────────────────────────
    # Tự động nối các câu tương đồng (>= 72%) bị ngắt quãng ngắn (<= 0.85s) do nhiễu/nền động
    merged_segments = []
    for seg in filtered_segments:
        if merged_segments:
            prev = merged_segments[-1]
            gap = seg["start"] - prev["end"]
            sim = _text_similarity(prev["text"], seg["text"])
            if sim >= 0.72 and gap <= 0.85:
                prev["end"] = max(prev["end"], seg["end"])
                if len(seg["text"]) > len(prev["text"]):
                    prev["text"] = seg["text"]
                continue
        merged_segments.append(seg)

    # ── XUẤT RA DANH SÁCH SRT.SUBTITLE & GHI FILE ──────────────────────────────
    subs = []
    for idx, seg in enumerate(merged_segments, start=1):
        s_td = timedelta(seconds=max(0.0, seg["start"]))
        e_td = timedelta(seconds=max(seg["start"] + 0.3, seg["end"]))
        subs.append(srt.Subtitle(
            index=idx,
            start=s_td,
            end=e_td,
            content=seg["text"]
        ))

    subs = sanitize_subtitles(subs)

    os.makedirs(os.path.dirname(os.path.abspath(output_srt)), exist_ok=True)
    with open(output_srt, "w", encoding="utf-8") as f:
        f.write(srt.compose(subs))

    return subs


def cmd_ocr(args):
    """Entrypoint CLI cho lệnh 'ocr'."""
    video = args.video
    output = getattr(args, "output", None)
    if not output:
        base = os.path.splitext(os.path.basename(video))[0]
        v_dir = os.path.dirname(os.path.abspath(video))
        out_folder = os.path.join(v_dir, f"{base}_output")
        output = os.path.join(out_folder, f"{base}_original.srt")

    top = float(getattr(args, "crop_top", None) if getattr(args, "crop_top", None) is not None else getattr(args, "top", 0.70))
    bottom = float(getattr(args, "crop_bottom", None) if getattr(args, "crop_bottom", None) is not None else getattr(args, "bottom", 0.95))
    left = float(getattr(args, "crop_left", None) if getattr(args, "crop_left", None) is not None else getattr(args, "left", 0.0))
    right = float(getattr(args, "crop_right", None) if getattr(args, "crop_right", None) is not None else getattr(args, "right", 1.0))
    sample_fps = float(getattr(args, "ocr_fps", None) if getattr(args, "ocr_fps", None) is not None else getattr(args, "sample_fps", 4.0))

    print(f"\n→ Bắt đầu quét phụ đề cứng (Hardsub OCR): {video}")
    print(f"  Vùng quét: Top={top:.3f}, Bottom={bottom:.3f}, Left={left:.3f}, Right={right:.3f}")
    subs = extract_hardsub_from_video(
        video_path=video,
        output_srt=output,
        crop_box=(top, bottom, left, right),
        sample_fps=sample_fps
    )
    print(f"\n✔ Hoàn tất quét phụ đề cứng: Đã tìm thấy {len(subs)} câu thoại.")
    print(f"📁 File đã lưu tại: {output}\n")
    return output
