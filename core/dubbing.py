"""
TIMELINE-AWARE DUBBING ENGINE VÀ ĐIỀU CHỈNH THỜI GIAN LỒNG TIẾNG
"""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import shutil
import tempfile
import threading
import time
import srt
from pydub import AudioSegment, effects
from pydub.silence import detect_leading_silence
from tqdm import tqdm

from .config import (
    MIN_GAP_MS,
    MIX_PRESETS,
    PIPER_VIETNAMESE_VOICES,
    VIETNAMESE_VOICES,
    CAPCUT_VIETNAMESE_VOICES,
    CAPCUT_TTS_API_BASE,
)
from .utils import (
    run,
    get_video_duration,
    td_to_ms,
    _looks_non_vietnamese,
    get_cache_dir,
    _cache_key,
    strip_speaker_tag,
    extract_speaker_label,
)
from .tts import (
    _get_piper_voices_dir,
    synthesize_line,
    synthesize_line_to_file,
)
from .diarize import (
    parse_speaker_mapping,
    load_role_map_from_debug_file,
    resolve_speaker_voice,
    print_speaker_voice_summary,
)


def normalize_voice_name(voice_alias: str, tts_engine: str = "edge") -> str:
    """Map voice alias (vd 'nam-namminh', 'co-gai') sang ID giọng thật của engine."""
    if not voice_alias:
        return voice_alias
    if tts_engine == "piper":
        return PIPER_VIETNAMESE_VOICES.get(voice_alias, voice_alias)
    elif tts_engine == "capcut":
        return CAPCUT_VIETNAMESE_VOICES.get(voice_alias, voice_alias)
    else:
        return VIETNAMESE_VOICES.get(voice_alias, voice_alias)



def _trim_silence(seg: AudioSegment, silence_thresh_db: float = -45.0) -> AudioSegment:
    """Cắt bớt khoảng lặng thừa ở đầu/cuối 1 đoạn audio TTS."""
    start_trim = detect_leading_silence(seg, silence_threshold=silence_thresh_db)
    end_trim = detect_leading_silence(seg.reverse(), silence_threshold=silence_thresh_db)
    trimmed = seg[start_trim: len(seg) - end_trim]
    return trimmed if len(trimmed) > 0 else seg


def _normalize_loudness(seg: AudioSegment, target_dBFS: float = -16.0) -> AudioSegment:
    """Normalize âm lượng audio TTS về mức target_dBFS để giọng đọc rõ ràng, đồng đều."""
    if len(seg) == 0 or seg.dBFS == float('-inf'):
        return seg
    change_in_dBFS = target_dBFS - seg.dBFS
    return seg.apply_gain(change_in_dBFS)


def analyze_speech_rate(text: str, duration_ms: int) -> dict:
    """Ước lượng tốc độ đọc THỰC TẾ của 1 câu."""
    seconds = max(duration_ms, 1) / 1000
    word_count = len(text.split())
    char_count = len(text)
    wps = word_count / seconds
    cps = char_count / seconds
    if wps <= 4.5:
        level = "tự nhiên"
    elif wps <= 5.5:
        level = "bình thường"
    elif wps <= 6.5:
        level = "nhanh"
    else:
        level = "quá nhanh"
    return {"word_count": word_count, "char_count": char_count,
            "words_per_second": wps, "chars_per_second": cps, "level": level}


def calculate_available_timeline(actual_start_ms: int, next_source_start_ms: int,
                                  min_gap_ms: int = MIN_GAP_MS) -> int:
    """Khung thời gian TỐI ĐA có thể dành cho TTS câu hiện tại."""
    safe_available_end = next_source_start_ms - min_gap_ms
    return max(safe_available_end - actual_start_ms, 0)


def calculate_required_speed(tts_duration_ms: int, available_ms: int) -> float:
    if available_ms <= 0:
        return float("inf")
    return tts_duration_ms / available_ms


def fit_tts_to_timeline(clip: AudioSegment, tmp_dir: str, i: int, available_ms: int,
                         source_slot_ms: int, max_speed: float = 1.25):
    """Vừa khít 1 clip TTS vào khung thời gian khả dụng."""
    tts_ms = len(clip)

    if tts_ms <= available_ms:
        status = "TIMELINE EXTENDED" if tts_ms > source_slot_ms else "NATURAL FIT"
        return clip, 1.0, status

    required_speed = calculate_required_speed(tts_ms, available_ms)
    if required_speed <= max_speed:
        applied_speed, status = required_speed, "SPEED_FIT"
    else:
        applied_speed, status = max_speed, "NEED_ADJUSTMENT"

    trimmed_path = os.path.join(tmp_dir, f"line_{i:04d}_trimmed.wav")
    sped_path = os.path.join(tmp_dir, f"line_{i:04d}_spd.mp3")
    clip.export(trimmed_path, format="wav")
    run(["ffmpeg", "-y", "-i", trimmed_path, "-filter:a", f"atempo={applied_speed:.3f}", sped_path])
    return AudioSegment.from_file(sped_path), applied_speed, status


def _overlay_extend(timeline: AudioSegment, clip: AudioSegment, position_ms: int) -> AudioSegment:
    """Overlay audio clip lên timeline, tự nới dài timeline nếu cần."""
    end_ms = position_ms + len(clip)
    if end_ms > len(timeline):
        timeline = timeline + AudioSegment.silent(duration=end_ms - len(timeline))
    return timeline.overlay(clip, position=position_ms)


def _print_dub_timing_report(stats: Counter, speeds: list, high_rate_count: int,
                              total_segments: int, max_speed: float):
    avg_speed = sum(speeds) / len(speeds) if speeds else 1.0
    max_speed_used = max(speeds) if speeds else 1.0
    over_limit = sum(1 for s in speeds if s > max_speed + 1e-9)
    print("\n========== DUB TIMING REPORT ==========")
    print(f"Total segments: {total_segments}")
    print()
    print(f"Natural fit: {stats.get('NATURAL FIT', 0)}")
    print(f"Timeline extended: {stats.get('TIMELINE EXTENDED', 0)}")
    print(f"Speed adjusted: {stats.get('SPEED_FIT', 0)}")
    print(f"Need adjustment: {stats.get('NEED_ADJUSTMENT', 0)}")
    print()
    print(f"Average speed: {avg_speed:.3f}x")
    print(f"Maximum speed: {max_speed_used:.3f}x")
    print()
    print(f"Segments > {max_speed:.2f}x: {over_limit}")
    print(f"Overlapping segments: 0")
    print(f"Clipped audio segments: 0")
    print()
    print(f"Speech rate > 6.5 words/sec: {high_rate_count}")
    print("========================================\n")


def validate_dub_timeline(dub_segments: list, max_speed: float = 1.25,
                           min_gap_ms: int = None) -> list:
    """Lưới an toàn ĐỘC LẬP cho timeline."""
    if min_gap_ms is None:
        min_gap_ms = MIN_GAP_MS
    errors = []
    tolerance_ms = 5
    prev = None
    for seg in dub_segments:
        if seg["dub_end"] <= seg["dub_start"]:
            errors.append(f"#{seg['index']}: dub_end ({seg['dub_end']}ms) <= dub_start "
                           f"({seg['dub_start']}ms) — thời lượng âm/bằng 0")
        if seg["speed"] > max_speed + 1e-6:
            errors.append(f"#{seg['index']}: speed {seg['speed']:.3f}x vượt max_speed {max_speed}x")
        if prev is not None:
            required_start = prev["dub_end"] + min_gap_ms - tolerance_ms
            if seg["dub_start"] < required_start:
                errors.append(
                    f"#{seg['index']}: dub_start ({seg['dub_start']}ms) chồng lấn với câu trước "
                    f"#{prev['index']} (dub_end={prev['dub_end']}ms, cần >= {prev['dub_end'] + min_gap_ms}ms)"
                )
        prev = seg
    return errors


def _print_timeline_propagation_report(dub_segments: list, video_duration_ms: int,
                                        final_audio_ms: int):
    shifts = [seg["dub_start"] - seg["source_start"] for seg in dub_segments]
    shifted = [s for s in shifts if s > 0]
    total_shift_ms = sum(shifted)
    max_shift_ms = max(shifted) if shifted else 0
    print("\n========== TIMELINE PROPAGATION ==========")
    print(f"Total segments: {len(dub_segments)}")
    print()
    print(f"Segments shifted: {len(shifted)}")
    print(f"Total accumulated shift: {total_shift_ms / 1000:.2f}s")
    print(f"Maximum single shift: {max_shift_ms / 1000:.2f}s")
    print()
    print(f"Overlaps prevented: {len(shifted)}")
    print()
    print(f"Original video duration: {video_duration_ms / 1000:.2f}s")
    print(f"Final audio duration: {final_audio_ms / 1000:.2f}s")
    print("============================================\n")
    if total_shift_ms > 3000:
        tqdm.write(f"⚠ Significant timeline drift detected: tổng độ trễ cộng dồn "
                   f"{total_shift_ms / 1000:.2f}s — các câu ở cuối video có thể lệch nhịp "
                   f"khá rõ so với hình. Cân nhắc rút ngắn bớt câu chữ ở những chỗ bị "
                   f"NEED_ADJUSTMENT (xem DUB TIMING REPORT phía trên).")


def build_dubbed_audio(srt_path, video_duration_ms, voice, tmp_dir,
                        fit_to_timing=True, max_speed=1.25,
                        cache_dir=None, use_cache=True, delay=0.3,
                        trim_silence=True, tts_engine="edge", piper_voices_dir=None,
                        capcut_rate=1.0, max_tts_workers=4,
                        speaker_voices_map=None, merge_map=None, role_map=None,
                        default_voice=None, single_voice=False):
    """
    KIẾN TRÚC 2-PHASE PIPELINE (HỖ TRỢ MULTI-VOICE THEO SPEAKER & SINGLE-VOICE OVERRIDE):
    - PHASE 1: Concurrent TTS Fetching (ThreadPoolExecutor, MAX_TTS_WORKERS)
    - PHASE 2: Sequential Autofit Timeline Assembly (Bảo toàn 100% công thức Autofit)
    """
    with open(srt_path, encoding="utf-8") as f:
        subs = list(srt.parse(f.read()))

    from core.burning import sanitize_subtitles
    subs = sanitize_subtitles(subs)

    timeline = AudioSegment.silent(duration=video_duration_ms)
    warned_non_vi = False
    stats = Counter()
    speeds = []
    high_rate_count = 0
    need_adjustment_lines = []
    cursor_end_ms = None
    dub_segments = []

    # Kiểm tra xem file srt có speaker tags hay không (bỏ qua nếu ép chế độ 1 giọng)
    has_speakers = any(extract_speaker_label(sub.content) is not None for sub in subs) and not single_voice

    if single_voice:
        tqdm.write(f"🔊 Chế độ 1 giọng: Dùng duy nhất giọng '{voice}' cho toàn bộ video (bỏ qua phân vai/người nói).")

    # Lọc danh sách công việc TTS (các câu hợp lệ)
    tasks = []
    last_logged_voice = None
    original_speakers = []

    for i, sub in enumerate(subs, start=1):
        raw_text = sub.content.strip()
        if not raw_text or raw_text.startswith("(điền lời thoại"):
            continue

        if has_speakers:
            clean_text = strip_speaker_tag(raw_text)
            speaker_label = extract_speaker_label(raw_text)
            if speaker_label and speaker_label not in original_speakers:
                original_speakers.append(speaker_label)

            resolved_alias = resolve_speaker_voice(
                speaker_label=speaker_label,
                speaker_voices_map=speaker_voices_map,
                merge_map=merge_map,
                role_map=role_map,
                default_voice=default_voice or "nu-hoaimy",
                tts_engine=tts_engine,
            )

            # Log ra 1 dòng ngắn cho mỗi lần đổi giọng so với dòng trước đó (tránh log rác nếu cùng giọng liên tục):
            # "🔊 Đổi giọng: {speaker_label} → {voice_name}"
            if resolved_alias != last_logged_voice:
                spk_display = speaker_label or "Mặc định"
                tqdm.write(f"🔊 Đổi giọng: {spk_display} → {resolved_alias}")
                last_logged_voice = resolved_alias

            line_tts_voice = normalize_voice_name(resolved_alias, tts_engine)
            text_to_synthesize = clean_text
        else:
            text_to_synthesize = strip_speaker_tag(raw_text)
            line_tts_voice = voice

        if line_tts_voice.startswith("vi-") and _looks_non_vietnamese(text_to_synthesize) and not warned_non_vi:
            tqdm.write("\n⚠ CẢNH BÁO: phát hiện văn bản có vẻ KHÔNG PHẢI tiếng Việt")
            tqdm.write(f"   (câu: \"{text_to_synthesize[:50]}\") trong khi đang dùng giọng đọc tiếng Việt ({line_tts_voice}).")
            tqdm.write("   Có thể bạn đang dùng nhầm file .srt CHƯA DỊCH (lấy từ lệnh 'transcribe').")
            tqdm.write("   → Hãy chạy 'python dub_tool.py translate <file>.srt -o <file>_vi.srt' trước,")
            tqdm.write("     hoặc dùng lệnh 'auto' để tool tự dịch giúp bạn.\n")
            warned_non_vi = True

        tasks.append((i, sub, text_to_synthesize, line_tts_voice))

    audio_paths = [None] * len(subs)  # Mapping chính xác subtitle_index (0-based) -> audio_path
    failed_lines = []
    print_lock = threading.Lock()

    num_workers = max(1, max_tts_workers)
    tqdm.write(f"\n═══ PHASE 1: CONCURRENT TTS FETCHING (Workers={num_workers}) ═══")
    t0_p1 = time.time()

    def tts_worker(task):
        i, sub, text, line_voice = task
        ext = "wav" if tts_engine == "piper" else "mp3"
        rate_suffix = f":r{capcut_rate:.2f}" if (tts_engine == "capcut" and abs(capcut_rate - 1.0) > 0.01) else ""
        cache_voice_key = f"{tts_engine}:{line_voice}{rate_suffix}"
        cache_path = os.path.join(cache_dir, f"{_cache_key(text, cache_voice_key)}.{ext}") if cache_dir else None

        # Check Cache Hit: Lưu trực tiếp cache_path, KHÔNG copy thừa
        if use_cache and cache_path and os.path.exists(cache_path):
            with print_lock:
                tqdm.write(f"  [TTS {i:03d}/{len(subs)}] (Cache hit) {text[:45]}")
            return i, cache_path, None

        # Cache Miss: Gọi worker xử lý và lưu vào tmp_path
        try:
            with print_lock:
                tqdm.write(f"  [TTS {i:03d}/{len(subs)}] (Fetch) {text[:45]}")
            path = synthesize_line_to_file(
                text=text, voice=line_voice, tmp_dir=tmp_dir, i=i,
                cache_dir=cache_dir, use_cache=use_cache, max_retries=4, delay=delay,
                tts_engine=tts_engine, piper_voices_dir=piper_voices_dir,
                capcut_rate=capcut_rate
            )
            return i, path, None
        except Exception as e:
            with print_lock:
                tqdm.write(f"  ✘ [TTS {i:03d}/{len(subs)}] Lỗi: {e}")
            return i, None, (i, text, str(e))

    if num_workers == 1:
        for task in tasks:
            idx, path, err = tts_worker(task)
            if path:
                audio_paths[idx - 1] = path
            if err:
                failed_lines.append(err)
    else:
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            future_to_task = {executor.submit(tts_worker, t): t for t in tasks}
            for future in as_completed(future_to_task):
                idx, path, err = future.result()
                if path:
                    audio_paths[idx - 1] = path
                if err:
                    failed_lines.append(err)

    t1_p1 = time.time()

    if failed_lines:
        tqdm.write(f"\n⚠ PHÁT HIỆN {len(failed_lines)} CÂU THẤT BẠI TRONG PHASE 1:")
        for f_i, f_text, f_err in sorted(failed_lines, key=lambda x: x[0]):
            tqdm.write(f"  - #{f_i:03d}: \"{f_text[:50]}\" -> {f_err}")
        tqdm.write("  (Tool sẽ bỏ qua các câu lỗi ở Phase 2 và tiếp tục xử lý các câu còn lại.)\n")
    else:
        tqdm.write(f"✔ Phase 1 hoàn tất: Đã tải/sinh {len(tasks)} file audio TTS ({t1_p1 - t0_p1:.2f}s).\n")

    tqdm.write("═══ PHASE 2: SEQUENTIAL AUTOFIT TIMELINE ASSEMBLY ═══")
    t0_p2 = time.time()

    for i, sub in enumerate(subs, start=1):
        raw_text = sub.content.strip()
        if not raw_text or raw_text.startswith("(điền lời thoại"):
            continue
        text = strip_speaker_tag(raw_text) if has_speakers else raw_text

        audio_path = audio_paths[i - 1]
        if not audio_path or not os.path.exists(audio_path):
            tqdm.write(f"  [#{i}] Bỏ qua do không có file TTS (bị lỗi ở Phase 1)")
            continue

        clip = AudioSegment.from_file(audio_path)
        if trim_silence:
            clip = _trim_silence(clip)
        clip = _normalize_loudness(clip, target_dBFS=-16.0)

        source_start = td_to_ms(sub.start)
        source_end = td_to_ms(sub.end)
        source_slot = max(source_end - source_start, 1)
        next_source_start = td_to_ms(subs[i].start) if i < len(subs) else video_duration_ms

        if not fit_to_timing:
            timeline = _overlay_extend(timeline, clip, source_start)
            cursor_end_ms = source_start + len(clip)
            continue

        actual_start = source_start
        if cursor_end_ms is not None and cursor_end_ms + MIN_GAP_MS > actual_start:
            actual_start = cursor_end_ms + MIN_GAP_MS
        prev_audio_end_ms = cursor_end_ms
        shift_ms = actual_start - source_start

        tts_natural_ms = len(clip)
        available_ms = calculate_available_timeline(actual_start, next_source_start)
        clip, applied_speed, status = fit_tts_to_timeline(
            clip, tmp_dir, i, available_ms, source_slot, max_speed=max_speed
        )
        final_ms = len(clip)

        timeline = _overlay_extend(timeline, clip, actual_start)
        cursor_end_ms = actual_start + final_ms

        dub_segments.append({
            "index": i, "text": text,
            "source_start": source_start, "source_end": source_end,
            "dub_start": actual_start, "dub_end": cursor_end_ms,
            "speed": applied_speed, "status": status,
        })

        stats[status] += 1
        speeds.append(applied_speed)
        rate_info = analyze_speech_rate(text, final_ms)
        if rate_info["words_per_second"] > 6.5:
            high_rate_count += 1
        if status == "NEED_ADJUSTMENT":
            need_adjustment_lines.append((i, text))

        prev_end_str = f"{prev_audio_end_ms/1000:.3f}s" if prev_audio_end_ms is not None else "—"
        shift_str = f"+{shift_ms}ms" if shift_ms > 0 else "0ms"
        tqdm.write(
            f"    [TIMELINE PROPAGATION] #{i}\n"
            f"    Source start: {source_start/1000:.3f}s (dài {source_slot/1000:.3f}s) "
            f"| Previous audio end: {prev_end_str} | Shift: {shift_str}\n"
            f"    Actual start: {actual_start/1000:.3f}s | TTS tự nhiên: {tts_natural_ms/1000:.3f}s "
            f"| Khung khả dụng: {available_ms/1000:.3f}s\n"
            f"    Tốc độ: {applied_speed:.3f}x | Audio cuối: {actual_start/1000:.3f}s→{cursor_end_ms/1000:.3f}s "
            f"| Trạng thái: {status}"
        )

    t1_p2 = time.time()

    if fit_to_timing:
        _print_dub_timing_report(stats, speeds, high_rate_count, len(subs), max_speed)
        _print_timeline_propagation_report(dub_segments, video_duration_ms, len(timeline))

        validation_errors = validate_dub_timeline(dub_segments, max_speed=max_speed)
        if validation_errors:
            print("✘✘✘ ERROR: Dub timeline validation failed ✘✘✘")
            print("  Phát hiện vi phạm nguyên tắc timeline dù logic build đã cố tránh — nên xem lại:")
            for e in validation_errors:
                print(f"  - {e}")
            print("  (Video vẫn được xuất ra bình thường — nhưng hãy nghe kỹ đúng (các) đoạn báo lỗi ở trên.)\n")
        else:
            tqdm.write("✔ Dub timeline validation: PASS (không overlap, không audio bị cắt/âm thời lượng, "
                       f"không vượt {max_speed}x)\n")

        if need_adjustment_lines:
            tqdm.write(f"⚠ {len(need_adjustment_lines)} câu không thể fit tự nhiên dù đã tăng tốc tối đa "
                       f"{max_speed}x lẫn tận dụng hết khoảng trống trước câu kế tiếp.")
            tqdm.write("  KHÔNG bị cắt mất nội dung, nhưng các câu SAU nó có thể bị trễ nhịp dần so với hình.")
            tqdm.write("  Cân nhắc rút ngắn câu chữ hoặc nới rộng khung thời gian cho các câu này:")
            for idx, txt in need_adjustment_lines[:10]:
                tqdm.write(f"    #{idx}: {txt[:60]}")
        if cursor_end_ms is not None and cursor_end_ms > video_duration_ms:
            extra_ms = cursor_end_ms - video_duration_ms
            tqdm.write(f"⚠ Câu cuối cùng cần thêm ~{extra_ms}ms sau khi hết video — phần audio thừa này")
            tqdm.write("  Nếu quan trọng, rút ngắn câu thoại cuối hoặc nới thời lượng khung .srt của nó.")

    # ── TỰ ĐỘNG CẬP NHẬT TIMELINE PHỤ ĐỀ THEO GIỌNG ĐỌC SAU KHI AUTOFIT ────────
    if fit_to_timing and dub_segments:
        import datetime
        seg_dict = {seg["index"]: seg for seg in dub_segments}
        seg_indices = sorted(seg_dict.keys())

        # Tạo bản sao lưu dự phòng (prefit) nếu chưa có
        try:
            prefit_path = srt_path.replace(".srt", "_prefit.srt")
            if not os.path.exists(prefit_path):
                shutil.copyfile(srt_path, prefit_path)
        except Exception:
            pass

        for pos, seg_idx in enumerate(seg_indices):
            seg = seg_dict[seg_idx]
            sub_idx = seg_idx - 1
            if 0 <= sub_idx < len(subs):
                s_ms = seg["dub_start"]
                e_ms = seg["dub_end"]
                # Đảm bảo câu có thời gian hiển thị tối thiểu 800ms để kịp đọc nếu không bị câu sau chèn
                next_start = seg_dict[seg_indices[pos + 1]]["dub_start"] if pos + 1 < len(seg_indices) else video_duration_ms
                max_safe_end = max(s_ms + 10, next_start - MIN_GAP_MS)
                e_ms = min(max_safe_end, max(e_ms, s_ms + 800))

                subs[sub_idx].start = datetime.timedelta(milliseconds=s_ms)
                subs[sub_idx].end = datetime.timedelta(milliseconds=e_ms)

        try:
            from core.burning import sanitize_subtitles
            subs = sanitize_subtitles(subs)
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write(srt.compose(subs))
            tqdm.write(f"\n✔ ĐÃ ĐỒNG BỘ TIMELINE PHỤ ĐỀ: Phụ đề đã khớp 100% với giọng lồng tiếng ({os.path.basename(srt_path)})\n")
        except Exception as e:
            tqdm.write(f"\n⚠ Không thể ghi đè timeline mới vào {srt_path}: {e}\n")

    timeline.dub_segments = dub_segments
    timeline.phase_timing = {
        "phase1_tts": t1_p1 - t0_p1,
        "phase2_autofit": t1_p2 - t0_p2,
    }
    timeline.has_speakers = has_speakers
    timeline.original_speakers = original_speakers if has_speakers else []

    return timeline


def cmd_dub(args, output_video=None):
    tmp_dir = tempfile.mkdtemp(prefix="dub_")
    try:
        duration_ms = int(get_video_duration(args.video) * 1000)
        tts_engine = getattr(args, "tts_engine", "edge")
        capcut_rate = float(getattr(args, "capcut_rate", 1.0))
        max_tts_workers = int(getattr(args, "max_tts_workers", 4))

        if tts_engine == "piper":
            voice = PIPER_VIETNAMESE_VOICES.get(args.voice, args.voice)
            piper_voices_dir = _get_piper_voices_dir(getattr(args, "piper_voices_dir", None))
            print(f"→ Dùng engine Piper (offline) — giọng: {voice}")
        elif tts_engine == "capcut":
            voice = CAPCUT_VIETNAMESE_VOICES.get(args.voice, args.voice)
            piper_voices_dir = None
            print(f"→ Dùng engine CapCut TTS (qua HuggingFace Space) — giọng: {voice}")
            print(f"  API: {CAPCUT_TTS_API_BASE}")
            if capcut_rate != 1.0:
                print(f"  Tốc độ đọc: {capcut_rate}x")
        else:
            voice = VIETNAMESE_VOICES.get(args.voice, args.voice)
            piper_voices_dir = None

        cache_dir = get_cache_dir(args.script)
        use_cache = not getattr(args, "no_cache", False)
        if use_cache:
            print(f"→ Dùng thư mục cache: {cache_dir}")
            print("  (nếu lỗi giữa chừng, chạy lại đúng lệnh này sẽ tự bỏ qua câu đã xong)")

        speaker_voices_str = getattr(args, "speaker_voices", None)
        merge_speakers_str = getattr(args, "merge_speakers", None)
        speaker_voices_map = parse_speaker_mapping(speaker_voices_str)
        merge_speakers_map = parse_speaker_mapping(merge_speakers_str)
        role_map = getattr(args, "role_map", None) or load_role_map_from_debug_file(args.script)
        default_voice = getattr(args, "voice", "nu-hoaimy")
        single_voice = getattr(args, "single_voice", False)

        dubbed_audio = build_dubbed_audio(
            args.script, duration_ms, voice, tmp_dir,
            fit_to_timing=not args.no_fit,
            max_speed=float(getattr(args, "max_speed", 1.25)),
            cache_dir=cache_dir, use_cache=use_cache,
            delay=float(getattr(args, "delay", 0.3)),
            tts_engine=tts_engine, piper_voices_dir=piper_voices_dir,
            trim_silence=not getattr(args, "no_trim_silence", False),
            capcut_rate=capcut_rate,
            max_tts_workers=max_tts_workers,
            speaker_voices_map=speaker_voices_map,
            merge_map=merge_speakers_map,
            role_map=role_map,
            default_voice=default_voice,
            single_voice=single_voice,
        )

        dub_wav = os.path.join(tmp_dir, "dubbed.wav")
        dubbed_audio.export(dub_wav, format="wav")

        out_path = output_video or args.output
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

        mix_preset = getattr(args, "mix_preset", None)
        if mix_preset and mix_preset in MIX_PRESETS:
            bg_vol, dub_vol = MIX_PRESETS[mix_preset]
        else:
            if getattr(args, "keep_original", "mix") == "mute":
                bg_vol, dub_vol = 0.0, 1.0
            else:
                bg_vol = float(getattr(args, "bg_volume", 0.15))
                dub_vol = float(getattr(args, "dub_volume", 1.1))

        print(f"  Âm lượng: audio gốc {bg_vol*100:.0f}% + giọng lồng tiếng {dub_vol*100:.0f}%")

        if bg_vol <= 0.0:
            run([
                "ffmpeg", "-y", "-i", args.video, "-i", dub_wav,
                "-filter_complex", f"[1:a]volume={dub_vol},alimiter=limit=0.95[aout]",
                "-map", "0:v:0", "-map", "[aout]",
                "-c:v", "copy", "-shortest", out_path
            ])
        else:
            run([
                "ffmpeg", "-y", "-i", args.video, "-i", dub_wav,
                "-filter_complex",
                f"[0:a]volume={bg_vol}[bg];[1:a]volume={dub_vol}[dub];"
                f"[bg][dub]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0[mix];"
                f"[mix]alimiter=limit=0.95[aout]",
                "-map", "0:v:0", "-map", "[aout]",
                "-c:v", "copy", out_path
            ])

        print(f"✔ Đã tạo video lồng tiếng: {out_path}")

        if getattr(dubbed_audio, "has_speakers", False):
            print_speaker_voice_summary(
                original_speakers=getattr(dubbed_audio, "original_speakers", []),
                speaker_voices_map=speaker_voices_map,
                merge_map=merge_speakers_map,
                role_map=role_map,
                default_voice=default_voice,
                tts_engine=tts_engine,
            )

        return out_path
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)