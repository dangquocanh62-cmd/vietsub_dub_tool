"""
GẮN PHỤ ĐỀ, ĐỊNH DẠNG ASS, VÀ CHE/LÀM MỜ VÙNG CHỮ GỐC
"""

import os
import subprocess
import tempfile
import srt
from tqdm import tqdm

from .utils import (
    run,
    run_ffmpeg_with_progress,
    get_video_duration,
    get_video_dimensions,
    _safe_blur_radius,
    _escape_ffmpeg_path,
    _to_ass_color,
    is_video_hdr,
)

_DETECTED_ENCODER = None


def _test_ffmpeg_encoder(codec_name, extra_args=None):
    """Kiểm tra nhanh xem encoder có hoạt động thực sự trên hệ thống không."""
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=0.1:size=64x64:rate=10",
        "-c:v", codec_name
    ]
    if extra_args:
        cmd.extend(extra_args)
    cmd.extend(["-f", "null", "-"])
    try:
        res = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3
        )
        return res.returncode == 0
    except Exception:
        return False


def get_video_encoder_flags(args=None):
    """Tự động lựa chọn bộ mã hóa video tối ưu (Ưu tiên GPU Intel QSV/NVENC/MediaFoundation, fallback CPU libx264 fast)."""
    global _DETECTED_ENCODER
    req = getattr(args, "video_encoder", "auto") or "auto"
    preset = getattr(args, "export_preset", "veryfast") or "veryfast"
    crf = int(getattr(args, "crf", 20) or 20)

    if req == "qsv":
        return ["-c:v", "h264_qsv", "-global_quality", str(crf + 3)], "Intel QuickSync (GPU h264_qsv)"
    elif req == "mf":
        return ["-c:v", "h264_mf", "-b:v", "12M"], "Media Foundation (GPU h264_mf)"
    elif req == "nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", str(crf)], "NVIDIA NVENC (GPU h264_nvenc)"
    elif req in ("cpu", "libx264"):
        return ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p"], f"CPU libx264 (preset: {preset})"

    # req == "auto"
    if _DETECTED_ENCODER is None:
        if _test_ffmpeg_encoder("h264_qsv", ["-global_quality", "23"]):
            _DETECTED_ENCODER = "qsv"
        elif _test_ffmpeg_encoder("h264_nvenc", ["-preset", "p4"]):
            _DETECTED_ENCODER = "nvenc"
        elif _test_ffmpeg_encoder("h264_mf", ["-b:v", "12M"]):
            _DETECTED_ENCODER = "mf"
        else:
            _DETECTED_ENCODER = "cpu"

    if _DETECTED_ENCODER == "qsv":
        return ["-c:v", "h264_qsv", "-global_quality", str(crf + 3)], "Intel QuickSync (GPU h264_qsv)"
    elif _DETECTED_ENCODER == "nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", str(crf)], "NVIDIA NVENC (GPU h264_nvenc)"
    elif _DETECTED_ENCODER == "mf":
        return ["-c:v", "h264_mf", "-b:v", "12M"], "Media Foundation (GPU h264_mf)"
    else:
        return ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p"], f"CPU libx264 (preset: {preset})"


def _run_burn_export(base_inputs_and_filters, out_path, args, duration):
    """Xuất video với encoder tối ưu và thanh tiến độ thời gian thực, tự động fallback an toàn nếu lỗi."""
    encoder_flags, encoder_name = get_video_encoder_flags(args)
    print(f"  ⚡ Bộ mã hóa video: {encoder_name}")
    cmd = ["ffmpeg", "-y"] + base_inputs_and_filters + ["-map", "0:a?"] + encoder_flags + ["-c:a", "copy", out_path]
    try:
        run_ffmpeg_with_progress(cmd, total_sec=duration, desc="Gắn phụ đề & xuất video")
    except Exception as e:
        if "libx264" not in encoder_flags:
            print(f"\n  ⚠ Bộ mã hóa GPU gặp sự cố, tự động kích hoạt mã hóa CPU dự phòng (libx264 veryfast)...")
            preset = getattr(args, "export_preset", "veryfast") or "veryfast"
            crf = int(getattr(args, "crf", 20) or 20)
            fallback_cmd = (
                ["ffmpeg", "-y"] + base_inputs_and_filters +
                ["-map", "0:a?", "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p", "-c:a", "copy", out_path]
            )
            run_ffmpeg_with_progress(fallback_cmd, total_sec=duration, desc="Gắn phụ đề (CPU dự phòng)")
        else:
            raise e



def cmd_template(args):
    duration = get_video_duration(args.video)
    seg = args.seconds
    n_blocks = int(duration // seg) + 1
    subs = []
    t = 0.0
    idx = 1
    with tqdm(total=n_blocks, desc="Tạo khung phụ đề") as bar:
        while t < duration:
            start = t
            end = min(t + seg, duration)
            subs.append(srt.Subtitle(
                index=idx,
                start=srt.timedelta(seconds=start),
                end=srt.timedelta(seconds=end),
                content="(điền lời thoại tiếng Việt ở đây)"
            ))
            t += seg
            idx += 1
            bar.update(1)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(srt.compose(subs))
    print(f"✔ Đã tạo khung phụ đề: {args.output}  ({idx - 1} dòng, video dài {duration:.1f}s)")
    print("  Mở file này và điền lời thoại tiếng Việt vào, chỉnh lại timestamp nếu cần.")
    print("  (Mẹo: dùng lệnh 'transcribe' bên dưới để tool tự nghe và điền sẵn cho bạn)")


def sanitize_subtitles(subs, max_duration_sec=9.0, min_gap_ms=30):
    """Tự động khử hiện tượng phụ đề đè lên nhau và cắt các câu kéo dài bất thường do lỗi timestamp."""
    from datetime import timedelta
    if not subs:
        return subs

    # 1. Luôn sắp xếp đơn điệu theo thời gian bắt đầu (chống nhảy ngược thời gian)
    subs = sorted(subs, key=lambda s: s.start)

    # 2. Sửa triệt để mọi câu có mốc kết thúc <= mốc bắt đầu
    for s in subs:
        if s.end <= s.start:
            s.end = s.start + timedelta(milliseconds=800)

    max_dur = timedelta(seconds=max_duration_sec)
    gap = timedelta(milliseconds=min_gap_ms)

    for i in range(len(subs) - 1):
        cur_sub = subs[i]
        next_sub = subs[i+1]

        # 3. Khử trùng lặp/chồng lấn thời gian với câu kế tiếp (nguyên nhân gây đè phụ đề)
        if cur_sub.end > next_sub.start:
            cur_sub.end = max(cur_sub.start + timedelta(milliseconds=200), next_sub.start - gap)

        # 4. Khử các câu kéo dài bất thường (> 9s)
        if cur_sub.end - cur_sub.start > max_dur:
            safe_end = next_sub.start - gap if next_sub.start > cur_sub.start else next_sub.start
            cur_sub.end = min(cur_sub.start + max_dur, safe_end)

    if subs:
        last = subs[-1]
        if last.end - last.start > max_dur:
            last.end = last.start + max_dur

    # Đánh lại chỉ mục 1..N tuần tự
    for idx, s in enumerate(subs, start=1):
        s.index = idx

    return subs


def _srt_to_positioned_ass(srt_path: str, ass_path: str, style_line: str,
                           pos_x: float, pos_y: float,
                           video_w: int, video_h: int):
    """Chuyển file .srt sang .ass với toạ độ phụ đề tự do."""
    with open(srt_path, encoding="utf-8") as f:
        subs = list(srt.parse(f.read()))

    subs = sanitize_subtitles(subs)

    # Chuẩn hoá độ phân giải tham chiếu ASS về chuẩn PlayResY = 288 (chuẩn mặc định của FFmpeg/libass khi đọc .srt)
    # Giúp cỡ chữ (FontSize) và viền chữ (Outline) hiển thị to rõ, đúng chuẩn trên mọi độ phân giải video (1080p, 2K, 4K)
    ref_res_y = 288
    ref_res_x = max(1, int(round(ref_res_y * (video_w / max(1, video_h)))))

    px = int(round(pos_x * ref_res_x))
    py = int(round(pos_y * ref_res_y))

    def _td_to_ass(td) -> str:
        total = int(td.total_seconds())
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        cs = int(td.microseconds / 10000)
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    lines = [
        "[Script Info]", "ScriptType: v4.00+",
        f"PlayResX: {ref_res_x}", f"PlayResY: {ref_res_y}", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: {style_line}", "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for sub in subs:
        text = sub.content.replace("\n", "\\N")
        start = _td_to_ass(sub.start)
        end = _td_to_ass(sub.end)
        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{{\\pos({px},{py})}}{text}")

    with open(ass_path, "w", encoding="utf-8-sig") as f:
        f.write("\n".join(lines) + "\n")


def _burn_mask_preview(args, video_in: str, out_path: str) -> str:
    """Xuất nhanh 1 ảnh JPG xem trước vùng che/mờ."""
    top    = float(getattr(args, "mask_top", 0.75))
    bottom = float(getattr(args, "mask_bottom", 0.97))
    t      = float(getattr(args, "preview_time", None) or 3.0)
    mask_style = getattr(args, "mask_style", "box")
    color  = getattr(args, "mask_color", "black")
    blur_strength = _safe_blur_radius(
        video_in, top, bottom, int(getattr(args, "mask_blur", 25))
    )

    region_h = f"ih*({bottom}-{top})"
    region_y = f"ih*{top}"
    overlay_y = f"main_h*{top}"
    guide = (
        f"drawbox=x=0:y=ih*{top}:w=iw:h=2:color=red@0.9:t=fill,"
        f"drawbox=x=0:y=ih*{bottom}:w=iw:h=2:color=red@0.9:t=fill"
    )

    if mask_style == "blur":
        filter_complex = ";".join([
            f"[0:v]split=2[vbase][vforblur]",
            f"[vforblur]crop=w=iw:h={region_h}:x=0:y={region_y},boxblur={blur_strength}:2[vblurred]",
            f"[vbase][vblurred]overlay=x=0:y={overlay_y}[vmasked]",
            f"[vmasked]{guide}[vout]",
        ])
        run(["ffmpeg", "-y", "-ss", str(t), "-i", video_in,
             "-filter_complex", filter_complex, "-map", "[vout]",
             "-frames:v", "1", out_path])
    else:
        vf = f"drawbox=x=0:y=ih*{top}:w=iw:h=ih*({bottom}-{top}):color={color}:t=fill," + guide
        run(["ffmpeg", "-y", "-ss", str(t), "-i", video_in,
             "-vf", vf, "-frames:v", "1", out_path])

    print(f"✔ Đã xuất ảnh xem trước tại giây {t:.1f}: {out_path}")
    print(f"  Vạch ĐỎ = ranh giới --mask-top ({top}) / --mask-bottom ({bottom}).")
    print("  Chưa ưng ý (che thiếu/thừa) thì chỉnh lại 2 số này rồi chạy lại đúng lệnh preview,")
    print("  không cần đợi render cả video mỗi lần thử.")
    return out_path


def cmd_burn(args, input_video=None):
    video_in = input_video or args.video
    out_path = args.output
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    is_preview = getattr(args, "preview", False) or getattr(args, "preview_only", False)
    if is_preview and getattr(args, "script", "-") == "-":
        return _burn_mask_preview(args, video_in, out_path)
    preview_t = float(getattr(args, "preview_time", None) or 3.0)

    duration = None
    if not is_preview:
        try:
            duration = get_video_duration(video_in)
        except Exception:
            duration = None
        try:
            vw, vh = get_video_dimensions(video_in)
            if vw > 1920 or vh > 1920:
                print(f"  ℹ Video độ phân giải cao: {vw}x{vh} (4K UHD) — Tự động kích hoạt luồng xuất GPU tối ưu.")
        except Exception:
            pass

    alignment_map = {"bottom": 2, "middle": 5, "top": 8}
    alignment = alignment_map.get(getattr(args, "position", "bottom"), 2)
    font_name = getattr(args, "font_name", "Arial")
    font_size = getattr(args, "font_size", 16)
    primary_color = _to_ass_color(getattr(args, "font_color", "white"))
    outline_color = _to_ass_color(getattr(args, "outline_color", "black"))
    outline_width = getattr(args, "outline_width", 2)
    shadow = getattr(args, "shadow", 0)
    bold = -1 if getattr(args, "bold", False) else 0
    margin_v = getattr(args, "margin_v", 40)
    box = getattr(args, "box", False)

    if box:
        box_color = _to_ass_color(getattr(args, "box_color", "white"))
        style = (
            f"FontName={font_name},FontSize={font_size},PrimaryColour={primary_color},"
            f"OutlineColour={box_color},BorderStyle=3,Outline={outline_width},Shadow={shadow},"
            f"Bold={bold},Alignment={alignment},MarginV={margin_v}"
        )
    else:
        style = (
            f"FontName={font_name},FontSize={font_size},PrimaryColour={primary_color},"
            f"OutlineColour={outline_color},BorderStyle=1,Outline={outline_width},Shadow={shadow},"
            f"Bold={bold},Alignment={alignment},MarginV={margin_v}"
        )
    sanitized_script_path = args.script
    try:
        with open(args.script, encoding="utf-8") as f:
            raw_subs = list(srt.parse(f.read()))
        clean_subs = sanitize_subtitles(raw_subs)
        has_timing_fix = any(s_old.end != s_new.end for s_old, s_new in zip(raw_subs, clean_subs))
        if has_timing_fix:
            fd_clean, clean_path = tempfile.mkstemp(suffix="_cleaned.srt")
            os.close(fd_clean)
            with open(clean_path, "w", encoding="utf-8") as f:
                f.write(srt.compose(clean_subs))
            sanitized_script_path = clean_path
            print("  ✔ Đã tự động điều chỉnh timestamp để chống đè phụ đề lên nhau.")
    except Exception:
        pass
    srt_escaped = _escape_ffmpeg_path(sanitized_script_path)

    pos_x = getattr(args, "pos_x", None)
    pos_y = getattr(args, "pos_y", None)

    subtitles_filter_ass = None
    if pos_x is not None and pos_y is not None:
        video_w, video_h = get_video_dimensions(video_in)
        back_colour = _to_ass_color(getattr(args, "box_color", "white")) if box else "&H00000000"
        outline_colour_field = box_color if box else outline_color
        # Khi dùng \pos(x,y) cần alignment=5 (middle-center) để tọa độ
        # tương ứng với tâm chữ, tránh bị lệch lên do neo ở đáy (alignment=2)
        free_pos_alignment = 5
        style_line = (
            f"Default,{font_name},{font_size},{primary_color},&H00000000,"
            f"{outline_colour_field},{back_colour},{bold},0,0,0,100,100,0,0,"
            f"{3 if box else 1},{outline_width},{shadow},{free_pos_alignment},0,0,0,1"
        )
        fd, ass_path = tempfile.mkstemp(suffix="_positioned.ass")
        os.close(fd)
        _srt_to_positioned_ass(args.script, ass_path, style_line, pos_x, pos_y, video_w, video_h)
        ass_escaped = _escape_ffmpeg_path(ass_path)
        subtitles_filter_ass = f"subtitles=filename='{ass_escaped}'"
        print(f"  → Đặt phụ đề tại toạ độ tuỳ chỉnh: x={pos_x*100:.0f}%, y={pos_y*100:.0f}% (tính từ góc trên-trái)")

    subtitles_filter = subtitles_filter_ass or f"subtitles=filename='{srt_escaped}':force_style='{style}'"

    extra_blur_regions = []
    for spec in getattr(args, "extra_blur", []):
        parts = spec.split(",")
        if len(parts) in (3, 5):
            try:
                t_val  = float(parts[0])
                b_val  = float(parts[1])
                s_val  = int(parts[2])
                l_val  = float(parts[3]) if len(parts) == 5 else 0.0
                r_val  = float(parts[4]) if len(parts) == 5 else 1.0
                extra_blur_regions.append((t_val, b_val, s_val, l_val, r_val))
            except ValueError:
                print(f"  ⚠ Bỏ qua --extra-blur '{spec}' (định dạng: top,bottom,strength hoặc top,bottom,strength,left,right)")
        else:
            print(f"  ⚠ Bỏ qua --extra-blur '{spec}' (cần 3 hoặc 5 phần: top,bottom,strength[,left,right])")

    mask_on = getattr(args, "mask_original", False)
    mask_style = getattr(args, "mask_style", "box")

    def _build_blur_filter_complex(regions, initial_label, subtitle_filter_str):
        parts = []
        cur = initial_label
        for idx, region in enumerate(regions):
            if len(region) == 5:
                top_r, bot_r, str_r, left_r, right_r = region
            else:
                top_r, bot_r, str_r = region[:3]; left_r, right_r = 0.0, 1.0
            safe_str = _safe_blur_radius(video_in, top_r, bot_r, str_r, left_r, right_r)
            rh = f"ih*({bot_r}-{top_r})"
            rw = f"iw*({right_r}-{left_r})"
            rx = f"iw*{left_r}"
            ry = f"ih*{top_r}"
            oy = f"main_h*{top_r}"
            ox = f"main_w*{left_r}"
            base_lbl  = f"[eb_base{idx}]"
            blur_in   = f"[eb_in{idx}]"
            blurred   = f"[eb_blur{idx}]"
            out_lbl   = f"[eb_out{idx}]"
            parts.append(f"{cur}split=2{base_lbl}{blur_in}")
            parts.append(f"{blur_in}crop=w={rw}:h={rh}:x={rx}:y={ry},boxblur={safe_str}:2{blurred}")
            parts.append(f"{base_lbl}{blurred}overlay=x={ox}:y={oy}{out_lbl}")
            cur = out_lbl
        parts.append(f"{cur}{subtitle_filter_str}[vout]")
        return ";".join(parts)

    if mask_on and mask_style == "blur":
        top = args.mask_top
        bottom = args.mask_bottom
        strength = _safe_blur_radius(video_in, top, bottom, getattr(args, "mask_blur", 25))
        rh = f"ih*({bottom}-{top})"
        ry = f"ih*{top}"
        oy = f"main_h*{top}"

        if extra_blur_regions:
            all_regions = [(top, bottom, getattr(args, "mask_blur", 25), 0.0, 1.0)] + extra_blur_regions
            fc = _build_blur_filter_complex(all_regions, "[0:v]", subtitles_filter)
        else:
            fc_parts = [
                f"[0:v]split=2[vbase][vforblur]",
                f"[vforblur]crop=w=iw:h={rh}:x=0:y={ry},boxblur={strength}:2[vblurred]",
                f"[vbase][vblurred]overlay=x=0:y={oy}[vmasked]",
                f"[vmasked]{subtitles_filter}[vout]",
            ]
            fc = ";".join(fc_parts)
        base_inputs = ["-i", video_in, "-filter_complex", fc, "-map", "[vout]"]
        if is_preview:
            cmd = ["ffmpeg", "-y", "-ss", str(preview_t)] + base_inputs + ["-frames:v", "1", out_path]
            run(cmd)
            print(f"✔ Đã xuất ảnh xem trước phụ đề tại giây {preview_t:.1f}: {out_path}")
        else:
            _run_burn_export(base_inputs, out_path, args, duration)
            print(f"✔ Đã gắn phụ đề (làm mờ phụ đề gốc{f' + {len(extra_blur_regions)} vùng tuỳ chỉnh' if extra_blur_regions else ''}): {out_path}")
        return out_path

    if extra_blur_regions:
        vf_prefix_parts = []
        if mask_on:
            m_top = args.mask_top; m_bot = args.mask_bottom; m_color = args.mask_color
            vf_prefix_parts.append(
                f"drawbox=x=0:y=ih*{m_top}:w=iw:h=ih*({m_bot}-{m_top}):color={m_color}:t=fill"
            )
        if vf_prefix_parts:
            lead = f"[0:v]{','.join(vf_prefix_parts)}[after_box]"
            fc = lead + ";" + _build_blur_filter_complex(extra_blur_regions, "[after_box]", subtitles_filter)
        else:
            fc = _build_blur_filter_complex(extra_blur_regions, "[0:v]", subtitles_filter)
        base_inputs = ["-i", video_in, "-filter_complex", fc, "-map", "[vout]"]
        if is_preview:
            cmd = ["ffmpeg", "-y", "-ss", str(preview_t)] + base_inputs + ["-frames:v", "1", out_path]
            run(cmd)
            print(f"✔ Đã xuất ảnh xem trước phụ đề tại giây {preview_t:.1f}: {out_path}")
        else:
            _run_burn_export(base_inputs, out_path, args, duration)
            print(f"✔ Đã gắn phụ đề ({len(extra_blur_regions)} vùng làm mờ tuỳ chỉnh): {out_path}")
        return out_path

    vf_parts = []
    if mask_on:
        top = args.mask_top
        bottom = args.mask_bottom
        color = args.mask_color
        vf_parts.append(
            f"drawbox=x=0:y=ih*{top}:w=iw:h=ih*({bottom}-{top}):color={color}:t=fill"
        )
    vf_parts.append(subtitles_filter)
    base_inputs = ["-i", video_in, "-vf", ",".join(vf_parts)]
    if is_preview:
        cmd = ["ffmpeg", "-y", "-ss", str(preview_t)] + base_inputs + ["-frames:v", "1", out_path]
        run(cmd)
        print(f"✔ Đã xuất ảnh xem trước phụ đề tại giây {preview_t:.1f}: {out_path}")
    else:
        _run_burn_export(base_inputs, out_path, args, duration)
        print(f"✔ Đã gắn phụ đề: {out_path}")
    return out_path
