"""
CORE PACKAGE FOR VIETSUB DUB TOOL
"""

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
    WHISPER_PRESETS,
    _QUOTA_SIGNALS,
    MIN_GAP_MS,
    MAX_START_SHIFT_MS,
    MIX_PRESETS,
)

from .utils import (
    run,
    get_video_duration,
    _safe_blur_radius,
    _escape_ffmpeg_path,
    get_video_duration_seconds,
    get_video_dimensions,
    is_video_hdr,
    td_to_ms,
    _looks_non_vietnamese,
    _cache_key,
    get_cache_dir,
    _download_with_progress,
    _to_ass_color,
)

from .transcribe import (
    _detect_cuda_available,
    _resolve_whisper_device,
    _resolve_whisper_compute_type,
    _resolve_whisper_settings,
    _find_and_register_cuda_dlls,
    cmd_transcribe,
)

from .translate import (
    _get_gemini_client,
    _get_groq_api_key,
    _is_quota_error,
    check_gemini_quota,
    check_groq_quota,
    cmd_check_quota,
    _checkpoint_path,
    _load_checkpoint,
    _save_checkpoint,
    _build_translate_prompt,
    _call_gemini_translate,
    _call_groq_translate,
    _write_partial_srt,
    cmd_translate,
)

from .tts import (
    _tts_to_file,
    _capcut_tts_to_file,
    _get_piper_voices_dir,
    _download_nghitts_voice,
    _resolve_piper_voice_files,
    _get_piper_voice,
    _piper_tts_to_file,
    synthesize_line_to_file,
    synthesize_line,
    cmd_voices,
)

from .dubbing import (
    _trim_silence,
    analyze_speech_rate,
    calculate_available_timeline,
    calculate_required_speed,
    fit_tts_to_timeline,
    _overlay_extend,
    _print_dub_timing_report,
    validate_dub_timeline,
    _print_timeline_propagation_report,
    build_dubbed_audio,
    cmd_dub,
)

from .burning import (
    cmd_template,
    _srt_to_positioned_ass,
    _burn_mask_preview,
    cmd_burn,
)

from .pipeline import (
    cmd_all,
    cmd_auto,
)

from .ocr_extractor import (
    extract_hardsub_from_video,
    cmd_ocr,
)

from .downloader import (
    extract_url,
    sanitize_filename,
    download_clean_video,
    cmd_download,
)

from .cli import (
    build_parser,
    main,
)

__all__ = [
    # Downloader
    "extract_url", "sanitize_filename", "download_clean_video", "cmd_download",
    # Config
    "VIETNAMESE_VOICES", "DEFAULT_VOICE", "PIPER_VIETNAMESE_VOICES", "DEFAULT_PIPER_VOICE",
    "_piper_voice_cache", "PIPER_NGHITTS_VOICES", "_NGHITTS_BASE_URL", "CAPCUT_TTS_API_BASE",
    "CAPCUT_VIETNAMESE_VOICES", "DEFAULT_CAPCUT_VOICE", "POPULAR_VOICES", "WHISPER_PRESETS",
    "_QUOTA_SIGNALS", "MIN_GAP_MS", "MAX_START_SHIFT_MS", "MIX_PRESETS",
    # Utils
    "run", "get_video_duration", "_safe_blur_radius", "_escape_ffmpeg_path",
    "get_video_duration_seconds", "get_video_dimensions", "is_video_hdr", "td_to_ms",
    "_looks_non_vietnamese", "_cache_key", "get_cache_dir", "_download_with_progress", "_to_ass_color",
    # Transcribe
    "_detect_cuda_available", "_resolve_whisper_device", "_resolve_whisper_compute_type",
    "_resolve_whisper_settings", "_find_and_register_cuda_dlls", "cmd_transcribe",
    # Translate
    "_get_gemini_client", "_is_quota_error", "check_gemini_quota", "cmd_check_quota", "_checkpoint_path", "_load_checkpoint",
    "_save_checkpoint", "_build_translate_prompt", "_call_gemini_translate", "_write_partial_srt", "cmd_translate",
    # TTS
    "_tts_to_file", "_capcut_tts_to_file", "_get_piper_voices_dir", "_download_nghitts_voice",
    "_resolve_piper_voice_files", "_get_piper_voice", "_piper_tts_to_file", "synthesize_line", "cmd_voices",
    # Dubbing
    "_trim_silence", "analyze_speech_rate", "calculate_available_timeline", "calculate_required_speed",
    "fit_tts_to_timeline", "_overlay_extend", "_print_dub_timing_report", "validate_dub_timeline",
    "_print_timeline_propagation_report", "build_dubbed_audio", "cmd_dub",
    # Burning
    "cmd_template", "_srt_to_positioned_ass", "_burn_mask_preview", "cmd_burn",
    # Pipeline
    "cmd_all", "cmd_auto",
    # OCR
    "extract_hardsub_from_video", "cmd_ocr",
    # CLI
    "build_parser", "main",
]
