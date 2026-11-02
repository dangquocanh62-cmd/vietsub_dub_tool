"""
DỊCH PHỤ ĐỀ SANG TIẾNG VIỆT (GIỮ NGUYÊN TIMESTAMP) BẰNG GEMINI HOẶC GROQ
"""

import json
import os
import sys
import time
import requests
import srt
from tqdm import tqdm

from .config import (
    _QUOTA_SIGNALS,
    DEFAULT_TRANSLATE_ENGINE,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_GROQ_MODEL,
    GROQ_API_URL,
)


def _read_saved_setting(key_name: str) -> str:
    """Đọc cấu hình đã lưu từ user_settings.json nếu có."""
    try:
        cfg_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "user_settings.json")
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return (data.get(key_name) or "").strip()
    except Exception:
        pass
    return ""


def _get_gemini_client(api_key=None):
    key = api_key or os.environ.get("GEMINI_API_KEY") or _read_saved_setting("gemini_api_key")
    if not key:
        print("✘ Thiếu Gemini API key.")
        print("  Lấy key miễn phí tại: https://aistudio.google.com/apikey")
        print("  Rồi dùng 1 trong 2 cách:")
        print("    1) Truyền trực tiếp:      --api-key DÁN_KEY_VÀO_ĐÂY")
        print("    2) Đặt biến môi trường:   set GEMINI_API_KEY=DÁN_KEY_VÀO_ĐÂY   (Windows)")
        print("                              export GEMINI_API_KEY=DÁN_KEY_VÀO_ĐÂY (Mac/Linux)")
        sys.exit(1)
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("✘ Thiếu thư viện google-genai. Cài bằng:")
        print("  pip install google-genai")
        sys.exit(1)
    http_options = types.HttpOptions(timeout=60_000)
    return genai.Client(api_key=key, http_options=http_options)


def _get_groq_api_key(api_key=None):
    key = api_key or os.environ.get("GROQ_API_KEY") or _read_saved_setting("groq_api_key")
    if not key:
        print("✘ Thiếu Groq API key.")
        print("  Lấy key miễn phí tại: https://console.groq.com/keys")
        print("  Rồi dùng 1 trong 2 cách:")
        print("    1) Truyền trực tiếp:      --groq-api-key DÁN_KEY_VÀO_ĐÂY (hoặc --api-key)")
        print("    2) Đặt biến môi trường:   set GROQ_API_KEY=DÁN_KEY_VÀO_ĐÂY   (Windows)")
        print("                              export GROQ_API_KEY=DÁN_KEY_VÀO_ĐÂY (Mac/Linux)")
        sys.exit(1)
    return key


def _is_quota_error(exc) -> bool:
    """Kiểm tra xem exception hoặc response có phải lỗi hết quota / rate limit hay không."""
    msg = str(exc).lower()
    return any(sig in msg for sig in _QUOTA_SIGNALS)


def check_gemini_quota(api_key=None, model=DEFAULT_GEMINI_MODEL):
    """
    Kiểm tra xem Gemini API key có hợp lệ và còn quota hay không.
    Trả về tuple: (is_ok: bool, message: str)
    """
    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        return False, "Thiếu Gemini API Key. Vui lòng nhập API Key trước khi kiểm tra."
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return False, "Thiếu thư viện google-genai. Hãy cài bằng: pip install google-genai"

    try:
        http_options = types.HttpOptions(timeout=15_000)
        client = genai.Client(api_key=key, http_options=http_options)
        response = client.models.generate_content(
            model=model,
            contents="Hi"
        )
        if response and response.text:
            return True, f"✔ Gemini API Key HỢP LỆ và CÒN QUOTA!\n\nModel: {model}\nTrạng thái: Phản hồi thành công."
        else:
            return True, f"✔ Gemini API Key HỢP LỆ!\n\nModel: {model}\nTrạng thái: Kết nối thành công."
    except Exception as e:
        msg = str(e)
        if _is_quota_error(e):
            return False, f"✘ Gemini API Key HẾT QUOTA (RESOURCE_EXHAUSTED / 429):\n\n{msg}"
        elif any(k in msg.lower() for k in ["api_key", "invalid", "unauthorized", "permission", "400", "403"]):
            return False, f"✘ Gemini API Key KHÔNG HỢP LỆ hoặc không có quyền truy cập:\n\n{msg}"
        else:
            return False, f"✘ Lỗi khi kiểm tra Gemini API:\n\n{msg}"


def check_groq_quota(api_key=None, model=DEFAULT_GROQ_MODEL):
    """
    Kiểm tra xem Groq API key có hợp lệ và còn quota hay không.
    Trả về tuple: (is_ok: bool, message: str)
    """
    key = api_key or os.environ.get("GROQ_API_KEY")
    if not key:
        return False, "Thiếu Groq API Key. Vui lòng nhập API Key trước khi kiểm tra."

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 10,
    }
    try:
        resp = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=15)
        if resp.status_code == 200:
            return True, f"✔ Groq API Key HỢP LỆ và CÒN QUOTA!\n\nModel: {model}\nTrạng thái: Phản hồi thành công."
        
        err_msg = resp.text

        if resp.status_code == 429 or _is_quota_error(err_msg):
            return False, f"✘ Groq API Key HẾT QUOTA / RATE LIMIT (429):\n\n{err_msg}"
        elif resp.status_code in (401, 403):
            return False, f"✘ Groq API Key KHÔNG HỢP LỆ (Unauthorized {resp.status_code}):\n\n{err_msg}"
        elif resp.status_code == 404:
            return False, f"✘ Model '{model}' không tồn tại trên Groq. Hãy chọn '{DEFAULT_GROQ_MODEL}'."
        else:
            return False, f"✘ Lỗi khi kiểm tra Groq API (HTTP {resp.status_code}):\n\n{err_msg}"
    except Exception as e:
        return False, f"✘ Lỗi kết nối tới Groq API:\n\n{e}"


def cmd_check_quota(args):
    engine = getattr(args, "translate_engine", None) or DEFAULT_TRANSLATE_ENGINE
    model = getattr(args, "translate_model", None)
    
    if engine == "groq":
        key = getattr(args, "groq_api_key", None) or getattr(args, "api_key", None) or _read_saved_setting("groq_api_key")
        model = model or _read_saved_setting("groq_model") or DEFAULT_GROQ_MODEL
        is_ok, msg = check_groq_quota(key, model)
    else:
        key = getattr(args, "api_key", None) or _read_saved_setting("gemini_api_key")
        model = model or _read_saved_setting("gemini_model") or DEFAULT_GEMINI_MODEL
        is_ok, msg = check_gemini_quota(key, model)

    print(msg)
    if not is_ok:
        sys.exit(1)


def _checkpoint_path(output_path: str) -> str:
    base = os.path.splitext(output_path)[0]
    # Check old checkpoint first
    old_ckpt = base + ".gemini_checkpoint.json"
    new_ckpt = base + ".translate_checkpoint.json"
    if os.path.exists(old_ckpt) and not os.path.exists(new_ckpt):
        return old_ckpt
    return new_ckpt


def _load_checkpoint(ckpt_path: str, engine: str, model: str, target: str, total: int):
    """Tải checkpoint nếu tồn tại và hợp lệ."""
    if not os.path.exists(ckpt_path):
        return []
    try:
        with open(ckpt_path, encoding="utf-8") as f:
            ck = json.load(f)
        if ck.get("target") != target:
            print(f"  ⚠ Checkpoint không khớp target, bỏ qua.")
            return []
        translations = ck.get("translations", [])
        completed = ck.get("completed", 0)
        if completed != len(translations):
            print(f"  ⚠ Checkpoint bị hỏng (completed={completed} ≠ len={len(translations)}), bỏ qua.")
            return []
        if completed > total:
            print(f"  ⚠ Checkpoint có nhiều câu hơn file hiện tại ({completed} > {total}), bỏ qua.")
            return []
        print(f"  ✔ Tìm thấy checkpoint: đã dịch {completed}/{total} câu. Tiếp tục từ câu {completed+1}.")
        return translations
    except Exception as e:
        print(f"  ⚠ Không đọc được checkpoint ({e}), bắt đầu lại từ đầu.")
        return []


def _save_checkpoint(ckpt_path: str, engine: str, model: str, target: str, translations: list):
    """Lưu tiến độ dịch vào file checkpoint."""
    try:
        data = {
            "engine": engine,
            "model": model,
            "target": target,
            "completed": len(translations),
            "translations": translations,
        }
        with open(ckpt_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        tqdm.write(f"  ⚠ Không lưu được checkpoint: {e}")


def _build_gemini_prompt(texts: list, target_lang: str) -> str:
    """Tạo prompt dịch Gemini."""
    lang_name = "Việt" if target_lang == "vi" else target_lang
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(texts))
    return (
        f"Dịch các câu đánh số dưới đây sang tiếng {lang_name}, văn phong tự nhiên, "
        "đời thường, phù hợp lồng tiếng cho video ngắn (vlog/dashcam). Giữ độ dài câu "
        "dịch gần với câu gốc, ưu tiên ngắn gọn — vì bản dịch sẽ dùng để lồng tiếng AI "
        "khớp với thời lượng nói của câu gốc. Dịch sát nghĩa, KHÔNG tự suy diễn/thêm ý "
        "nếu câu gốc không rõ nghĩa.\n\n"
        f"Trả lời DUY NHẤT 1 JSON array of string, đúng {len(texts)} phần tử, đúng thứ "
        "tự tương ứng từng câu, không thêm markdown/code fence, không thêm giải thích.\n\n"
        f"{numbered}"
    )


_build_translate_prompt = _build_gemini_prompt


def _call_gemini_translate(client, model, group: list, target: str):
    """Gọi Gemini dịch 1 danh sách câu. Trả về (result_list, is_quota_error, error_msg)."""
    try:
        r = client.models.generate_content(
            model=model,
            contents=_build_gemini_prompt(group, target)
        )
        raw = (r.text or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        parsed = json.loads(raw.strip())
        if isinstance(parsed, list) and len(parsed) == len(group):
            return [str(x) for x in parsed], False, None
        got = len(parsed) if isinstance(parsed, list) else "?"
        return None, False, f"Gemini trả về {got} dòng, khác với {len(group)} dòng gửi đi"
    except Exception as e:
        if _is_quota_error(e):
            return None, True, str(e)
        return None, False, str(e)


def _build_groq_messages(texts: list, target_lang: str) -> list:
    """Tạo messages cho Groq API với JSON object mode."""
    lang_name = "Việt" if target_lang == "vi" else target_lang
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(texts))
    sys_prompt = (
        f"Bạn là chuyên gia dịch thuật phụ đề phim và video ngắn. "
        f"Hãy dịch các câu được đánh số sang tiếng {lang_name}, văn phong tự nhiên, "
        "đời thường, phù hợp lồng tiếng video ngắn (vlog/review/dashcam). "
        "Giữ độ dài câu dịch gần với câu gốc, ưu tiên ngắn gọn — vì bản dịch sẽ dùng để "
        "lồng tiếng AI khớp với thời lượng nói của câu gốc. Dịch sát nghĩa, KHÔNG tự suy diễn thêm ý.\n\n"
        "QUAN TRỌNG: Bạn PHẢI trả về duy nhất 1 JSON object hợp lệ chứa key 'translations' "
        f"là mảng đúng {len(texts)} chuỗi, đúng thứ tự tương ứng từng câu:\n"
        '{"translations": ["câu dịch 1", "câu dịch 2", ...]}'
    )
    return [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": numbered}
    ]


def _parse_groq_response(raw_text: str, expected_count: int):
    raw = (raw_text or "").strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
    parsed = json.loads(raw.strip())
    if isinstance(parsed, dict):
        translations = parsed.get("translations") or parsed.get("result") or parsed.get("items")
        if isinstance(translations, list):
            parsed = translations
    if isinstance(parsed, list) and len(parsed) == expected_count:
        return [str(x) for x in parsed], None
    got = len(parsed) if isinstance(parsed, list) else "?"
    return None, f"Groq trả về {got} dòng, khác với {expected_count} dòng gửi đi"


def _call_groq_translate(api_key: str, model: str, group: list, target: str):
    """Gọi Groq API dịch 1 danh sách câu. Trả về (result_list, is_quota_error, error_msg)."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": _build_groq_messages(group, target),
        "response_format": {"type": "json_object"},
        "temperature": 0.3,
    }
    try:
        resp = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=60)
        if resp.status_code == 200:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            result, err = _parse_groq_response(content, len(group))
            if result is not None:
                return result, False, None
            return None, False, err

        err_body = resp.text
        if resp.status_code == 404 and "model_not_found" in err_body and model != DEFAULT_GROQ_MODEL:
            print(f"  ⚠ Model '{model}' không tồn tại hoặc đã đổi tên trên Groq.")
            print(f"  → Tự động chuyển sang model '{DEFAULT_GROQ_MODEL}'...")
            return _call_groq_translate(api_key, DEFAULT_GROQ_MODEL, group, target)

        is_quota = resp.status_code == 429 or any(sig in err_body.lower() for sig in _QUOTA_SIGNALS)
        return None, is_quota, f"HTTP {resp.status_code}: {err_body}"
    except Exception as e:
        if _is_quota_error(e):
            return None, True, str(e)
        return None, False, str(e)


def _call_translate(engine: str, client_or_key, model: str, group: list, target: str):
    """Điều phối gọi dịch theo engine tương ứng."""
    if engine == "groq":
        return _call_groq_translate(client_or_key, model, group, target)
    return _call_gemini_translate(client_or_key, model, group, target)


def _write_partial_srt(subs, indices, translations, output_path):
    """Ghi file .srt với phần đã dịch được, phần còn lại giữ nguyên bản gốc."""
    for i, new_text in zip(indices[:len(translations)], translations):
        subs[i].content = new_text
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(srt.compose(subs))
        print(f"  → Đã ghi file từng phần: {output_path}")
    except Exception as e:
        print(f"  ⚠ Không ghi được file từng phần: {e}")


def cmd_translate(args):
    engine = getattr(args, "translate_engine", None) or DEFAULT_TRANSLATE_ENGINE
    batch_size = max(int(getattr(args, "batch_size", 30)), 1)
    target = getattr(args, "target", "vi")

    # Xác định API key và Model theo engine
    gemini_key = getattr(args, "api_key", None) or os.environ.get("GEMINI_API_KEY")
    groq_key = getattr(args, "groq_api_key", None) or getattr(args, "api_key", None) if engine == "groq" else (getattr(args, "groq_api_key", None) or os.environ.get("GROQ_API_KEY"))

    if engine == "groq":
        client_or_key = _get_groq_api_key(groq_key)
        model = getattr(args, "translate_model", None) or DEFAULT_GROQ_MODEL
        if "llama" in model.lower():
            print(f"  ℹ Model Groq '{model}' không còn khả dụng trên API. Tự động chuyển sang '{DEFAULT_GROQ_MODEL}'.")
            model = DEFAULT_GROQ_MODEL
    else:
        client_or_key = _get_gemini_client(gemini_key)
        model = getattr(args, "translate_model", None) or DEFAULT_GEMINI_MODEL

    with open(args.input, encoding="utf-8") as f:
        subs = list(srt.parse(f.read()))

    non_empty = [(i, s.content.strip()) for i, s in enumerate(subs) if s.content.strip()]
    if not non_empty:
        print("✘ File không có nội dung để dịch.")
        sys.exit(1)
    indices = [i for i, _ in non_empty]
    texts   = [t for _, t in non_empty]
    total   = len(texts)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)

    ckpt_path  = _checkpoint_path(args.output)
    translated = _load_checkpoint(ckpt_path, engine, model, target, total)
    start_from = len(translated)

    if start_from == total:
        print(f"✔ Tất cả {total} câu đã được dịch (từ checkpoint). Ghi file...")
    else:
        engine_display = "Groq" if engine == "groq" else "Gemini"
        if start_from == 0:
            print(f"→ Đang thử dịch NGUYÊN FILE ({total} câu) bằng {engine_display} ({model})...")
            result, is_quota, err_msg = _call_translate(engine, client_or_key, model, texts, target)
            if result is not None:
                print(f"✔ Dịch nguyên file thành công ({total} câu)!")
                translated = result
                _save_checkpoint(ckpt_path, engine, model, target, translated)
            elif is_quota:
                # Kiểm tra auto-fallback sang Groq nếu đang dùng Gemini
                if engine == "gemini" and groq_key:
                    print(f"\n⚠ Gemini hết quota Free Tier ({err_msg}).")
                    print(f"  → Tự động chuyển sang Groq ({DEFAULT_GROQ_MODEL}) làm phương án dự phòng!")
                    engine = "groq"
                    model = DEFAULT_GROQ_MODEL
                    client_or_key = groq_key
                    engine_display = "Groq"
                    result, is_quota, err_msg = _call_translate(engine, client_or_key, model, texts, target)
                    if result is not None:
                        print(f"✔ Dịch nguyên file thành công bằng Groq ({total} câu)!")
                        translated = result
                        _save_checkpoint(ckpt_path, engine, model, target, translated)
                if not translated:
                    if is_quota:
                        print(f"\n✘ {engine_display} hết quota khi dịch nguyên file: {err_msg}")
                        print(f"→ DỪNG NGAY LẬP TỨC. Hãy chờ quota reset hoặc đổi API key/model.")
                        return
                    else:
                        print(f"  ⚠ Dịch nguyên file không thành công ({err_msg}).")
                        print(f"  → Chuyển sang dịch theo từng nhóm {batch_size} dòng (batch)...")
            else:
                print(f"  ⚠ Dịch nguyên file không thành công ({err_msg}).")
                print(f"  → Chuyển sang dịch theo từng nhóm {batch_size} dòng (batch)...")

        if len(translated) < total:
            start_from = len(translated)
            remaining = total - start_from
            n_batches = (remaining + batch_size - 1) // batch_size
            print(f"→ Đang dịch {remaining} câu còn lại theo batch bằng {engine_display} (kích thước {batch_size}, tổng {n_batches} batch)")
            if start_from > 0:
                print(f"  (Bỏ qua {start_from} câu đầu đã có trong checkpoint)")

            quota_hit = False
            for batch_idx, start in enumerate(range(start_from, total, batch_size), start=1):
                end   = min(start + batch_size, total)
                group = texts[start:end]
                print(f"\n→ Batch {batch_idx}/{n_batches}: câu {start+1}–{end}")

                result = None
                for attempt in range(1, 5):
                    result, is_quota, err_msg = _call_translate(engine, client_or_key, model, group, target)
                    if result is not None:
                        break
                    if is_quota:
                        # Auto fallback sang Groq nếu đang chạy Gemini
                        if engine == "gemini" and groq_key:
                            print(f"\n⚠ Gemini hết quota ở batch {batch_idx}!")
                            print(f"  → Tự động chuyển sang Groq ({DEFAULT_GROQ_MODEL}) để tiếp tục...")
                            engine = "groq"
                            model = DEFAULT_GROQ_MODEL
                            client_or_key = groq_key
                            engine_display = "Groq"
                            result, is_quota, err_msg = _call_translate(engine, client_or_key, model, group, target)
                            if result is not None:
                                break
                        quota_hit = True
                        print(f"\n✘ {engine_display} hết quota ở batch {batch_idx}: {err_msg}")
                        print(f"✔ Checkpoint đã lưu: {len(translated)}/{total} câu.")
                        if translated:
                            _write_partial_srt(subs, indices, translated, args.output)
                        print(f"→ DỪNG NGAY. Không retry thêm.")
                        break
                    is_fatal = any(k in str(err_msg).lower() for k in ["unauthorized", "invalid_api_key", "model_not_found", "401", "403"])
                    if is_fatal:
                        print(f"  ✘ Lỗi cấu hình / quyền truy cập: {err_msg}")
                        if translated:
                            _write_partial_srt(subs, indices, translated, args.output)
                        sys.exit(1)

                    print(f"  ⚠ [{attempt}/4] Lỗi tạm thời / lệch dòng: {err_msg}")
                    if attempt < 4:
                        wait = min(2 ** attempt, 20)
                        print(f"    Thử lại sau {wait}s...")
                        time.sleep(wait)

                if quota_hit:
                    return

                if result is None:
                    print(f"\n✘ Batch {batch_idx} vẫn thất bại sau 4 lần thử: {err_msg}")
                    print(f"  → DỪNG TIẾN TRÌNH DỊCH (đã lưu {len(translated)}/{total} câu hợp lệ vào checkpoint).")
                    if translated:
                        _write_partial_srt(subs, indices, translated, args.output)
                    sys.exit(1)

                translated.extend(result)
                _save_checkpoint(ckpt_path, engine, model, target, translated)
                print(f"✔ Batch {batch_idx} hoàn thành → Đã lưu checkpoint: {len(translated)}/{total} câu")

    for i, new_text in zip(indices, translated):
        subs[i].content = new_text

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(srt.compose(subs))
    print(f"\n✔ Đã dịch xong: {args.output}  ({total} câu)")
    print("  Nên mở lại file này để chỉnh câu chữ cho tự nhiên/ngắn gọn hơn trước khi lồng tiếng")
    print("  (câu dịch càng dài hơn bản gốc, TTS càng phải nói nhanh hơn để khớp thời lượng).")

    try:
        if os.path.exists(ckpt_path):
            os.remove(ckpt_path)
    except Exception:
        pass
