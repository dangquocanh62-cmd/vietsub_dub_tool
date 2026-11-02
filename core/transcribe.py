"""
TỰ NHẬN DIỆN LỜI THOẠI (SPEECH-TO-TEXT) BẰNG FASTER-WHISPER
"""

import ctypes
import os
import sys
import tempfile
import shutil
import srt
from tqdm import tqdm

from .config import WHISPER_PRESETS
from .utils import get_video_duration, run
from .burning import sanitize_subtitles


def _detect_cuda_available() -> bool:
    """Phát hiện có GPU NVIDIA (CUDA) dùng được cho ctranslate2/faster-whisper không."""
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def _resolve_whisper_device(device_arg: str) -> str:
    if device_arg and device_arg != "auto":
        return device_arg
    return "cuda" if _detect_cuda_available() else "cpu"


def _resolve_whisper_compute_type(compute_type_arg: str, device: str) -> str:
    if compute_type_arg and compute_type_arg != "auto":
        return compute_type_arg
    return "float16" if device == "cuda" else "int8"


def _resolve_whisper_settings(args):
    """Gộp preset + tuỳ chọn thủ công thành bộ cấu hình Whisper cuối cùng."""
    model = args.model
    preset = getattr(args, "preset", None)
    if preset and preset in WHISPER_PRESETS:
        model = WHISPER_PRESETS[preset]["model"]

    device = _resolve_whisper_device(args.device)
    compute_type = _resolve_whisper_compute_type(args.compute_type, device)
    return model, device, compute_type


def _find_and_register_cuda_dlls(verbose: bool = True):
    """Trên Windows, chủ động DÒ TÌM file cublas64_12.dll (và cudnn64_9.dll)."""
    if sys.platform != "win32":
        return

    target_dlls = ["cublas64_12.dll", "cudnn64_9.dll"]
    sibling_dlls = {
        "cublas64_12.dll": ["cublasLt64_12.dll"],
        "cudnn64_9.dll": ["cudnn_ops64_9.dll", "cudnn_cnn64_9.dll", "cudnn_engines_precompiled64_9.dll"],
    }

    candidate_dirs = []
    candidate_dirs += [
        os.path.join(sys.prefix, "Lib", "site-packages", "nvidia", "cublas", "bin"),
        os.path.join(sys.prefix, "Lib", "site-packages", "nvidia", "cudnn", "bin"),
        os.path.join(sys.prefix, "Lib", "site-packages", "nvidia", "cuda_nvrtc", "bin"),
        os.path.join(sys.prefix, "Lib", "site-packages", "nvidia", "cuda_runtime", "bin"),
    ]
    candidate_dirs.append(os.path.join(sys.prefix, "Lib", "site-packages", "torch", "lib"))
    for base in (r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA",
                 r"C:\Program Files (x86)\NVIDIA GPU Computing Toolkit\CUDA"):
        if os.path.isdir(base):
            for entry in os.listdir(base):
                candidate_dirs.append(os.path.join(base, entry, "bin"))
    candidate_dirs += [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]

    found_locations = {}
    registered_dirs = set()
    for d in candidate_dirs:
        if not d or not os.path.isdir(d):
            continue
        try:
            entries = os.listdir(d)
        except OSError:
            continue
        for dll_name in target_dlls:
            if dll_name in found_locations:
                continue
            if dll_name in entries:
                found_locations[dll_name] = os.path.join(d, dll_name)
                if d not in registered_dirs:
                    try:
                        os.add_dll_directory(d)
                        registered_dirs.add(d)
                    except Exception:
                        pass
        if len(found_locations) == len(target_dlls):
            break

    if verbose:
        missing_siblings = {}
        load_errors = {}
        for dll_name in target_dlls:
            if dll_name in found_locations:
                print(f"  ✔ Tìm thấy {dll_name} tại: {found_locations[dll_name]}")
                dll_dir = os.path.dirname(found_locations[dll_name])
                try:
                    dir_entries = set(os.listdir(dll_dir))
                except OSError:
                    dir_entries = set()
                missing = [s for s in sibling_dlls.get(dll_name, []) if s not in dir_entries]
                if missing:
                    missing_siblings[dll_name] = missing
                    print(f"    ⚠ NHƯNG thiếu {len(missing)} file phụ thuộc cùng thư mục: {', '.join(missing)}")
                    print(f"      → Đây thường là NGUYÊN NHÂN THẬT khiến {dll_name} 'not found or cannot "
                          f"be loaded' dù bản thân file {dll_name} vẫn tồn tại — Windows báo tên file gốc,")
                    print("        không báo rõ file phụ thuộc nào thật sự thiếu, nên dễ hiểu lầm.")

                try:
                    ctypes.WinDLL(found_locations[dll_name])
                    print(f"    ✔ Load thử trực tiếp bằng ctypes: THÀNH CÔNG "
                          f"(DLL này không phải nguyên nhân gây lỗi)")
                except OSError as e:
                    load_errors[dll_name] = e
                    winerror = getattr(e, "winerror", None)
                    print(f"    ✘ Load thử trực tiếp bằng ctypes: THẤT BẠI — mã lỗi Windows {winerror}")
                    if winerror == 126:
                        print("      → Lỗi 126 (MODULE NOT FOUND): thiếu 1 DLL phụ thuộc KHÁC mà mình")
                        print("        chưa liệt kê sẵn để kiểm tra. Nguyên nhân phổ biến nhất cho lỗi")
                        print("        này là THIẾU Microsoft Visual C++ Redistributable (cublas/cudnn")
                        print("        cần msvcp140.dll, vcruntime140.dll, vcruntime140_1.dll đi kèm hệ")
                        print("        điều hành, không phải do CUDA). Tải & cài bản mới nhất tại:")
                        print("          https://aka.ms/vs/17/release/vc_redist.x64.exe")
                    elif winerror == 193:
                        print("      → Lỗi 193 (NOT A VALID WIN32 APPLICATION): sai kiến trúc 32/64-bit,")
                        print("        hoặc file bị tải thiếu/hỏng dù đúng dung lượng hiển thị — thử gỡ")
                        print("        cài lại package chứa DLL này bằng pip.")
                    else:
                        print(f"      → Tra mã lỗi {winerror} tại: "
                              f"https://learn.microsoft.com/windows/win32/debug/system-error-codes")
            else:
                print(f"  ✘ KHÔNG tìm thấy {dll_name} ở bất kỳ đâu trên máy (đã quét "
                      f"{len(candidate_dirs)} thư mục, gồm site-packages, PyTorch, "
                      f"CUDA Toolkit trong Program Files, và toàn bộ PATH hệ thống).")
        if missing_siblings:
            print("\n  → Cách sửa (chạy trong CMD/PowerShell):")
            if "cublas64_12.dll" in missing_siblings:
                print("      pip uninstall nvidia-cublas-cu12 -y")
                print("      pip install nvidia-cublas-cu12")
            if "cudnn64_9.dll" in missing_siblings:
                print("      pip uninstall nvidia-cudnn-cu12 -y")
                print("      pip install nvidia-cudnn-cu12")
            print("    Cài đặt qua pip đôi khi tải thiếu file (do lỗi mạng giữa chừng, hoặc phiên bản")
            print("    package không trọn bộ) — gỡ và cài lại thường khắc phục được lỗi thiếu file này.")
        elif load_errors:
            print("\n  → Các file DLL đều CÓ MẶT và đủ file phụ thuộc mình biết trước, nhưng vẫn load lỗi")
            print("    thật (xem mã lỗi Windows cụ thể ở trên) — làm theo hướng dẫn tương ứng mã lỗi đó.")
        elif len(found_locations) < len(target_dlls):
            print("  → Nếu bạn CHẮC CHẮN đã cài CUDA Toolkit, mở CMD gõ lệnh sau để tự tìm:")
            print(f"      where /R C:\\ {target_dlls[0]}")
            print("    rồi cho mình biết đường dẫn thật để mình sửa đúng chỗ. Có thể máy bạn")
            print("    đang có bản CUDA KHÁC version 12 (VD: cublas64_11.dll của CUDA 11),")
            print("    lệch với version mà faster-whisper/CTranslate2 hiện tại cần (CUDA 12).")


def _preprocess_audio_for_whisper(video_path: str, tmp_dir: str) -> str:
    """
    Trích xuất và lọc sạch âm thanh qua bộ lọc dải tần giọng nói trước khi đưa vào Whisper:
    - 16kHz mono 16-bit PCM (chuẩn đầu vào gốc của Whisper).
    - highpass=f=80: Cắt bỏ các dải tần siêu trầm (<80Hz: tiếng nổ bass, rung lắc, gió thổi, tiếng va đập).
    - lowpass=f=8000: Cắt bỏ các dải tần quá cao (>8kHz: tiếng rít, cọ xát kim loại, chũm chọe).
    - alimiter=limit=0.90: Khống chế các đỉnh âm lượng lớn đột ngột (tiếng hét, tiếng súng/nổ) không bị vỡ sóng (clipping)
      tránh làm bão hòa attention weights của Whisper dẫn đến hallucination hoặc lệch timestamp.
    """
    clean_wav = os.path.join(tmp_dir, "whisper_clean_audio.wav")
    filter_chain = "highpass=f=80,lowpass=f=8000,alimiter=limit=0.90"
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-ac", "1", "-ar", "16000",
        "-af", filter_chain,
        clean_wav
    ]
    try:
        run(cmd)
        if os.path.isfile(clean_wav) and os.path.getsize(clean_wav) > 0:
            return clean_wav
    except Exception as e:
        print(f"  ⚠ Không tạo được audio tiền xử lý ({e}), dùng file gốc.")
    return video_path


def cmd_transcribe(args):
    model_name, device, compute_type = _resolve_whisper_settings(args)
    _find_and_register_cuda_dlls(verbose=(device != "cpu"))
    from faster_whisper import WhisperModel

    beam_size = getattr(args, "beam_size", 5)
    min_silence_ms = getattr(args, "min_silence_ms", 500)
    word_timestamps = getattr(args, "word_timestamps", None)
    if word_timestamps is None:
        word_timestamps = True
    total_ms = int(get_video_duration(args.video) * 1000)

    def _load_model(dev, ctype):
        try:
            return WhisperModel(model_name, device=dev, compute_type=ctype, local_files_only=True)
        except Exception:
            print(f"→ Model '{model_name}' chưa có sẵn offline, đang kết nối mạng để tải về (device={dev}, compute_type={ctype})...")
            return WhisperModel(model_name, device=dev, compute_type=ctype, local_files_only=False)

    vad_on = getattr(args, "vad", False)

    def _transcribe_with_progress(model, audio_source, vad_intervals=None):
        vad_parameters = dict(
            threshold=0.5,
            min_silence_duration_ms=min_silence_ms,
            min_speech_duration_ms=250,
            max_speech_duration_s=15.0,
            speech_pad_ms=250,
        ) if vad_on else None

        segments, info = model.transcribe(
            audio_source,
            beam_size=beam_size,
            vad_filter=vad_on,
            vad_parameters=vad_parameters,
            word_timestamps=word_timestamps,
            condition_on_previous_text=False,
            compression_ratio_threshold=2.4,
            log_prob_threshold=-1.0,
            no_speech_threshold=0.6,
            no_repeat_ngram_size=3,
            hallucination_silence_threshold=2.0,
        )
        subs = []
        with tqdm(total=total_ms, desc="Nhận diện lời thoại", unit="ms") as bar:
            last = 0
            for i, seg in enumerate(segments, start=1):
                text = seg.text.strip()
                if text:
                    # 1. Lấy mốc cơ sở từ word_timestamps nếu có
                    if getattr(seg, "words", None) and len(seg.words) > 0:
                        first_word = seg.words[0]
                        last_word = seg.words[-1]
                        start_sec = first_word.start
                        end_sec = last_word.end

                        # Chống lem tiếng ồn đi trước: Nếu từ đầu tiên bị kéo dài bất thường (> 0.6s)
                        # do Whisper bị lem năng lượng từ tiếng nổ/tiếng ồn xảy ra ngay trước câu,
                        # tự động gọt bớt phần tiếng ồn, neo sát vào thời điểm người thực sự bắt đầu nói.
                        first_dur = first_word.end - first_word.start
                        if first_dur > 0.6:
                            max_first_word_len = min(0.45, first_dur)
                            start_sec = max(start_sec, first_word.end - max_first_word_len)

                        # Chống kéo đuôi: Nếu từ cuối cùng bị kéo dài bất thường (> 0.8s)
                        # do dính tiếng ồn/hiệu ứng âm thanh ngay sau câu nói, tự động gọt bớt.
                        last_dur = last_word.end - last_word.start
                        if last_dur > 0.8:
                            end_sec = min(end_sec, last_word.start + 0.6)
                    else:
                        start_sec = seg.start
                        end_sec = seg.end

                    # 2. Hiệu chỉnh chống dính tiếng ồn & chống phụ đề xuất hiện sớm bằng Silero VAD
                    if vad_intervals:
                        # Chỉ lấy các speech chunk thực sự giao thoa với khoảng thời gian của câu
                        speech_chunks = [
                            (vst, ven) for vst, ven in vad_intervals
                            if vst < end_sec and ven > start_sec - 0.05
                        ]
                        if speech_chunks:
                            first_vad_st = speech_chunks[0][0]
                            last_vad_en = speech_chunks[-1][1]

                            # Neo mốc bắt đầu sát vào thời điểm có tiếng nói con người thực tế:
                            # Nếu Whisper gán start_sec sớm hơn thời điểm tiếng nói bắt đầu:
                            if first_vad_st > start_sec:
                                start_sec = max(start_sec, first_vad_st - 0.015)

                            # Nếu Whisper kéo đuôi trôi theo tiếng ồn sau khi nhân vật đã dứt lời (> 0.15s)
                            if last_vad_en < end_sec - 0.15:
                                end_sec = min(end_sec, last_vad_en + 0.10)

                    # 3. Đảm bảo an toàn không để start_sec vượt quá giới hạn an toàn của từ cuối cùng
                    if getattr(seg, "words", None) and len(seg.words) > 0:
                        w_end = seg.words[-1].end
                        start_sec = min(start_sec, max(seg.start, w_end - 0.2))

                    if end_sec <= start_sec:
                        end_sec = start_sec + 0.5

                    subs.append(srt.Subtitle(
                        index=i,
                        start=srt.timedelta(seconds=start_sec),
                        end=srt.timedelta(seconds=end_sec),
                        content=text
                    ))
                now = int(seg.end * 1000)
                bar.update(max(now - last, 0))
                last = now
            bar.update(max(total_ms - last, 0))
        return subs, info

    tmp_audio_dir = tempfile.mkdtemp(prefix="whisper_audio_")
    try:
        print("→ Tiền xử lý âm thanh (lọc dải tần giọng nói & nén chống vỡ tiếng ồn lớn)...")
        audio_for_whisper = _preprocess_audio_for_whisper(args.video, tmp_audio_dir)

        # Trích xuất mốc thời gian giọng nói thực (Silero VAD) để khử triệt để hiện tượng
        # phụ đề bị kéo sớm theo tiếng nổ, tiếng va đập, tiếng động lớn trước lời thoại.
        vad_intervals = []
        try:
            import wave
            import numpy as np
            from faster_whisper.vad import VadOptions, get_speech_timestamps
            with wave.open(audio_for_whisper, "rb") as w:
                audio_data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
            v_opts = VadOptions(
                threshold=0.45,
                min_speech_duration_ms=100,
                min_silence_duration_ms=250,
                speech_pad_ms=10
            )
            chunks = get_speech_timestamps(audio_data, v_opts)
            vad_intervals = [(c["start"] / 16000.0, c["end"] / 16000.0) for c in chunks]
            print(f"✔ Đã phân tích {len(vad_intervals)} mốc giọng nói chuẩn xác (Silero VAD) để chống dính tiếng ồn.")
        except Exception as e:
            print(f"  ⚠ Không chạy được Silero VAD ({e}), dùng mốc thời gian gốc của Whisper.")

        print("→ Đang nghe và nhận diện lời thoại trong video...")
        try:
            model = _load_model(device, compute_type)
            subs, info = _transcribe_with_progress(model, audio_for_whisper, vad_intervals=vad_intervals)
        except Exception as e:
            is_oom = "out of memory" in str(e).lower()

            if device == "cuda" and is_oom and compute_type != "int8_float16":
                print(f"\n⚠ Hết bộ nhớ GPU (VRAM) khi chạy {device}/{compute_type}: {e}")
                print(f"  Model '{model_name}' ở compute_type float16 cần khá nhiều VRAM.")
                print("  Thử lại với compute_type nhẹ hơn (int8_float16 — vẫn chạy GPU, nhanh hơn")
                print("  CPU nhiều lần, chỉ giảm nhẹ độ chính xác) trước khi lùi hẳn về CPU...")
                try:
                    compute_type = "int8_float16"
                    model = _load_model(device, compute_type)
                    subs, info = _transcribe_with_progress(model, audio_for_whisper, vad_intervals=vad_intervals)
                except Exception as e2:
                    print(f"\n⚠ Vẫn hết VRAM ở int8_float16: {e2}")
                    print("  Tự động chuyển hẳn sang CPU/int8 và chạy lại từ đầu...")
                    device, compute_type = "cpu", "int8"
                    try:
                        model = _load_model(device, compute_type)
                        subs, info = _transcribe_with_progress(model, audio_for_whisper, vad_intervals=vad_intervals)
                    except Exception as e3:
                        print(f"✘ Vẫn lỗi sau khi lùi về CPU: {e3}")
                        sys.exit(1)
            elif device != "cpu":
                print(f"\n⚠ Không dùng được {device}/{compute_type}: {e}")
                print("  (Thường do thiếu thư viện CUDA Toolkit/cuDNN trên máy, dù có GPU NVIDIA —")
                print("   driver GPU và CUDA Toolkit là 2 thứ khác nhau, cài driver thôi chưa đủ.)")
                print("  Tự động chuyển sang CPU/int8 và chạy lại từ đầu...")
                device, compute_type = "cpu", "int8"
                try:
                    model = _load_model(device, compute_type)
                    subs, info = _transcribe_with_progress(model, audio_for_whisper, vad_intervals=vad_intervals)
                except Exception as e2:
                    print(f"✘ Vẫn lỗi sau khi lùi về CPU: {e2}")
                    sys.exit(1)
            else:
                print("✘ Không nhận diện được. Kiểm tra lại kết nối internet (lần đầu cần tải model) "
                      "hoặc video có bị lỗi/hỏng không.")
                print(f"  Chi tiết lỗi: {e}")
                sys.exit(1)

        print(f"  Whisper model: {model_name}")
        print(f"  Device: {device}")
        print(f"  Compute type: {compute_type}")
        print(f"  Language: {info.language} (độ tin cậy {info.language_probability:.0%})")
        print(f"  VAD filter: {'bật' if vad_on else 'tắt (mặc định — tránh nuốt chữ khi có nhạc nền)'}")
        print(f"  Word timestamps: {'bật' if word_timestamps else 'tắt'}")
        print(f"  Beam size: {beam_size}")

        # Hỗ trợ bù trừ độ trễ phụ đề thủ công nếu người dùng chỉ định (--sub-delay-ms)
        sub_delay_ms = getattr(args, "sub_delay_ms", 0) or 0
        if sub_delay_ms:
            delay_sec = sub_delay_ms / 1000.0
            for s in subs:
                s.start = max(srt.timedelta(0), s.start + srt.timedelta(seconds=delay_sec))
                s.end = max(s.start + srt.timedelta(milliseconds=300), s.end + srt.timedelta(seconds=delay_sec))
            print(f"✔ Đã áp dụng độ trễ mốc thời gian phụ đề: +{sub_delay_ms}ms")

        # Tự động lọc sạch phụ đề: chống đè nhau và cắt câu kéo dài bất thường do tiếng ồn
        subs = sanitize_subtitles(subs)

        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(srt.compose(subs))
        print(f"✔ Đã tạo phụ đề gốc ({info.language}): {args.output}  ({len(subs)} câu)")
    finally:
        shutil.rmtree(tmp_audio_dir, ignore_errors=True)

    # ── Speaker Diarization (opt-in) ────────────────────────────
    # Toàn bộ khối này bọc try/except: nếu diarization lỗi bất kỳ,
    # file .srt thường đã ghi ở trên KHÔNG BỊ MẤT.
    diarize = getattr(args, "diarize", False)
    if diarize:
        try:
            from .diarize import (
                run_diarization,
                match_speaker_to_subtitle,
                postprocess_speaker_matches,
                compute_speaker_pitch,
                assign_speaker_roles,
                export_srt_with_speaker_tags,
                write_diarization_debug_report,
                print_diarization_summary,
            )

            # Resolve HF token: args > env var
            hf_token = getattr(args, "hf_token", None) or os.environ.get("HF_TOKEN", "")
            if not hf_token:
                print("⚠ Chưa có HuggingFace token. Cung cấp qua --hf-token hoặc biến môi trường HF_TOKEN.")
                print("  Tạo token tại: https://huggingface.co/settings/tokens")
                print("  Chấp nhận điều khoản model: https://huggingface.co/pyannote/speaker-diarization-3.1")
                print(f"  → Bỏ qua diarization, giữ nguyên file .srt thường: {args.output}")
            else:
                print("\n── Speaker Diarization ──")
                speaker_segments = run_diarization(args.video, hf_token)

                # Match từng câu phụ đề với speaker
                speaker_info_list = []
                for sub in subs:
                    sub_start = sub.start.total_seconds()
                    sub_end = sub.end.total_seconds()
                    info_match = match_speaker_to_subtitle(sub_start, sub_end, speaker_segments)
                    speaker_info_list.append(info_match)

                # Hậu xử lý: nếu toàn video chỉ có đúng 1 người nói, gán toàn bộ UNKNOWN về người đó
                speaker_info_list = postprocess_speaker_matches(speaker_info_list, speaker_segments)

                # Phân loại vai trò (Role Bucketing: main / male_secondary / female_secondary)
                pitch_map = compute_speaker_pitch(args.video, speaker_segments)
                role_map = assign_speaker_roles(speaker_segments, pitch_map)

                # Ghi đè file .srt với speaker tag
                export_srt_with_speaker_tags(subs, speaker_info_list, args.output, role_map=role_map)
                print(f"✔ Đã ghi phụ đề có speaker tag: {args.output}")

                # Debug report
                write_diarization_debug_report(
                    args.output,
                    speaker_segments,
                    speaker_info_list,
                    subs,
                    role_map=role_map,
                    pitch_map=pitch_map,
                )

                # Console summary + khuyến nghị
                print_diarization_summary(speaker_info_list)

        except ImportError as e:
            print(f"\n⚠ {e}")
            print(f"  → Bỏ qua diarization, giữ nguyên file .srt thường: {args.output}")
        except Exception as e:
            print(f"\n⚠ Diarization thất bại: {e}")
            print(f"  → Kết quả Whisper KHÔNG bị mất, giữ nguyên file .srt thường: {args.output}")
    else:
        print("  Chạy tiếp lệnh 'translate' để dịch sang tiếng Việt.")

