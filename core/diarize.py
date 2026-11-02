"""
SPEAKER DIARIZATION — NHẬN DIỆN NGƯỜI NÓI BẰNG PYANNOTE-AUDIO

Thư viện diarization (torch, torchaudio, pyannote-audio) KHÔNG nằm trong
requirements.txt chính. Cài riêng:
    pip install -r requirements-diarization.txt

Cần HuggingFace token (chấp nhận điều khoản model gated):
    https://huggingface.co/settings/tokens
    https://huggingface.co/pyannote/speaker-diarization-3.1
"""

import os
import re
import subprocess
import sys
import tempfile
import wave
from dataclasses import dataclass, field
from datetime import timedelta
from typing import List, Optional

import numpy as np

# ──────────────────────────────────────────────────────────────
# HẰNG SỐ NGƯỠNG — dễ chỉnh sau
# ──────────────────────────────────────────────────────────────
CONFIDENT_THRESHOLD = 0.85   # ratio >= mức này -> CONFIDENT
UNCERTAIN_THRESHOLD = 0.55   # ratio >= mức này (và < CONFIDENT) -> UNCERTAIN
# ratio < UNCERTAIN_THRESHOLD, hoặc không có overlap nào -> UNKNOWN

MALE_PITCH_MAX = 150.0       # pitch <= ngưỡng này -> male_secondary
FEMALE_PITCH_MIN = 170.0     # pitch >= ngưỡng này -> female_secondary
# Khoảng giữa 150-170Hz là vùng xám, chưa đủ tin cậy để phân loại -> gộp về main (fallback an toàn)



# ──────────────────────────────────────────────────────────────
# DATACLASS GIỮ METADATA TÁCH RỜI KHỎI CONTENT
# ──────────────────────────────────────────────────────────────
@dataclass
class SubtitleWithSpeaker:
    """Metadata người nói cho 1 câu phụ đề — content là text GỐC, KHÔNG có tag."""
    index: int
    start: float          # seconds
    end: float            # seconds
    content: str          # text gốc, KHÔNG chứa [Người X] hay bất kỳ tag nào
    speaker: Optional[str] = None       # "Người 1", "Người 2", ... hoặc None
    confidence: float = 0.0
    status: str = "UNKNOWN"             # "CONFIDENT" / "UNCERTAIN" / "UNKNOWN"


# ──────────────────────────────────────────────────────────────
# HÀM CHÍNH: CHẠY DIARIZATION
# ──────────────────────────────────────────────────────────────
def run_diarization(video_path: str, hf_token: str) -> List[dict]:
    """Chạy speaker diarization trên video, trả về danh sách segment đã chuẩn hoá.

    Returns:
        list[dict]: [{"speaker": "Người 1", "start": float, "end": float}, ...]
        Speaker đã chuẩn hoá theo thứ tự xuất hiện (SPEAKER_00 -> "Người 1", ...).
    """
    # --- Import lazy, bọc try/except ---
    try:
        from pyannote.audio import Pipeline
        import torch
    except ImportError:
        raise ImportError(
            "Chưa cài thư viện diarization. Chạy:\n"
            "    pip install -r requirements-diarization.txt\n"
            "\n"
            "(Cần cài torch, torchaudio, pyannote-audio)"
        )

    # --- Trích audio ra WAV tạm (mono 16kHz) ---
    tmp_wav = None
    try:
        tmp_fd, tmp_wav = tempfile.mkstemp(suffix=".wav")
        os.close(tmp_fd)

        ffmpeg_cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vn",                      # bỏ video
            "-acodec", "pcm_s16le",     # WAV PCM 16-bit
            "-ar", "16000",             # 16 kHz
            "-ac", "1",                 # mono
            tmp_wav,
        ]
        result = subprocess.run(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg không trích được audio từ video:\n{result.stderr[-1000:]}"
            )

        # --- Load pipeline (mặc định CPU để tránh tranh VRAM với Whisper) ---
        print("→ Đang tải model diarization (pyannote/speaker-diarization-3.1)...")
        try:
            pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                token=hf_token,
            )
        except Exception as e:
            err_str = str(e).lower()
            if "401" in err_str or "403" in err_str or "unauthorized" in err_str or "forbidden" in err_str \
               or "gated" in err_str or "private" in err_str or "accept" in err_str:
                raise RuntimeError(
                    "Không xác thực được HuggingFace token cho model diarization.\n"
                    "\n"
                    "Hướng dẫn:\n"
                    "  1. Tạo token tại: https://huggingface.co/settings/tokens\n"
                    "  2. Vào TỪNG trang model sau và chấp nhận điều khoản sử dụng:\n"
                    "     • https://huggingface.co/pyannote/speaker-diarization-3.1\n"
                    "     • https://huggingface.co/pyannote/segmentation-3.0\n"
                    "     • https://huggingface.co/pyannote/speaker-diarization-community-1\n"
                    "     (Pipeline cần TẤT CẢ các model trên — thiếu 1 sẽ bị lỗi)\n"
                    "  3. Chạy lại với: --hf-token YOUR_TOKEN\n"
                    "     hoặc đặt biến môi trường: set HF_TOKEN=YOUR_TOKEN"
                ) from e
            raise

        # Ép chạy trên CPU — an toàn, không tranh VRAM với Whisper
        pipeline.to(torch.device("cpu"))

        # Đọc WAV qua wave + numpy để truyền waveform dict trực tiếp vào pipeline
        # (Bỏ qua torchcodec, tránh lỗi thiếu FFmpeg shared DLLs trên Windows)
        with wave.open(tmp_wav, "rb") as wf:
            sample_rate = wf.getframerate()
            n_frames = wf.getnframes()
            frames = wf.readframes(n_frames)
            audio_data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
            waveform = torch.from_numpy(audio_data).unsqueeze(0)

        # --- Chạy diarization ---
        print("→ Đang phân tích người nói (diarization)... (có thể mất vài phút)")
        diarization = pipeline({"waveform": waveform, "sample_rate": sample_rate})

        # Tương thích cả pyannote 3.x (trả Annotation trực tiếp) và 4.x (trả DiarizeOutput)
        annotation = getattr(diarization, "speaker_diarization", diarization)

        # --- Chuẩn hoá speaker theo thứ tự xuất hiện ---
        raw_segments = []
        for turn, _, speaker_label in annotation.itertracks(yield_label=True):
            raw_segments.append({
                "raw_label": speaker_label,
                "start": turn.start,
                "end": turn.end,
            })

        # Sắp xếp theo thời gian xuất hiện
        raw_segments.sort(key=lambda s: s["start"])

        # Map SPEAKER_xx -> "Người 1", "Người 2", ... theo thứ tự xuất hiện đầu tiên
        label_map = {}
        counter = 0
        for seg in raw_segments:
            raw = seg["raw_label"]
            if raw not in label_map:
                counter += 1
                label_map[raw] = f"Người {counter}"

        # Build kết quả cuối
        segments = []
        for seg in raw_segments:
            segments.append({
                "speaker": label_map[seg["raw_label"]],
                "start": seg["start"],
                "end": seg["end"],
            })

        n_speakers = len(label_map)
        print(f"  Phát hiện {n_speakers} người nói: {', '.join(label_map.values())}")
        return segments

    finally:
        # Dọn file tạm
        if tmp_wav and os.path.exists(tmp_wav):
            try:
                os.remove(tmp_wav)
            except OSError:
                pass


# ──────────────────────────────────────────────────────────────
# PITCH ESTIMATION & ROLE BUCKETING (MULTI-VOICE TTS)
# ──────────────────────────────────────────────────────────────
def test_pitch_measurement(target_freq: float = 120.0, sample_rate: int = 16000, duration_sec: float = 2.0) -> dict:
    """Sanity check: kiểm tra độ chính xác của hàm đo pitch trên sóng sin chuẩn 120Hz."""
    try:
        import librosa
    except ImportError:
        raise ImportError(
            "Chưa cài thư viện librosa để ước lượng pitch. Chạy:\n"
            "    pip install -r requirements-diarization.txt"
        )

    t = np.linspace(0, duration_sec, int(sample_rate * duration_sec))
    wave_data = (np.sin(2 * np.pi * target_freq * t)).astype(np.float32)

    f0, _, _ = librosa.pyin(
        wave_data,
        fmin=65,
        fmax=300,
        sr=sample_rate,
    )
    valid_f0 = f0[~np.isnan(f0)]
    measured_pitch = float(np.median(valid_f0)) if len(valid_f0) > 0 else 0.0
    err_pct = abs(measured_pitch - target_freq) / target_freq * 100.0

    print(f"Tần số thật: {target_freq:.1f}Hz | Tần số đo được: {measured_pitch:.1f}Hz | Sai lệch: {err_pct:.2f}%")
    if err_pct > 10.0:
        print("⚠ PHÁT HIỆN LỖI ĐO PITCH — kiểm tra lại sample rate truyền vào librosa.pyin() có khớp với sample rate thật của audio buffer không.")

    return {
        "target_freq": target_freq,
        "measured_pitch": measured_pitch,
        "error_pct": err_pct,
    }


def compute_speaker_pitch(video_path: str, speaker_segments: List[dict]) -> dict:
    """Ước lượng cao độ cơ bản (F0/pitch) cho từng speaker bằng librosa.pyin.

    - Trích audio mono 16kHz PCM qua ffmpeg.
    - Với mỗi speaker, gộp toàn bộ các đoạn audio thuộc speaker đó lại.
    - Chạy librosa.pyin(fmin=65, fmax=300) trên đoạn gộp.
    - Lấy median của các giá trị pitch hợp lệ (loại bỏ NaN).
    - Nếu tổng thời lượng < 1.0 giây hoặc không tìm thấy pitch hợp lệ -> None.

    Returns:
        dict[str, Optional[float]]: {"Người 1": 145.2, "Người 2": 210.5, ...}
    """
    try:
        import librosa
    except ImportError:
        raise ImportError(
            "Chưa cài thư viện librosa để ước lượng pitch. Chạy:\n"
            "    pip install -r requirements-diarization.txt"
        )

    unique_speakers = list(dict.fromkeys(s["speaker"] for s in speaker_segments if s.get("speaker")))
    pitch_map = {}
    if not unique_speakers:
        return pitch_map

    tmp_wav = None
    try:
        tmp_fd, tmp_wav = tempfile.mkstemp(suffix=".wav")
        os.close(tmp_fd)

        ffmpeg_cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            tmp_wav,
        ]
        result = subprocess.run(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            print(f"  ⚠ Không trích được audio để tính pitch: {result.stderr[-300:]}")
            for spk in unique_speakers:
                pitch_map[spk] = None
            return pitch_map

        # Đọc WAV qua wave + numpy
        with wave.open(tmp_wav, "rb") as wf:
            sr = wf.getframerate()
            n_frames = wf.getnframes()
            frames = wf.readframes(n_frames)
            audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0

        for spk in unique_speakers:
            spk_segs = [s for s in speaker_segments if s["speaker"] == spk]
            tot_dur = sum(s["end"] - s["start"] for s in spk_segs)
            if tot_dur < 1.0:
                pitch_map[spk] = None
                continue

            slices = []
            for s in spk_segs:
                i_start = max(0, int(s["start"] * sr))
                i_end = min(len(audio), int(s["end"] * sr))
                if i_end > i_start:
                    slices.append(audio[i_start:i_end])

            if not slices:
                pitch_map[spk] = None
                continue

            spk_audio = np.concatenate(slices)
            try:
                print(f"[DEBUG] sample_rate truyền vào pyin: {sr}")
                print(f"[DEBUG] độ dài buffer audio (giây): {len(spk_audio)/sr:.2f}s")
                f0, _, _ = librosa.pyin(
                    spk_audio,
                    fmin=65,
                    fmax=300,
                    sr=sr,
                )
                valid_f0 = f0[~np.isnan(f0)]
                if len(valid_f0) > 0:
                    pitch_rep = np.percentile(valid_f0, 20)  # 20th percentile bền với nhiễu môi trường hơn median
                    pitch_map[spk] = round(float(pitch_rep), 1)
                else:
                    pitch_map[spk] = None
            except Exception as e:
                pitch_map[spk] = None

        return pitch_map

    finally:
        if tmp_wav and os.path.exists(tmp_wav):
            try:
                os.remove(tmp_wav)
            except OSError:
                pass


def assign_speaker_roles(
    speaker_segments: List[dict],
    pitch_map: dict,
) -> dict:
    """Phân loại vai trò cho từng speaker dựa trên tổng thời lượng và pitch.

    - Sắp xếp speaker theo tổng thời lượng GIẢM DẦN.
    - Speaker top 1 theo thời lượng luôn là 'main' (vô điều kiện).
    - Với các speaker còn lại:
      - nếu pitch_map[speaker] là None -> 'main' (fallback an toàn về giọng chính).
      - nếu pitch_map[speaker] <= MALE_PITCH_MAX (150Hz) -> 'male_secondary'.
      - nếu pitch_map[speaker] >= FEMALE_PITCH_MIN (170Hz) -> 'female_secondary'.
      - nếu nằm giữa (150Hz < pitch < 170Hz) -> 'main' (vùng xám, fallback an toàn).

    Returns:
        dict[str, str]: {"Người 1": "main", "Người 2": "female_secondary", ...}
    """
    speaker_durations = {}
    for s in speaker_segments:
        spk = s.get("speaker")
        if not spk:
            continue
        dur = max(0.0, s["end"] - s["start"])
        speaker_durations[spk] = speaker_durations.get(spk, 0.0) + dur

    if not speaker_durations:
        return {}

    sorted_speakers = sorted(
        speaker_durations.keys(),
        key=lambda k: speaker_durations[k],
        reverse=True
    )

    role_map = {}
    print("\n── Phân loại vai trò (Role Bucketing) ──")
    for idx, spk in enumerate(sorted_speakers):
        dur = speaker_durations[spk]
        p = pitch_map.get(spk)
        p_str = f"{p} Hz" if p is not None else "None (<1s hoặc không rõ)"

        if idx == 0:
            role = "main"
        else:
            if p is None:
                role = "main"
            elif p <= MALE_PITCH_MAX:
                role = "male_secondary"
            elif p >= FEMALE_PITCH_MIN:
                role = "female_secondary"
            else:
                # Vùng xám 150-170Hz: chưa đủ tin cậy để phân biệt -> fallback về main
                role = "main"

        role_map[spk] = role
        print(f"  {spk} | Tổng thời lượng: {dur:.1f}s | Pitch (20th pct): {p_str} | Vai trò: {role}")

    return role_map


# ──────────────────────────────────────────────────────────────
# MULTI-VOICE RESOLUTION & SPEAKER MERGING (TTS MAPPING)
# ──────────────────────────────────────────────────────────────
def parse_speaker_mapping(val: Optional[str]) -> dict:
    """Parse chuỗi CLI dạng 'Người 1:nam-namminh,Người 3:nam-namminh' thành dict."""
    if not val or not isinstance(val, str):
        return {}
    res = {}
    for item in val.split(","):
        item = item.strip()
        if not item or ":" not in item:
            continue
        k, v = item.split(":", 1)
        k = k.strip()
        v = v.strip()
        if k and v:
            res[k] = v
    return res


def load_role_map_from_debug_file(srt_path: str) -> dict:
    """Đọc role_map từ file <base>_diarization_debug.txt nếu có cạnh file .srt."""
    if not srt_path:
        return {}
    base, _ = os.path.splitext(srt_path)
    debug_path = f"{base}_diarization_debug.txt"
    if not os.path.exists(debug_path):
        return {}

    role_map = {}
    try:
        with open(debug_path, "r", encoding="utf-8") as f:
            in_roles = False
            for line in f:
                line_str = line.strip()
                if "=== PHÂN LOẠI VAI TRÒ (ROLE BUCKETING) ===" in line_str:
                    in_roles = True
                    continue
                if in_roles:
                    if line_str.startswith("===") or line_str.startswith("⚠"):
                        continue
                    m = re.match(r'^(Người\s*\d+)\s*\((main|male_secondary|female_secondary)\):', line_str)
                    if m:
                        role_map[m.group(1)] = m.group(2)
    except Exception:
        pass
    return role_map


def get_default_role_voice(role: str, default_voice: str, tts_engine: str = "edge") -> str:
    """Map role từ role bucketing sang giọng đọc mặc định theo engine."""
    if role == "main":
        return default_voice

    if tts_engine == "capcut":
        if role == "male_secondary":
            return "nam-tram"
        elif role == "female_secondary":
            return "co-gai"
        return default_voice

    if tts_engine == "piper":
        return default_voice

    # Mặc định: Edge-TTS
    if role == "male_secondary":
        return "nam-namminh"
    elif role == "female_secondary":
        return "nu-hoaimy"
    return default_voice


def resolve_speaker_voice(
    speaker_label: Optional[str],
    speaker_voices_map: Optional[dict] = None,
    merge_map: Optional[dict] = None,
    role_map: Optional[dict] = None,
    default_voice: str = "nu-hoaimy",
    tts_engine: str = "edge",
) -> str:
    """Giải quyết giọng đọc cho một dòng phụ đề dựa trên speaker_label.

    Nguyên tắc 4 bước:
    - Bước 1 - MERGE: nếu speaker_label có trong merge_map, thay speaker_label = merge_map[speaker_label].
      Chỉ ảnh hưởng tới việc chọn giọng ở bước cuối này, KHÔNG sửa speaker_label gốc.
    - Bước 2 - ƯU TIÊN CHỈ ĐỊNH TAY: nếu (speaker_label sau merge) có trong speaker_voices_map, dùng giọng đó ngay.
    - Bước 3 - FALLBACK ROLE BUCKETING: nếu không có chỉ định tay, tra role_map ('main'/'male_secondary'/'female_secondary'),
      map role sang giọng mặc định hợp lý theo engine.
    - Bước 4 - FALLBACK CUỐI: nếu không có speaker_label hoặc không match bất kỳ quy tắc nào, dùng default_voice.
    """
    if not speaker_label:
        return default_voice

    speaker_voices_map = speaker_voices_map or {}
    merge_map = merge_map or {}
    role_map = role_map or {}

    # Bước 1 - MERGE
    effective_speaker = merge_map.get(speaker_label, speaker_label)

    # Bước 2 - ƯU TIÊN CHỈ ĐỊNH TAY
    if effective_speaker in speaker_voices_map:
        return speaker_voices_map[effective_speaker]

    # Bước 3 - FALLBACK ROLE BUCKETING
    if effective_speaker in role_map:
        role = role_map[effective_speaker]
        return get_default_role_voice(role, default_voice, tts_engine=tts_engine)

    # Bước 4 - FALLBACK CUỐI
    return default_voice


def get_speaker_voice_details(
    target_speaker: str,
    speaker_voices_map: Optional[dict],
    role_map: Optional[dict],
    default_voice: str,
    tts_engine: str = "edge",
) -> tuple:
    """Trả về (voice_name, reason) cho target_speaker."""
    speaker_voices_map = speaker_voices_map or {}
    role_map = role_map or {}

    if target_speaker in speaker_voices_map:
        return speaker_voices_map[target_speaker], "chỉ định tay"
    if target_speaker in role_map:
        role = role_map[target_speaker]
        voice = get_default_role_voice(role, default_voice, tts_engine=tts_engine)
        return voice, f"role: {role}, mặc định"
    return default_voice, "mặc định"


def print_speaker_voice_summary(
    original_speakers: List[str],
    speaker_voices_map: Optional[dict] = None,
    merge_map: Optional[dict] = None,
    role_map: Optional[dict] = None,
    default_voice: str = "nu-hoaimy",
    tts_engine: str = "edge",
):
    """In bảng tổng kết giọng đọc đã dùng cho từng speaker ở cuối job dub."""
    speaker_voices_map = speaker_voices_map or {}
    merge_map = merge_map or {}
    role_map = role_map or {}

    # Tìm tập hợp các target speakers theo thứ tự tự nhiên (Người 1, Người 2...)
    target_to_merged = {}
    all_targets = set()
    for spk in original_speakers:
        target = merge_map.get(spk, spk)
        all_targets.add(target)
        if target != spk:
            if target not in target_to_merged:
                target_to_merged[target] = []
            if spk not in target_to_merged[target]:
                target_to_merged[target].append(spk)

    def _sort_key(s):
        m = re.search(r'\d+', s)
        return int(m.group(0)) if m else 9999

    sorted_targets = sorted(all_targets, key=_sort_key)

    print("\n=== TÓM TẮT GIỌNG ĐÃ DÙNG ===")
    for tgt in sorted_targets:
        merged_sources = target_to_merged.get(tgt, [])
        if merged_sources:
            merge_str = ", ".join(f"{src} → {tgt}" for src in merged_sources)
            header = f"{tgt} (merged: {merge_str})"
        else:
            header = tgt

        voice, reason = get_speaker_voice_details(tgt, speaker_voices_map, role_map, default_voice, tts_engine)
        print(f"{header} → {voice} ({reason})")
    print()


# ──────────────────────────────────────────────────────────────
# MATCH SPEAKER VỚI TỪNG CÂU PHỤ ĐỀ
# ──────────────────────────────────────────────────────────────
def match_speaker_to_subtitle(
    sub_start: float,
    sub_end: float,
    speaker_segments: List[dict],
) -> dict:
    """Tính overlap giữa 1 câu phụ đề và các speaker segment, trả về speaker thắng.

    Returns:
        {"speaker": str|None, "confidence": float, "status": "CONFIDENT"/"UNCERTAIN"/"UNKNOWN"}
    """
    sub_duration = sub_end - sub_start
    if sub_duration <= 0:
        return {"speaker": None, "confidence": 0.0, "status": "UNKNOWN"}

    # Cộng dồn overlap_duration theo từng speaker
    overlap_by_speaker = {}
    for seg in speaker_segments:
        # Tính phần giao [max(sub_start, seg_start), min(sub_end, seg_end)]
        overlap_start = max(sub_start, seg["start"])
        overlap_end = min(sub_end, seg["end"])
        overlap_duration = max(0.0, overlap_end - overlap_start)

        if overlap_duration > 0:
            spk = seg["speaker"]
            overlap_by_speaker[spk] = overlap_by_speaker.get(spk, 0.0) + overlap_duration

    if not overlap_by_speaker:
        return {"speaker": None, "confidence": 0.0, "status": "UNKNOWN"}

    # Chọn speaker có overlap cao nhất
    best_speaker = max(overlap_by_speaker, key=overlap_by_speaker.get)
    best_overlap = overlap_by_speaker[best_speaker]
    overlap_ratio = best_overlap / sub_duration

    # Kiểm tra xem có người nói khác cùng xuất hiện trong câu không (nghi vấn gộp nhiều người vào 1 câu)
    competing = [
        f"{s} ({dur/sub_duration:.0%})"
        for s, dur in overlap_by_speaker.items()
        if s != best_speaker and (dur / sub_duration) >= 0.15
    ]

    # Phân loại
    if overlap_ratio >= CONFIDENT_THRESHOLD:
        status = "CONFIDENT"
    elif overlap_ratio >= UNCERTAIN_THRESHOLD:
        status = "UNCERTAIN"
    else:
        status = "UNKNOWN"

    # Nếu UNKNOWN, không đoán bừa
    if status == "UNKNOWN":
        return {"speaker": None, "confidence": overlap_ratio, "status": "UNKNOWN", "competing": competing}

    return {
        "speaker": best_speaker,
        "confidence": overlap_ratio,
        "status": status,
        "competing": competing,
    }


def postprocess_speaker_matches(
    speaker_info_list: List[dict],
    speaker_segments: List[dict],
) -> List[dict]:
    """Hậu xử lý kết quả match speaker:
    - Nếu toàn video chỉ phát hiện đúng 1 speaker duy nhất, về mặt logic mọi câu thoại
      đều thuộc về người đó (kể cả các câu UNKNOWN do lệch VAD giữa Whisper và pyannote).
      Tự động gán toàn bộ câu UNKNOWN về speaker duy nhất này với status CONFIDENT.
    """
    unique_speakers = list(dict.fromkeys(s["speaker"] for s in speaker_segments if s.get("speaker")))
    if len(unique_speakers) == 1:
        only_spk = unique_speakers[0]
        for info in speaker_info_list:
            if info["status"] == "UNKNOWN" or info.get("speaker") is None:
                info["speaker"] = only_spk
                info["status"] = "CONFIDENT"
                info["fallback_single_speaker"] = True
    return speaker_info_list


# ──────────────────────────────────────────────────────────────
# EXPORT SRT VỚI SPEAKER TAG — ĐIỂM DUY NHẤT GHÉP TAG VÀO TEXT
# ──────────────────────────────────────────────────────────────
def export_srt_with_speaker_tags(
    subs,
    speaker_info_list: List[dict],
    output_path: str,
    role_map: Optional[dict] = None,
):
    """Ghi file .srt với tag [Người X] gắn vào content.

    Đây là điểm DUY NHẤT trong toàn bộ pipeline được phép ghép tag vào text.
    Mọi nơi khác (translate, tts, gui) phải dùng strip_speaker_tag() từ utils.py.

    Args:
        subs: list[srt.Subtitle] — phụ đề gốc (content KHÔNG có tag)
        speaker_info_list: list[dict] — kết quả từ match_speaker_to_subtitle cho mỗi sub
        output_path: đường dẫn file .srt đầu ra
        role_map: dict[str, str] — phân loại vai trò (tùy chọn, để dành cho bước dub)
    """
    import srt

    tagged_subs = []
    for sub, info in zip(subs, speaker_info_list):
        text = sub.content
        status = info["status"]
        speaker = info["speaker"]

        if status == "CONFIDENT":
            tagged_content = f"[{speaker}] {text}"
        elif status == "UNCERTAIN":
            tagged_content = f"[{speaker}] {text} [⚠ SPEAKER KHÔNG CHẮC]"
        else:  # UNKNOWN
            tagged_content = f"[?] {text}"

        tagged_subs.append(srt.Subtitle(
            index=sub.index,
            start=sub.start,
            end=sub.end,
            content=tagged_content,
        ))

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(srt.compose(tagged_subs))


# ──────────────────────────────────────────────────────────────
# DEBUG REPORT
# ──────────────────────────────────────────────────────────────
def _format_time(seconds: float) -> str:
    """Format float seconds thành HH:MM:SS.cc"""
    td = timedelta(seconds=seconds)
    total_secs = int(td.total_seconds())
    h = total_secs // 3600
    m = (total_secs % 3600) // 60
    s = total_secs % 60
    cs = int((seconds - int(seconds)) * 100)
    return f"{h:02d}:{m:02d}:{s:02d}.{cs:02d}"


def write_diarization_debug_report(
    output_path: str,
    speaker_segments: List[dict],
    speaker_info_list: List[dict],
    subs,
    role_map: Optional[dict] = None,
    pitch_map: Optional[dict] = None,
):
    """Ghi file debug report chi tiết cho diarization.

    File output: <output>_diarization_debug.txt
    """
    base, ext = os.path.splitext(output_path)
    debug_path = f"{base}_diarization_debug.txt"

    # Thống kê
    total = len(speaker_info_list)
    n_confident = sum(1 for i in speaker_info_list if i["status"] == "CONFIDENT")
    n_uncertain = sum(1 for i in speaker_info_list if i["status"] == "UNCERTAIN")
    n_unknown = sum(1 for i in speaker_info_list if i["status"] == "UNKNOWN")

    # Tìm danh sách speaker duy nhất
    unique_speakers = []
    seen = set()
    for seg in speaker_segments:
        if seg["speaker"] not in seen:
            unique_speakers.append(seg["speaker"])
            seen.add(seg["speaker"])

    lines = []
    lines.append("=== SPEAKER DIARIZATION DEBUG ===")
    lines.append(f"Phát hiện: {len(unique_speakers)} người nói")
    lines.append("")

    # Liệt kê các đoạn của từng speaker
    for spk in unique_speakers:
        lines.append(f"{spk}:")
        for seg in speaker_segments:
            if seg["speaker"] == spk:
                lines.append(f"  {_format_time(seg['start'])} → {_format_time(seg['end'])}")
        lines.append("")

    # Chi tiết từng subtitle
    for sub, info in zip(subs, speaker_info_list):
        sub_start = sub.start.total_seconds()
        sub_end = sub.end.total_seconds()
        sub_duration = sub_end - sub_start
        status = info["status"]
        confidence = info["confidence"]
        speaker = info["speaker"]

        if status == "CONFIDENT":
            icon = "🟢 CONFIDENT"
        elif status == "UNCERTAIN":
            icon = "🟡 UNCERTAIN"
        else:
            icon = "🔴 UNKNOWN"

        overlap_secs = confidence * sub_duration

        lines.append(
            f"Subtitle #{sub.index}: "
            f"{_format_time(sub_start)} → {_format_time(sub_end)} "
            f"[{icon}]"
        )

        if info.get("fallback_single_speaker"):
            lines.append(
                f"  → {speaker} [Tự động gán: toàn video chỉ có đúng 1 người nói "
                f"(overlap VAD gốc: {confidence:.0%})]"
            )
        elif status == "UNKNOWN":
            if confidence > 0:
                lines.append(
                    f"  → không xác định "
                    f"(overlap cao nhất chỉ {confidence:.0%}, "
                    f"dưới ngưỡng {UNCERTAIN_THRESHOLD:.0%})"
                )
            else:
                lines.append("  → không xác định (không có overlap nào)")
        else:
            lines.append(
                f"  → {speaker} "
                f"(overlap: {overlap_secs:.2f}s/{sub_duration:.2f}s = {confidence:.0%})"
            )
        if info.get("competing"):
            lines.append(f"  ⚠ Cảnh báo nghi vấn gộp giọng: có thêm {', '.join(info['competing'])}")
        lines.append("")

    # Dòng tổng kết cuối
    def _pct(n):
        return f"{n / total * 100:.0f}%" if total > 0 else "0%"

    lines.append(
        f"Tổng: {total} câu | "
        f"🟢 CONFIDENT: {n_confident} ({_pct(n_confident)}) | "
        f"🟡 UNCERTAIN: {n_uncertain} ({_pct(n_uncertain)}) | "
        f"🔴 UNKNOWN: {n_unknown} ({_pct(n_unknown)})"
    )

    # Mục phân loại vai trò (Role Bucketing)
    if role_map:
        lines.append("")
        lines.append("=== PHÂN LOẠI VAI TRÒ (ROLE BUCKETING) ===")
        lines.append(f"(Ngưỡng: pitch <= {int(MALE_PITCH_MAX)}Hz → nam phụ | pitch >= {int(FEMALE_PITCH_MIN)}Hz → nữ phụ | {int(MALE_PITCH_MAX)}-{int(FEMALE_PITCH_MIN)}Hz → vùng xám, gộp về giọng chính)")
        speaker_durations = {}
        for s in speaker_segments:
            spk = s.get("speaker")
            if spk:
                dur = max(0.0, s["end"] - s["start"])
                speaker_durations[spk] = speaker_durations.get(spk, 0.0) + dur

        total_spk_dur = sum(speaker_durations.values()) or 1.0

        sorted_spks = sorted(
            role_map.keys(),
            key=lambda k: speaker_durations.get(k, 0.0),
            reverse=True
        )

        for spk in sorted_spks:
            role = role_map[spk]
            dur = speaker_durations.get(spk, 0.0)
            pct = dur / total_spk_dur * 100
            p = pitch_map.get(spk) if pitch_map else None
            p_str = f"{p:.0f} Hz" if p is not None else "None (<1s hoặc không rõ)"
            lines.append(f"{spk} ({role}): {dur:.0f}s nói ({pct:.0f}%) | Pitch: {p_str}")

        lines.append("")
        lines.append("⚠ Lưu ý: nếu video có 2+ người thật cùng giới tính phụ, họ sẽ dùng chung 1 giọng lồng tiếng")

    os.makedirs(os.path.dirname(os.path.abspath(debug_path)), exist_ok=True)
    with open(debug_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"  Debug report: {debug_path}")


# ──────────────────────────────────────────────────────────────
# CONSOLE SUMMARY + KHUYẾN NGHỊ
# ──────────────────────────────────────────────────────────────
def print_diarization_summary(speaker_info_list: List[dict]):
    """In dòng tổng kết + khuyến nghị ra console."""
    total = len(speaker_info_list)
    if total == 0:
        print("  Không có câu phụ đề nào để đánh giá diarization.")
        return

    n_confident = sum(1 for i in speaker_info_list if i["status"] == "CONFIDENT")
    n_uncertain = sum(1 for i in speaker_info_list if i["status"] == "UNCERTAIN")
    n_unknown = sum(1 for i in speaker_info_list if i["status"] == "UNKNOWN")

    usable = n_confident + n_uncertain
    usable_ratio = usable / total

    def _pct(n):
        return f"{n / total * 100:.0f}%"

    print(
        f"  Tổng: {total} câu | "
        f"🟢 CONFIDENT: {n_confident} ({_pct(n_confident)}) | "
        f"🟡 UNCERTAIN: {n_uncertain} ({_pct(n_uncertain)}) | "
        f"🔴 UNKNOWN: {n_unknown} ({_pct(n_unknown)})"
    )

    n_single_fallback = sum(1 for i in speaker_info_list if i.get("fallback_single_speaker"))
    if n_single_fallback > 0:
        print(f"  ℹ Đã tự động gán {n_single_fallback} câu UNKNOWN về người nói duy nhất (video đơn giọng).")

    multi_count = sum(1 for i in speaker_info_list if i.get("competing"))
    if multi_count > 0:
        print(f"  ⚠ Chú ý: Có {multi_count} câu bị nghi vấn gộp nhiều người nói vào 1 câu.")

    if usable_ratio >= 0.90:
        print("  ✔ Diarization đủ tin cậy, có thể cân nhắc lồng tiếng đa giọng.")
    elif usable_ratio >= 0.75:
        print(
            "  ⚠ Diarization còn nhiều câu chưa chắc — nên xem lại "
            "*_diarization_debug.txt trước khi dùng multi-voice."
        )
    else:
        print(
            "  ✘ Diarization chưa đủ tin cậy cho video này — khuyến nghị dùng "
            "1 giọng chung, chưa nên làm multi-voice."
        )
