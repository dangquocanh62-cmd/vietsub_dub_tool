"""
ĐỊNH NGHĨA COMMAND LINE INTERFACE (CLI) CHO DUB TOOL
"""

import argparse

from .burning import cmd_template, cmd_burn
from .dubbing import cmd_dub
from .pipeline import cmd_all, cmd_auto
from .transcribe import cmd_transcribe
from .translate import cmd_translate, cmd_check_quota
from .tts import cmd_voices
from .ocr_extractor import cmd_ocr
from .downloader import cmd_download


def build_parser():
    p = argparse.ArgumentParser(description="Tool Vietsub + Lồng tiếng AI")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_dl = sub.add_parser("download", aliases=["dl"], help="Tải video từ link (TikTok, Douyin, YouTube, Facebook...) không logo/watermark")
    p_dl.add_argument("url", help="Link video hoặc đoạn text chia sẻ chứa link")
    p_dl.add_argument("-o", "--output", default=None, help="Đường dẫn file hoặc thư mục lưu video")
    p_dl.add_argument("--with-watermark", action="store_true", dest="keep_watermark",
                      help="Không loại bỏ watermark (giữ nguyên gốc)")
    p_dl.set_defaults(func=cmd_download)

    p_tpl = sub.add_parser("template", help="Tạo khung phụ đề rỗng từ video")
    p_tpl.add_argument("video")
    p_tpl.add_argument("-o", "--output", default="script.srt")
    p_tpl.add_argument("--seconds", type=float, default=3.0, help="Độ dài mỗi khối phụ đề (giây)")
    p_tpl.set_defaults(func=cmd_template)

    def add_tts_options(sp):
        """Các tuỳ chọn liên quan tới TTS/mix, dùng chung cho dub / all / auto."""
        sp.add_argument("--tts-engine", choices=["edge", "piper", "capcut"], default="edge", dest="tts_engine",
                         help="edge (mặc định) = Edge-TTS của Microsoft, cần mạng, chất lượng cao nhất. "
                              "piper = Piper TTS chạy OFFLINE (chỉ cần mạng 1 lần để tải model ~vài chục MB), "
                              "nhanh hơn nhiều vì không gọi mạng mỗi câu, nhưng ít lựa chọn giọng hơn. "
                              "capcut = CapCut TTS qua HuggingFace Space (tony2k/ai-voice-studio), "
                              "nhiều giọng tiếng Việt phong phú (bản tin, review phim, idol...), "
                              "cần internet, không cần cài thêm thư viện. "
                              "Xem giọng: python dub_tool.py voices")
        sp.add_argument("--piper-voices-dir", dest="piper_voices_dir", default=None,
                         help="[Chỉ dùng khi --tts-engine piper] Thư mục lưu model giọng Piper đã tải "
                              "(mặc định: ~/.cache/piper_voices). Model tải 1 lần, dùng lại mãi về sau.")
        sp.add_argument("--capcut-rate", dest="capcut_rate", type=float, default=1.0,
                         help="[Chỉ dùng khi --tts-engine capcut] Tốc độ đọc CapCut TTS "
                              "(1.0 = normal, 1.3 = nhanh hơn, 0.8 = chậm hơn). Mặc định: 1.0")
        sp.add_argument("--voice", default="nu-hoaimy",
                         help="Với --tts-engine edge (mặc định): nu-hoaimy | nam-namminh | mã giọng edge-tts bất kỳ. "
                              "Với --tts-engine piper: vi-vais1000 (khuyên dùng) | vi-25hours | vi-vivos | "
                              "tên giọng Piper đầy đủ bất kỳ (VD: vi_VN-vais1000-medium). "
                              "Với --tts-engine capcut: co-gai (mặc định) | thanh-nien | nu-pho-thong | "
                              "nho-ngot | mai | alex | ban-mai | ban-tin | gai-moi-lon | nam-tram | robot | "
                              "hoặc voice_type CapCut đầy đủ bất kỳ. Chạy 'voices' để xem đủ danh sách.")
        sp.add_argument("--keep-original", choices=["mute", "mix"], default="mix",
                         help="[Cũ, vẫn dùng được] mute = thay hẳn audio gốc, mix = giữ nền gốc nhỏ. "
                              "Khuyên dùng --mix-preset hoặc --bg-volume/--dub-volume thay thế, linh hoạt hơn.")
        sp.add_argument("--mix-preset", choices=["dubbing", "voiceover"], default=None,
                         help="Bộ trộn âm dựng sẵn, ghi đè --keep-original/--bg-volume/--dub-volume: "
                              "dubbing = audio gốc 0%%, giọng đọc 100%% (lồng tiếng hoàn toàn); "
                              "voiceover = audio gốc 25%%, giọng đọc 100%% (thuyết minh, giữ tiếng nền)")
        sp.add_argument("--bg-volume", type=float, default=0.15, dest="bg_volume",
                         help="Âm lượng audio gốc (0.0-1.0), mặc định 0.15. Bỏ qua nếu dùng --mix-preset.")
        sp.add_argument("--dub-volume", type=float, default=1.0, dest="dub_volume",
                         help="Âm lượng giọng lồng tiếng (0.0-1.0 mặc định 1.0. Bỏ qua nếu dùng --mix-preset.")
        sp.add_argument("--no-fit", action="store_true", help="Không tự tăng tốc giọng đọc cho vừa khung thời gian")
        sp.add_argument("--max-speed", type=float, default=1.25, dest="max_speed",
                         help="Giới hạn tốc độ tăng tối đa khi giọng đọc dài hơn khung thời gian phụ đề "
                              "(mặc định 1.25x, an toàn, không làm giọng méo). Vượt giới hạn này thì tool "
                              "giữ nguyên trọn câu (không cắt cuối câu) và chỉ cảnh báo, không ép tăng thêm.")
        sp.add_argument("--no-trim-silence", action="store_true", dest="no_trim_silence",
                         help="Không tự cắt khoảng lặng thừa đầu/cuối mỗi câu TTS trước khi canh khớp thời gian "
                              "(mặc định CÓ cắt — thường giúp giảm nhu cầu tăng tốc).")
        sp.add_argument("--no-cache", action="store_true",
                         help="Không dùng cache, luôn tạo lại giọng đọc từ đầu cho mọi câu")
        sp.add_argument("--delay", type=float, default=0.3,
                         help="Số giây nghỉ giữa mỗi câu khi gọi edge-tts, tăng lên nếu hay bị lỗi rate-limit (mặc định 0.3)")
        sp.add_argument("--max-tts-workers", type=int, default=4, dest="max_tts_workers",
                         help="Số lượng worker/thread tối đa để tải/sinh TTS đồng thời (mặc định 4)")
        sp.add_argument("--speaker-voices", dest="speaker_voices", default=None,
                         help="Chỉ định giọng TTS riêng cho từng người nói, định dạng: "
                              "'Người 1:nam-namminh,Người 3:nam-namminh'. "
                              "Ghi đè gợi ý mặc định từ role bucketing.")
        sp.add_argument("--merge-speakers", dest="merge_speakers", default=None,
                         help="Gộp người nói ở bước lồng tiếng, định dạng: "
                              "'Người 3:Người 1,Người 5:Người 2' (coi Người 3 như Người 1 "
                              "để dùng chung giọng, không sửa dữ liệu diarization gốc).")
        sp.add_argument("--single-voice", action="store_true", dest="single_voice",
                         help="Chỉ dùng 1 giọng đọc duy nhất cho toàn bộ video "
                              "(bỏ qua phân chia nhiều giọng theo vai/người nói).")

    def add_common_dub_args(sp):
        sp.add_argument("video")
        sp.add_argument("script", help="File .srt chứa lời thoại tiếng Việt")
        sp.add_argument("-o", "--output", required=True)
        add_tts_options(sp)

    def add_style_args(sp):
        """Tuỳ chỉnh font chữ / cỡ chữ / màu sắc / vị trí phụ đề, dùng chung cho burn / all / auto."""
        sp.add_argument("--font-name", default="Arial", dest="font_name",
                         help="Tên font chữ (phải có sẵn/cài trên máy đang chạy tool, VD: Arial, "
                              "Roboto, Be Vietnam Pro, Times New Roman...). Mặc định: Arial")
        sp.add_argument("--font-size", type=int, default=16, dest="font_size",
                         help="Cỡ chữ (mặc định 16, tăng lên nếu muốn chữ to hơn)")
        sp.add_argument("--font-color", default="white", dest="font_color",
                         help="Màu chữ: tên có sẵn (white/yellow/red/green/blue/cyan/magenta/orange/"
                              "pink/purple/gray/gold) hoặc mã hex (#RRGGBB, VD: #FFCC00)")
        sp.add_argument("--outline-color", default="black", dest="outline_color",
                         help="Màu viền chữ, cùng định dạng với --font-color")
        sp.add_argument("--outline-width", type=float, default=2, dest="outline_width",
                         help="Độ dày viền chữ (mặc định 2, 0 = không viền)")
        sp.add_argument("--shadow", type=float, default=0,
                         help="Độ đổ bóng chữ (mặc định 0 = không bóng)")
        sp.add_argument("--bold", action="store_true", help="Chữ đậm")
        sp.add_argument("--position", choices=["top", "middle", "bottom"], default="bottom",
                         help="Vị trí phụ đề trên khung hình (mặc định: bottom - phía dưới, giống video mẫu)")
        sp.add_argument("--margin-v", type=int, default=40, dest="margin_v",
                         help="Khoảng cách lề trên/dưới tính bằng pixel (mặc định 40)")
        sp.add_argument("--box", action="store_true",
                         help="Kiểu 'hộp nền đặc' thay vì chữ viền — giống caption TikTok "
                              "(nền trắng/màu, chữ đậm bên trong). Lưu ý: hộp sẽ là hình chữ "
                              "nhật vuông góc, KHÔNG bo tròn góc được như một số app TikTok/CapCut.")
        sp.add_argument("--box-color", default="white", dest="box_color",
                         help="Màu nền hộp khi dùng --box (cùng định dạng với --font-color)")
        sp.add_argument("--pos-x", type=float, default=None, dest="pos_x",
                         help="Đặt phụ đề tại toạ độ X tuỳ ý, theo tỉ lệ %% chiều RỘNG video "
                              "(0.0 = mép trái, 0.5 = giữa, 1.0 = mép phải). Phải đi kèm --pos-y. "
                              "Khi dùng, ghi đè hoàn toàn --position/--margin-v (định vị tự do, "
                              "không giới hạn 3 vùng top/middle/bottom).")
        sp.add_argument("--pos-y", type=float, default=None, dest="pos_y",
                         help="Đặt phụ đề tại toạ độ Y tuỳ ý, theo tỉ lệ %% chiều CAO video "
                              "(0.0 = mép trên, 0.5 = giữa, 1.0 = mép dưới). Phải đi kèm --pos-x.")

    def add_mask_args(sp):
        """Tuỳ chọn che/làm mờ vùng phụ đề GỐC đã khắc cứng sẵn trong video, dùng chung cho burn / all / auto."""
        sp.add_argument("--mask-original", action="store_true",
                         help="Che/làm mờ vùng phụ đề GỐC đã khắc cứng sẵn trong video, "
                              "trước khi khắc phụ đề tiếng Việt mới đè lên (tránh chồng 2 lớp chữ)")
        sp.add_argument("--mask-style", choices=["box", "blur"], default="box",
                         help="Kiểu che: box (mặc định) = khối màu đặc, che HOÀN TOÀN chữ gốc; "
                              "blur = làm mờ vùng đó thay vì tô màu đặc, nhìn tự nhiên hơn với nền "
                              "phức tạp nhưng chữ gốc có thể còn lờ mờ nhận ra")
        sp.add_argument("--mask-top", type=float, default=0.75,
                         help="Vị trí bắt đầu vùng che/mờ, tính theo tỉ lệ chiều cao video (0-1)")
        sp.add_argument("--mask-bottom", type=float, default=0.97,
                         help="Vị trí kết thúc vùng che/mờ (0-1)")
        sp.add_argument("--mask-color", default="black@1.0",
                         help="[Chỉ dùng khi --mask-style box] Màu khối che, dạng ffmpeg "
                              "(VD: black@1.0 = che đặc hoàn toàn (mặc định), black@0.85 = hơi mờ "
                              "có thể lộ chữ gốc, white@1.0 = che trắng đặc)")
        sp.add_argument("--mask-blur", type=int, default=25, dest="mask_blur",
                         help="[Chỉ dùng khi --mask-style blur] Độ mờ (bán kính blur, mặc định 25 — "
                              "tăng lên để mờ nhiều hơn, giảm xuống nếu vẫn còn đọc được chữ gốc)")
        sp.add_argument("--extra-blur", action="append", default=[], dest="extra_blur",
                         metavar="TOP,BOTTOM,STRENGTH[,LEFT,RIGHT]",
                         help="Làm mờ thêm 1 vùng tuỳ chỉnh: top,bottom,strength[,left,right] "
                              "(tỉ lệ 0-1 theo chiều cao & chiều ngang, bán kính blur). "
                              "Nếu không điền left,right sẽ blur full chiều ngang (0.0→1.0). "
                              "Dùng nhiều lần để blur nhiều vùng. "
                              "VD: --extra-blur 0.0,0.08,20 --extra-blur 0.45,0.60,15,0.1,0.9")

    def add_export_args(sp):
        """Tuỳ chọn cấu hình xuất video (encoder tăng tốc GPU, preset, CRF)."""
        sp.add_argument("--video-encoder", choices=["auto", "qsv", "mf", "nvenc", "cpu", "libx264"],
                        default="auto", dest="video_encoder",
                        help="Bộ mã hóa video: auto (mặc định) = tự động phát hiện và dùng GPU phần cứng "
                             "(Intel QSV, NVIDIA NVENC, Media Foundation), nếu không có sẽ dùng CPU. "
                             "cpu = ép dùng CPU (libx264).")
        sp.add_argument("--export-preset", choices=["ultrafast", "superfast", "veryfast", "faster", "fast", "medium"],
                        default="veryfast", dest="export_preset",
                        help="Tốc độ mã hóa khi dùng CPU libx264 (mặc định: veryfast — nhanh gấp 3-4 lần medium, chất lượng xuất sắc).")
        sp.add_argument("--crf", type=int, default=20, dest="crf",
                        help="Chất lượng nén video (CRF 0-51, mặc định 20 — chuẩn cân bằng dung lượng và độ sắc nét cao).")

    p_dub = sub.add_parser("dub", help="Chỉ lồng tiếng AI (không gắn phụ đề)")
    add_common_dub_args(p_dub)
    p_dub.set_defaults(func=cmd_dub)

    p_burn = sub.add_parser("burn", help="Chỉ gắn phụ đề vào video")
    p_burn.add_argument("video")
    p_burn.add_argument("script")
    p_burn.add_argument("-o", "--output", required=True)
    add_style_args(p_burn)
    add_mask_args(p_burn)
    add_export_args(p_burn)
    p_burn.add_argument("--preview", action="store_true",
                         help="CHỈ xuất ra 1 ẢNH xem trước vùng che/mờ (--mask-top/--mask-bottom) "
                              "tại 1 khung hình, KHÔNG render cả video — dùng để canh chỉnh nhanh trước "
                              "khi chạy thật. 'script' vẫn cần điền (bắt buộc về cú pháp) nhưng không "
                              "được dùng tới ở chế độ này, điền đường dẫn bất kỳ cũng được.")
    p_burn.add_argument("--preview-time", dest="preview_time", type=float, default=None,
                         help="Giây nào trong video để xuất ảnh xem trước (mặc định: giữa video)")
    p_burn.set_defaults(func=cmd_burn)

    p_all = sub.add_parser("all", help="Lồng tiếng + gắn phụ đề trong 1 lệnh (hoặc --no-dub để chỉ gắn phụ đề)")
    p_all.add_argument("--no-dub", "--sub-only", action="store_true", dest="no_dub",
                       help="Chỉ gắn phụ đề vào video gốc, KHÔNG lồng tiếng AI (giữ nguyên 100%% âm thanh gốc)")
    add_common_dub_args(p_all)
    add_style_args(p_all)
    add_mask_args(p_all)
    add_export_args(p_all)
    p_all.set_defaults(func=cmd_all)

    p_voices = sub.add_parser("voices", help="Xem danh sách giọng đọc")
    p_voices.set_defaults(func=cmd_voices)

    def add_whisper_args(sp):
        sp.add_argument("--model", default="small", choices=["tiny", "base", "small", "medium", "large-v3"],
                         help="Kích cỡ model Whisper (nhỏ = nhanh nhưng kém chính xác, lớn = chậm "
                              "nhưng chính xác hơn). Bị ghi đè nếu dùng --preset.")
        sp.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"],
                         help="auto (mặc định) = tự phát hiện GPU NVIDIA (CUDA), có thì dùng CUDA, "
                              "không có thì dùng CPU. Chỉ cần chỉnh tay nếu muốn ép buộc cụ thể.")
        sp.add_argument("--compute-type", default="auto", dest="compute_type",
                         choices=["auto", "int8", "float16"],
                         help="auto (mặc định) = float16 nếu chạy CUDA, int8 nếu chạy CPU "
                              "(lựa chọn phù hợp nhất cho từng loại phần cứng, tự động theo --device).")
        sp.add_argument("--preset", choices=["fast", "balanced", "quality"], default=None,
                         help="Bộ cấu hình dựng sẵn, ghi đè --model: "
                              "fast = model small (nhanh nhất, hợp video ngắn/xem qua); "
                              "balanced = model medium (cân bằng tốc độ/chính xác, khuyên dùng); "
                              "quality = model large-v3 (chính xác nhất, chậm nhất, nên có GPU).")
        sp.add_argument("--min-silence-ms", type=int, default=500, dest="min_silence_ms",
                         help="Ngưỡng VAD: khoảng lặng tối thiểu (ms) để tách câu (mặc định 500). "
                              "Tăng lên nếu phụ đề bị tách vụn quá nhiều, giảm xuống nếu bị gộp câu.")
        sp.add_argument("--beam-size", type=int, default=5, dest="beam_size",
                         help="Beam size khi giải mã (mặc định 5 — đủ tốt, KHÔNG khuyến khích tăng "
                              "cao hơn vì làm chậm đáng kể mà độ chính xác cải thiện không đáng kể).")
        sp.add_argument("--word-timestamps", action="store_true", default=True, dest="word_timestamps",
                         help="Căn chỉnh timestamp bám sát từng từ để chống trôi phụ đề khi có tiếng ồn lớn (mặc định BẬT).")
        sp.add_argument("--no-word-timestamps", action="store_false", dest="word_timestamps",
                         help="Tắt căn chỉnh timestamp từng từ nếu muốn tăng tốc nhận diện.")
        sp.add_argument("--vad", action="store_true", default=False, dest="vad",
                         help="Bật bộ lọc VAD (Silero VAD). Mặc định TẮT để bắt trọn 100%% lời thoại cả khi có nhạc nền hoặc tiếng ồn.")
        sp.add_argument("--sub-delay-ms", type=int, default=0, dest="sub_delay_ms",
                         help="Độ trễ mốc thời gian phụ đề (ms), mặc định 0. "
                              "Ví dụ: 100 hoặc 150 để lùi thời điểm phụ đề xuất hiện lại nếu thấy chữ nhảy ra trước tiếng nói.")

    def add_diarize_args(sp):
        sp.add_argument("--diarize", action="store_true",
                         help="Bật nhận diện người nói (speaker diarization) bằng pyannote-audio. "
                              "Cần cài thêm: pip install -r requirements-diarization.txt "
                              "và cần HuggingFace token (--hf-token hoặc biến môi trường HF_TOKEN).")
        sp.add_argument("--hf-token", dest="hf_token", default=None,
                         help="HuggingFace token để tải model diarization (model gated, cần chấp nhận "
                              "điều khoản). Nếu bỏ trống, đọc từ biến môi trường HF_TOKEN. "
                              "Tạo token tại: https://huggingface.co/settings/tokens")

    p_trans = sub.add_parser("transcribe", help="Tự nhận diện lời thoại (giọng nói) trong video bằng Whisper -> .srt")
    p_trans.add_argument("video")
    p_trans.add_argument("-o", "--output", default="transcript.srt")
    add_whisper_args(p_trans)
    add_diarize_args(p_trans)
    p_trans.set_defaults(func=cmd_transcribe)

    def add_translate_args(sp):
        sp.add_argument("--translate-engine", choices=["gemini", "groq"], default="gemini", dest="translate_engine",
                         help="Engine AI dùng để dịch phụ đề: gemini (mặc định) = Google Gemini; "
                              "groq = Groq Cloud (Llama 3.3 70B, Qwen 2.5 32B, siêu tốc độ).")
        sp.add_argument("--api-key", dest="api_key", default=None,
                         help="Gemini API key. Nếu bỏ trống, lấy từ biến môi trường GEMINI_API_KEY. "
                              "Lấy key miễn phí tại: https://aistudio.google.com/apikey")
        sp.add_argument("--groq-api-key", dest="groq_api_key", default=None,
                         help="Groq API key (khi dùng --translate-engine groq hoặc làm fallback). "
                              "Nếu bỏ trống, lấy từ biến môi trường GROQ_API_KEY. "
                              "Lấy key miễn phí tại: https://console.groq.com/keys")
        sp.add_argument("--translate-model", dest="translate_model", default=None,
                         help="Tên model dùng để dịch (mặc định: gemini-flash-latest cho Gemini, "
                              "llama-3.3-70b-versatile cho Groq).")
        sp.add_argument("--batch-size", dest="batch_size", type=int, default=30,
                         help="Nếu dịch nguyên file 1 lần bị lỗi/lệch số dòng, tool tự chia nhỏ ra dịch "
                              "lại theo từng nhóm bao nhiêu dòng 1 lần (mặc định 30).")

    add_gemini_args = add_translate_args

    p_tr = sub.add_parser("translate", help="Dịch file .srt sang tiếng Việt bằng Gemini hoặc Groq (giữ nguyên timestamp)")
    p_tr.add_argument("input", help="File .srt gốc (ngôn ngữ bất kỳ)")
    p_tr.add_argument("-o", "--output", default="translated.srt")
    p_tr.add_argument("--target", default="vi", help="Ngôn ngữ đích, mặc định tiếng Việt")
    add_translate_args(p_tr)
    p_tr.set_defaults(func=cmd_translate)

    p_chk = sub.add_parser("check-quota", help="Kiểm tra Gemini hoặc Groq API Key có hợp lệ và còn quota hay không")
    add_translate_args(p_chk)
    p_chk.set_defaults(func=cmd_check_quota)

    def add_ocr_args(sp):
        sp.add_argument("--crop-top", type=float, default=0.70, dest="crop_top",
                        help="Vị trí đỉnh vùng quét phụ đề (0.0 -> 1.0, mặc định: 0.70)")
        sp.add_argument("--crop-bottom", type=float, default=0.98, dest="crop_bottom",
                        help="Vị trí đáy vùng quét phụ đề (0.0 -> 1.0, mặc định: 0.98)")
        sp.add_argument("--crop-left", type=float, default=0.05, dest="crop_left",
                        help="Vị trí mép trái vùng quét phụ đề (0.0 -> 1.0, mặc định: 0.05)")
        sp.add_argument("--crop-right", type=float, default=0.95, dest="crop_right",
                        help="Vị trí mép phải vùng quét phụ đề (0.0 -> 1.0, mặc định: 0.95)")
        sp.add_argument("--ocr-fps", type=float, default=1.5, dest="ocr_fps",
                        help="Tần suất quét frame (khung hình/giây, mặc định 1.5 - quét siêu tốc & không sót chữ)")

    p_ocr = sub.add_parser("ocr", help="Trích xuất phụ đề cứng từ hình ảnh video bằng RapidOCR -> .srt")
    p_ocr.add_argument("video", help="File video đầu vào chứa phụ đề cứng")
    p_ocr.add_argument("-o", "--output", default="hardsub.srt", help="File .srt xuất ra")
    add_ocr_args(p_ocr)
    p_ocr.set_defaults(func=cmd_ocr)

    p_auto = sub.add_parser(
        "auto",
        help="TỰ ĐỘNG HOÀN TOÀN: nghe giọng nói (Whisper) hoặc quét chữ (OCR) -> dịch -> lồng tiếng AI -> gắn phụ đề"
    )
    p_auto.add_argument("video")
    p_auto.add_argument("-o", "--output", required=True)
    p_auto.add_argument("--ocr", "--use-ocr", action="store_true", dest="use_ocr",
                        help="Dùng RapidOCR quét chữ trên khung hình thay vì nhận diện giọng nói bằng Whisper")
    p_auto.add_argument("--no-dub", "--sub-only", action="store_true", dest="no_dub",
                        help="Chỉ nhận diện/quét chữ -> dịch -> gắn phụ đề vào video gốc (KHÔNG lồng tiếng AI, giữ 100%% âm thanh gốc)")
    add_ocr_args(p_auto)
    add_tts_options(p_auto)
    add_whisper_args(p_auto)
    add_diarize_args(p_auto)
    add_translate_args(p_auto)
    add_style_args(p_auto)
    p_auto.add_argument("--script-out", dest="script_out", default=None,
                         help="Nơi lưu file phụ đề tiếng Việt (máy dịch) để bạn xem/sửa lại")
    p_auto.add_argument("--pause-for-edit", action="store_true",
                         help="Dừng lại sau khi dịch xong để bạn tự sửa câu chữ, "
                              "chưa lồng tiếng/gắn phụ đề ngay")
    add_mask_args(p_auto)
    add_export_args(p_auto)
    p_auto.set_defaults(func=cmd_auto)

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
