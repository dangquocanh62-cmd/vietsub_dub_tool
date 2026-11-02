"""
QUY TRÌNH PHỐI HỢP NHIỀU BƯỚC: CMD_ALL VÀ CMD_AUTO
"""

import argparse
import os
import shutil
import tempfile

from .transcribe import cmd_transcribe
from .translate import cmd_translate
from .dubbing import cmd_dub
from .burning import cmd_burn


def cmd_all(args):
    if getattr(args, "no_dub", False):
        print("→ Chế độ: Chỉ gắn phụ đề vào video gốc (không lồng tiếng AI, giữ 100% âm thanh gốc)")
        cmd_burn(args, input_video=args.video)
        return
    tmp_dir = tempfile.mkdtemp(prefix="all_")
    try:
        tmp_dubbed = os.path.join(tmp_dir, "dubbed.mp4")
        cmd_dub(args, output_video=tmp_dubbed)
        cmd_burn(args, input_video=tmp_dubbed)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def cmd_auto(args):
    # Tự động tải video nếu đầu vào là đường link trực tuyến (TikTok, Douyin, YouTube...)
    raw_video = str(getattr(args, "video", "")).strip()
    if raw_video.startswith(("http://", "https://")) or "://" in raw_video:
        from .downloader import extract_url, download_clean_video
        found_url = extract_url(raw_video)
        if found_url:
            print(f"→ Phát hiện liên kết video trực tuyến: {found_url}")
            print("→ Đang tải video chất lượng cao (tự động loại bỏ Watermark / Logo)...")
            target_out_dir = None
            if getattr(args, "output", None):
                target_out_dir = os.path.dirname(os.path.abspath(args.output))
            dl_file, dl_title = download_clean_video(found_url, output_dir=target_out_dir)
            print(f"✔ Đã tải video thành công: {dl_file}")
            print(f"  Tiêu đề: {dl_title}\n")
            args.video = dl_file

    tmp_dir = tempfile.mkdtemp(prefix="auto_")
    try:
        video_dir = os.path.dirname(os.path.abspath(args.video))
        out_target = getattr(args, "output", None) or getattr(args, "script_out", None) or "output.mp4"
        if not os.path.isabs(out_target):
            out_target = os.path.join(video_dir, out_target)
        out_dir = os.path.dirname(os.path.abspath(out_target))
        os.makedirs(out_dir, exist_ok=True)

        video_base = os.path.splitext(os.path.basename(args.video))[0]
        orig_srt = os.path.join(out_dir, f"{video_base}_original.srt")

        use_ocr = getattr(args, "use_ocr", False)
        if use_ocr:
            print("→ Nguồn: Phụ đề cứng trên khung hình video (RapidOCR)")
            from .ocr_extractor import extract_hardsub_from_video
            c_top = float(getattr(args, "crop_top", None) if getattr(args, "crop_top", None) is not None else getattr(args, "top", 0.70))
            c_bot = float(getattr(args, "crop_bottom", None) if getattr(args, "crop_bottom", None) is not None else getattr(args, "bottom", 0.98))
            c_left = float(getattr(args, "crop_left", None) if getattr(args, "crop_left", None) is not None else getattr(args, "left", 0.0))
            c_right = float(getattr(args, "crop_right", None) if getattr(args, "crop_right", None) is not None else getattr(args, "right", 1.0))
            sample_fps = float(getattr(args, "ocr_fps", None) if getattr(args, "ocr_fps", None) is not None else getattr(args, "sample_fps", 4.0))
            extract_hardsub_from_video(
                video_path=args.video,
                output_srt=orig_srt,
                crop_box=(c_top, c_bot, c_left, c_right),
                sample_fps=sample_fps,
            )
        else:
            print("→ Nguồn: giọng nói trong video (Whisper)")
            cmd_transcribe(argparse.Namespace(
                video=args.video, output=orig_srt, model=args.model,
                device=args.device, compute_type=args.compute_type,
                preset=getattr(args, "preset", None),
                min_silence_ms=getattr(args, "min_silence_ms", 500),
                beam_size=getattr(args, "beam_size", 5),
                word_timestamps=getattr(args, "word_timestamps", True),
                diarize=getattr(args, "diarize", False),
                hf_token=getattr(args, "hf_token", None),
                sub_delay_ms=getattr(args, "sub_delay_ms", 0),
                vad=getattr(args, "vad", False),
            ))

        vi_srt = args.script_out or os.path.join(out_dir, f"{video_base}_vietsub.srt")
        cmd_translate(argparse.Namespace(
            input=orig_srt, output=vi_srt, target="vi",
            translate_engine=getattr(args, "translate_engine", "gemini"),
            api_key=getattr(args, "api_key", None),
            groq_api_key=getattr(args, "groq_api_key", None),
            translate_model=getattr(args, "translate_model", None),
            batch_size=getattr(args, "batch_size", 30),
        ))

        if args.pause_for_edit:
            final_srt_path = args.script_out or "vietnamese_auto.srt"
            if vi_srt != final_srt_path:
                shutil.copy(vi_srt, final_srt_path)
            print(f"\n⏸  Đã tạo phụ đề tiếng Việt (máy dịch) tại: {final_srt_path}")
            print("   Mở file này, sửa lại câu chữ cho tự nhiên/hài hước theo ý bạn,")
            print("   rồi chạy lệnh sau để ra video hoàn chỉnh:")
            mask_flag = " --mask-original" if getattr(args, "mask_original", False) else ""
            print(f'   python dub_tool.py all "{args.video}" "{final_srt_path}" -o "{args.output}"{mask_flag}')
            return

        args.script = vi_srt
        if getattr(args, "no_dub", False):
            print("\n→ Chế độ: Chỉ gắn phụ đề vào video gốc (không lồng tiếng AI, giữ 100% âm thanh gốc)")
            cmd_burn(args, input_video=args.video)
        else:
            tmp_dubbed = os.path.join(tmp_dir, "dubbed.mp4")
            cmd_dub(args, output_video=tmp_dubbed)
            cmd_burn(args, input_video=tmp_dubbed)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
