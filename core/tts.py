"""
TTS ENGINES (EDGE-TTS, PIPER, CAPCUT) VÀ DANH SÁCH GIỌNG ĐỌC
"""

import asyncio
import json
import os
from pathlib import Path
import shutil
import sys
import time
import wave
import edge_tts
from pydub import AudioSegment
from tqdm import tqdm

from .config import (
    VIETNAMESE_VOICES,
    DEFAULT_VOICE,
    PIPER_VIETNAMESE_VOICES,
    DEFAULT_PIPER_VOICE,
    _piper_voice_cache,
    PIPER_NGHITTS_VOICES,
    _NGHITTS_BASE_URL,
    CAPCUT_TTS_API_BASE,
    CAPCUT_VIETNAMESE_VOICES,
    DEFAULT_CAPCUT_VOICE,
    POPULAR_VOICES,
)
from .utils import _cache_key, _download_with_progress


async def _tts_to_file(text: str, voice: str, out_path: str, rate: str = "+0%"):
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(out_path)


def _capcut_tts_to_file(text: str, voice: str, out_path: str,
                         rate: float = 1.0, max_retries: int = 5):
    """Sinh giọng đọc qua CapCut TTS."""
    import urllib.request as _ureq
    import urllib.error as _uerr

    api_url = CAPCUT_TTS_API_BASE.rstrip("/") + "/api/tts"
    payload = json.dumps({"text": text, "voice": voice, "rate": rate}).encode("utf-8")
    last_err = None

    for attempt in range(1, max_retries + 1):
        try:
            req = _ureq.Request(
                api_url, data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with _ureq.urlopen(req, timeout=90) as resp:
                result = json.loads(resp.read().decode("utf-8"))

            speech_url = result.get("speech_url")
            if not speech_url:
                raise RuntimeError(f"Không có speech_url trong response: {result}")

            _ureq.urlretrieve(speech_url, out_path)

            # Áp dụng tốc độ đọc thực tế bằng FFmpeg atempo nếu rate != 1.0
            if abs(rate - 1.0) > 0.01:
                from .utils import run
                clamped_rate = max(0.5, min(2.0, rate))
                tmp_spd = out_path + ".spd.mp3"
                run(["ffmpeg", "-y", "-i", out_path, "-filter:a", f"atempo={clamped_rate:.2f}", tmp_spd])
                if os.path.exists(tmp_spd) and os.path.getsize(tmp_spd) > 0:
                    shutil.move(tmp_spd, out_path)
            return

        except (_uerr.URLError, OSError, RuntimeError) as e:
            last_err = e
            if attempt < max_retries:
                wait = min(5 * attempt, 30)
                tqdm.write(f"  ⚠ CapCut TTS lần {attempt}/{max_retries}: {e}")
                if attempt == 1:
                    tqdm.write("    (Space HuggingFace có thể đang cold-start — "
                               "chờ ~30s rồi tự thử lại, bình thường ở lần đầu dùng)")
                tqdm.write(f"    Thử lại sau {wait}s...")
                time.sleep(wait)

    raise RuntimeError(
        f"CapCut TTS thất bại sau {max_retries} lần thử.\n"
        f"  Lỗi cuối: {last_err}\n"
        f"  Kiểm tra kết nối mạng hoặc Space có còn online không:\n"
        f"  {CAPCUT_TTS_API_BASE}"
    )


def _get_piper_voices_dir(custom_dir=None) -> str:
    d = custom_dir or os.path.join(os.path.expanduser("~"), ".cache", "piper_voices")
    os.makedirs(d, exist_ok=True)
    return d


def _download_nghitts_voice(voice_name: str, model_path: str, config_path: str):
    """Tải 1 giọng từ bộ mở rộng 'nghitts' (doof-ferb/nghitts-copy)."""
    print(f"→ Chưa có giọng '{voice_name}' (bộ mở rộng nghitts) trên máy, đang tải về "
          f"(~63MB, chỉ cần tải 1 lần duy nhất)...")
    try:
        _download_with_progress(f"{_NGHITTS_BASE_URL}/{voice_name}.onnx?download=true",
                                 model_path, f"Đang tải {voice_name}.onnx")
        shared_config = os.path.join(os.path.dirname(config_path), "_nghitts_shared_config.json")
        if not os.path.exists(shared_config):
            _download_with_progress(f"{_NGHITTS_BASE_URL}/config.json?download=true",
                                     shared_config, "Đang tải config.json dùng chung")
        shutil.copy(shared_config, config_path)
    except Exception as e:
        print(f"✘ Tải giọng '{voice_name}' thất bại: {e}")
        print("  Kiểm tra lại kết nối mạng, hoặc HuggingFace có thể đang chặn/giới hạn khu vực bạn.")
        for p in (model_path, config_path):
            if os.path.exists(p):
                os.remove(p)
        raise RuntimeError(f"Tải giọng nghitts '{voice_name}' thất bại: {e}") from e
    print(f"✔ Đã tải xong giọng '{voice_name}' vào: {os.path.dirname(model_path)}")


def _resolve_piper_voice_files(voice_arg: str, voices_dir: str):
    """Trả về (model_path, config_path) cho 1 giọng Piper — TỰ ĐỘNG TẢI VỀ nếu chưa có."""
    is_nghitts = voice_arg in PIPER_NGHITTS_VOICES
    voice_code = voice_arg if is_nghitts else PIPER_VIETNAMESE_VOICES.get(voice_arg, voice_arg)
    model_path = os.path.join(voices_dir, f"{voice_code}.onnx")
    config_path = os.path.join(voices_dir, f"{voice_code}.onnx.json")

    if not (os.path.exists(model_path) and os.path.exists(config_path)):
        if is_nghitts:
            _download_nghitts_voice(voice_code, model_path, config_path)
            return model_path, config_path

        print(f"→ Chưa có giọng Piper '{voice_code}' trên máy, đang tải về "
              f"(chỉ cần tải 1 lần duy nhất, khoảng vài chục MB)...")
        try:
            from piper.download_voices import download_voice
        except ImportError:
            print("✘ Thiếu thư viện piper-tts. Cài bằng: pip install piper-tts")
            raise RuntimeError("Thiếu thư viện piper-tts. Cài bằng: pip install piper-tts")
        try:
            download_voice(voice_code, Path(voices_dir))
        except Exception as e:
            print(f"✘ Tải giọng Piper '{voice_code}' thất bại: {e}")
            raise RuntimeError(f"Tải giọng Piper '{voice_code}' thất bại: {e}") from e
        print(f"✔ Đã tải xong giọng '{voice_code}' vào: {voices_dir}")

    return model_path, config_path


def _get_piper_voice(voice_arg: str, voices_dir: str):
    """Load model Piper (ONNX)."""
    model_path, config_path = _resolve_piper_voice_files(voice_arg, voices_dir)
    if model_path not in _piper_voice_cache:
        try:
            from piper import PiperVoice
        except ImportError:
            print("✘ Thiếu thư viện piper-tts. Cài bằng: pip install piper-tts")
            raise RuntimeError("Thiếu thư viện piper-tts. Cài bằng: pip install piper-tts")
        _piper_voice_cache[model_path] = PiperVoice.load(model_path, config_path=config_path)
    return _piper_voice_cache[model_path]


def _piper_tts_to_file(text: str, voice_arg: str, voices_dir: str, out_path: str,
                        length_scale: float = 1.0):
    """Sinh giọng đọc OFFLINE bằng Piper."""
    from piper import SynthesisConfig
    voice = _get_piper_voice(voice_arg, voices_dir)
    syn_config = SynthesisConfig(length_scale=length_scale)
    with wave.open(out_path, "wb") as wav_file:
        voice.synthesize_wav(text, wav_file, syn_config)


def synthesize_line_to_file(text, voice, tmp_dir, i, rate="+0%",
                            cache_dir=None, use_cache=True, max_retries=4, delay=0.3,
                            tts_engine="edge", piper_voices_dir=None,
                            capcut_rate=1.0) -> str:
    """
    Sinh giọng đọc AI và lưu vào file. Trả về đường dẫn file audio.
    KHÔNG sys.exit(), trả RuntimeError nếu gặp lỗi để ThreadPool handle.
    """
    ext = "wav" if tts_engine == "piper" else "mp3"
    rate_suffix = f":r{capcut_rate:.2f}" if (tts_engine == "capcut" and abs(capcut_rate - 1.0) > 0.01) else ""
    cache_voice_key = f"{tts_engine}:{voice}{rate_suffix}"
    cache_path = os.path.join(cache_dir, f"{_cache_key(text, cache_voice_key)}.{ext}") if cache_dir else None

    if use_cache and cache_path and os.path.exists(cache_path):
        return cache_path

    out_path = os.path.join(tmp_dir, f"line_{i:04d}.{ext}")

    if tts_engine == "piper":
        try:
            piper_voices_dir = piper_voices_dir or _get_piper_voices_dir()
            _piper_tts_to_file(text, voice, piper_voices_dir, out_path)
        except Exception as e:
            raise RuntimeError(f"Lỗi sinh giọng Piper cho câu #{i} '{text[:80]}': {e}") from e
        if use_cache and cache_path:
            shutil.copy(out_path, cache_path)
        if delay > 0:
            time.sleep(delay)
        return out_path

    if tts_engine == "capcut":
        try:
            # _capcut_tts_to_file retries 5 times internally
            _capcut_tts_to_file(text, voice, out_path, rate=capcut_rate)
        except Exception as e:
            raise RuntimeError(f"Lỗi sinh giọng CapCut cho câu #{i} '{text[:80]}': {e}") from e
        if use_cache and cache_path:
            shutil.copy(out_path, cache_path)
        if delay > 0:
            time.sleep(delay)
        return out_path

    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            asyncio.run(_tts_to_file(text, voice, out_path, rate))
            last_err = None
            break
        except Exception as e:
            last_err = e
            if attempt < max_retries:
                wait = min(2 ** attempt, 20)
                time.sleep(wait)

    if last_err is not None:
        raise RuntimeError(f"Lỗi Edge-TTS cho câu #{i} '{text[:80]}' sau {max_retries} lần thử: {last_err}") from last_err

    if use_cache and cache_path:
        shutil.copy(out_path, cache_path)

    if delay > 0:
        time.sleep(delay)

    return out_path


def synthesize_line(text, voice, tmp_dir, i, rate="+0%",
                     cache_dir=None, use_cache=True, max_retries=4, delay=0.3,
                     tts_engine="edge", piper_voices_dir=None,
                     capcut_rate=1.0):
    """Hàm wrapper tương thích ngược: trả về AudioSegment."""
    out_path = synthesize_line_to_file(
        text=text, voice=voice, tmp_dir=tmp_dir, i=i, rate=rate,
        cache_dir=cache_dir, use_cache=use_cache, max_retries=max_retries,
        delay=delay, tts_engine=tts_engine, piper_voices_dir=piper_voices_dir,
        capcut_rate=capcut_rate
    )
    return AudioSegment.from_file(out_path)


def generate_voice_preview(tts_engine: str, voice_arg: str, out_wav_path: str, capcut_rate: float = 1.0):
    """
    Sinh 1 câu mẫu tiếng Việt cho engine + voice đang chọn và lưu thành file .wav tại out_wav_path.
    """
    import tempfile
    if tts_engine == "piper":
        voice = PIPER_VIETNAMESE_VOICES.get(voice_arg, voice_arg)
    elif tts_engine == "capcut":
        voice = CAPCUT_VIETNAMESE_VOICES.get(voice_arg, voice_arg)
    else:
        voice = VIETNAMESE_VOICES.get(voice_arg, voice_arg)

    sample_text = "Xin chào, đây là giọng đọc mẫu"
    tmp_dir = tempfile.gettempdir()

    out_file = synthesize_line_to_file(
        text=sample_text,
        voice=voice,
        tmp_dir=tmp_dir,
        i=9999,
        tts_engine=tts_engine,
        capcut_rate=capcut_rate,
        use_cache=False
    )

    if not out_file.endswith(".wav"):
        seg = AudioSegment.from_file(out_file)
        seg.export(out_wav_path, format="wav")
        try:
            os.remove(out_file)
        except Exception:
            pass
    elif out_file != out_wav_path:
        shutil.move(out_file, out_wav_path)



def cmd_voices(args):
    print("═══ Engine 'edge' (mặc định, cần mạng) ═══\n")
    print("Giọng tắt (dùng thẳng, không cần gõ dài):")
    for key, val in VIETNAMESE_VOICES.items():
        print(f"  --voice {key:15s} -> {val}")

    print("\nMột số giọng phổ biến khác (dùng --voice <mã-giọng>, ví dụ --voice en-US-GuyNeural):")
    for lang, voices in POPULAR_VOICES.items():
        print(f"  {lang}:")
        for v in voices:
            print(f"    {v}")

    print("\nEdge TTS có hàng trăm giọng, đủ ngôn ngữ. Xem TOÀN BỘ danh sách bằng:")
    print("  edge-tts --list-voices")
    print("  edge-tts --list-voices | grep vi-VN     # chỉ lọc giọng tiếng Việt")
    print("\n--voice nhận bất kỳ mã giọng nào ở trên (VD: --voice vi-VN-HoaiMyNeural),")
    print("không bắt buộc phải là 'nu-hoaimy' / 'nam-namminh'.")

    print("\n\n═══ Engine 'piper' (--tts-engine piper, chạy OFFLINE) ═══\n")
    print("Giọng chính thức (kho rhasspy/piper-voices):")
    for key, val in PIPER_VIETNAMESE_VOICES.items():
        star = " (khuyên dùng)" if key == DEFAULT_PIPER_VOICE else ""
        print(f"  --voice {key:15s} -> {val}{star}")

    print(f"\nGiọng mở rộng — {len(PIPER_NGHITTS_VOICES)} giọng nam/nữ đa dạng hơn, cùng nguồn HuggingFace")
    print("'doof-ferb/nghitts-copy' (không nằm trong kho Piper chính thức, tự tải riêng):")
    for name in sorted(PIPER_NGHITTS_VOICES):
        print(f"  --voice {name}")

    print("\nModel tự động tải về lần đầu dùng (~vài chục-60MB/giọng), các lần sau")
    print("chạy offline hoàn toàn — không phụ thuộc mạng/rate-limit như edge-tts.")
    print("Xem thêm giọng ngôn ngữ khác tại: https://github.com/rhasspy/piper/blob/master/VOICES.md")

    print("\n")
    print("=" * 55)
    print(" Engine 'capcut' (--tts-engine capcut, nhieu giong, can mang)")
    print("=" * 55)
    print(f"\nAPI: {CAPCUT_TTS_API_BASE}")
    print("Giong tieng Viet co alias ngan (khuyen dung):")
    _capcut_list = None
    try:
        import urllib.request as _ureq
        with _ureq.urlopen(CAPCUT_TTS_API_BASE.rstrip("/") + "/api/voices", timeout=10) as _r:
            _capcut_list = json.loads(_r.read().decode("utf-8"))
    except Exception:
        pass
    _capcut_names = {}
    if _capcut_list:
        for _v in _capcut_list:
            _capcut_names[_v.get("voice_type", "")] = _v.get("display_name", "")
    for alias, vtype in CAPCUT_VIETNAMESE_VOICES.items():
        star = " (mac dinh)" if alias == DEFAULT_CAPCUT_VOICE else ""
        dname = _capcut_names.get(vtype, "")
        dname_str = f" [{dname}]" if dname else ""
        print(f"  --voice {alias:20s} -> {vtype}{dname_str}{star}")
    if _capcut_list:
        vi_voices = [v for v in _capcut_list if v.get("lang", "").startswith("vi")]
        aliases_used = set(CAPCUT_VIETNAMESE_VOICES.values())
        extra = [v for v in vi_voices if v.get("voice_type") not in aliases_used]
        if extra:
            print("\nGiong tieng Viet khac (dung voice_type truc tiep):")
            for v in extra:
                print(f"  --voice {v['voice_type']:50s}  [{v['display_name']}]")
        print(f"\n(Da lay danh sach tu API - tong {len(vi_voices)} giong tieng Viet)")
    else:
        print("\n(Khong lay duoc danh sach tu API - kiem tra internet hoac Space con online)")
        print(f"  URL Space: {CAPCUT_TTS_API_BASE}")
    print("\nLuu y:")
    print("  * Space HuggingFace free tier co the sleep - lan dau dung cho ~30s (cold-start).")
    print("  * Dung alias ngan (VD: --voice co-gai) hoac voice_type day du deu duoc.")
    print("  * Doi server: dat bien moi truong CAPCUT_TTS_URL=https://your-server")
    print("  * Khong can cai them thu vien, chi can internet.")

    async def _list_live():
        try:
            voices = await edge_tts.list_voices()
            vi = [v for v in voices if v["Locale"].startswith("vi-")]
            if vi:
                print("\n(Danh sach giong vi-VN lay truc tiep tu server, can internet):")
                for v in vi:
                    print(f"  {v['ShortName']} ({v['Gender']})")
        except Exception:
            pass

    try:
        asyncio.run(_list_live())
    except Exception:
        pass
