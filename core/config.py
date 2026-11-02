"""
CẤU HÌNH VÀ HẰNG SỐ CỦA DUB TOOL
"""

import os

# Edge-TTS voices
VIETNAMESE_VOICES = {
    "nu-hoaimy": "vi-VN-HoaiMyNeural",     # giọng nữ, tự nhiên
    "nam-namminh": "vi-VN-NamMinhNeural",  # giọng nam
}
DEFAULT_VOICE = VIETNAMESE_VOICES["nu-hoaimy"]

# Giọng Piper tiếng Việt (OFFLINE)
PIPER_VIETNAMESE_VOICES = {
    "vi-vais1000": "vi_VN-vais1000-medium",     # khuyên dùng — chất lượng tốt nhất trong kho chính thức
    "vi-25hours": "vi_VN-25hours_single-low",   # thay thế, chất lượng thấp hơn
    "vi-vivos": "vi_VN-vivos-x_low",            # thay thế khác, chất lượng thấp hơn
}
DEFAULT_PIPER_VOICE = "vi-vais1000"
_piper_voice_cache = {}  # {model_path: PiperVoice đã load} — load model 1 lần, dùng lại cho mọi câu

# Bộ giọng Piper tiếng Việt MỞ RỘNG từ HuggingFace "doof-ferb/nghitts-copy"
PIPER_NGHITTS_VOICES = {
    "banmai", "chieuthanh", "lacphi", "manhdung", "ngochuyen",
    "adam1", "calmwoman3688", "deepman3909", "duyoryx3175", "maiphuong",
    "minhkhang", "minhquang", "minhthu", "mytam2", "mytam2794",
    "ngochuyennew", "ngocngan3701", "phuongtrang", "taian2", "taian4",
    "thanhphuong2", "thientam", "tranthanh3870", "vietthao3886", "yannew",
}
_NGHITTS_BASE_URL = "https://huggingface.co/doof-ferb/nghitts-copy/resolve/main/piper-tts"

# CapCut TTS qua HuggingFace Space tony2k/ai-voice-studio
CAPCUT_TTS_API_BASE = os.environ.get(
    "CAPCUT_TTS_URL",
    "https://tony2k-ai-voice-studio.hf.space"
)

# Giọng CapCut tiếng Việt nổi bật
CAPCUT_VIETNAMESE_VOICES = {
    "co-gai"           : "BV074_streaming",           # Cô Gái Hoạt Ngôn (mặc định)
    "thanh-nien"       : "BV075_streaming",           # Thanh Niên Tự Tin
    "nu-pho-thong"     : "vi_female_huong",           # Giọng Nữ Phổ Thông
    "nho-ngot"         : "BV421_vivn_streaming",      # Nhỏ Ngọt Ngào
    "mai"              : "BV562_streaming",           # Mai
    "alex"             : "BV560_streaming",           # Alex Đại Đế
    "ban-mai"          : "multi_female_yangguangnv_uranus_bigtts",  # Ban Mai
    "ban-tin"          : "multi_female_sisi_uranus_bigtts",         # Bản Tin nữ
    "gai-moi-lon"      : "multi_female_peiqi_uranus_bigtts",        # Giọng Gái Mới Lớn
    "nam-tram"         : "multi_male_felipe_uranus_bigtts",         # Giọng Nam Trầm
    "robot"            : "BV075_streaming_robot_dsp",               # Robot VN
}
DEFAULT_CAPCUT_VOICE = "co-gai"  # BV074_streaming

# Danh sách rút gọn các giọng edge-tts hay dùng
POPULAR_VOICES = {
    "Tiếng Việt": ["vi-VN-HoaiMyNeural (nữ)", "vi-VN-NamMinhNeural (nam)"],
    "Tiếng Anh (Mỹ)": ["en-US-AvaNeural (nữ)", "en-US-GuyNeural (nam)", "en-US-JennyNeural (nữ)"],
    "Tiếng Trung": ["zh-CN-XiaoxiaoNeural (nữ)", "zh-CN-YunxiNeural (nam)"],
    "Tiếng Hàn": ["ko-KR-SunHiNeural (nữ)", "ko-KR-InJoonNeural (nam)"],
    "Tiếng Nhật": ["ja-JP-NanamiNeural (nữ)", "ja-JP-KeitaNeural (nam)"],
}

# Whisper Presets
WHISPER_PRESETS = {
    "fast":     {"model": "small"},
    "balanced": {"model": "medium"},
    "quality":  {"model": "large-v3"},
}

# Cấu hình AI Translation
DEFAULT_TRANSLATE_ENGINE = "gemini"

# Gemini Models
DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"

# Groq Models & API
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELS = {
    "qwen/qwen3.8-27b": "Qwen 3.8 27B (Khuyên dùng - dịch tiếng Việt tự nhiên, ngắn gọn)",
    "openai/gpt-oss-120b": "GPT-OSS 120B (OpenAI mã nguồn mở 120B - rất mạnh)",
    "openai/gpt-oss-20b": "GPT-OSS 20B (Nhẹ, tốc độ xử lý nhanh)",
}
DEFAULT_GROQ_MODEL = "qwen/qwen3.8-27b"

# Dấu hiệu lỗi quota Gemini & Groq (429 RESOURCE_EXHAUSTED / Rate limit)
_QUOTA_SIGNALS = (
    "429", "resource_exhausted", "quota exceeded",
    "quotafailure", "generaterequestsperdayperproject", "free_tier",
    "rate_limit_exceeded", "rate limit reached", "tokens per day", "requests per day",
)

# Timing & Dubbing Constants
MIN_GAP_MS = 120        # khoảng nghỉ tối thiểu bắt buộc trước câu kế tiếp, tránh dính giọng
MAX_START_SHIFT_MS = 100  # dự phòng cho việc dịch start sớm hơn 1 chút

MIX_PRESETS = {
    "dubbing":   (0.0, 1.0),   # lồng tiếng hoàn toàn: tắt hẳn audio gốc
    "voiceover": (0.25, 1.0),  # thuyết minh: giữ nhẹ audio gốc, giọng đọc đè lên
}
