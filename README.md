# Tool Vietsub + Lồng Tiếng AI (Video Dubbing & Subtitle Automation)

Công cụ tự động hóa toàn diện quy trình làm video Vietsub, Thuyết minh và Lồng tiếng AI (chuẩn trend TikTok, Douyin, YouTube Shorts, Reels, Review phim, Phim tài liệu,...).

---

## 🌟 Điểm nổi bật & Tính năng chính

1. **Nhận diện giọng nói siêu chuẩn (Whisper + VAD)**:
   - Tích hợp mô hình `faster-whisper` (hỗ trợ GPU CUDA và CPU int8).
   - Tự động gắn nhãn mốc thời gian từng từ (`word_timestamps`).
   - **Lọc tần số & Khử lệch mốc thời gian**: Kết hợp bộ lọc dải tần âm thanh và mô hình **Silero VAD** giúp triệt tiêu hoàn toàn hiện tượng tiếng động lớn (tiếng nổ, súng, đập bàn, va đập) làm phụ đề xuất hiện sớm trước khi nhân vật cất lời.
2. **Trích xuất phụ đề cứng ngoại tuyến (RapidOCR)**:
   - Quét và nhận diện chữ trực tiếp trên khung hình video (Hardsub OCR) bằng **RapidOCR (ONNX Runtime)** nhẹ, không cần GPU rời.
   - Thích hợp cho video Douyin, TikTok, Kuaishou có nhạc quá to hoặc diễn viên lầm bầm khiến Whisper khó nghe.
3. **Dịch thuật AI thông minh (Gemini & Groq Cloud)**:
   - Dịch bằng **Google Gemini** (`gemini-2.5-flash`) hoặc **Groq Cloud** siêu tốc (`qwen/qwen3.8-27b`, `llama-3.3-70b-versatile`).
   - Tự động giữ nguyên timestamp, chia nhỏ xử lý theo nhóm tránh lỗi lệch dòng, tự động thử lại khi gặp giới hạn hạn mức (quota).
4. **Đa dạng công nghệ giọng đọc (TTS Engine)**:
   - **CapCut TTS**: Giọng lồng tiếng biểu cảm cao, tự nhiên như người thật (cô gái, thanh niên, nữ phổ thông, nhỏ ngọt, mai, alex, ban mai, bản tin, gái mới lớn, nam trầm, robot,...) kèm tùy chỉnh tốc độ đọc (`--capcut-rate`).
   - **Microsoft Edge-TTS**: Chuẩn giọng Hoài My, Nam Minh cực kỳ mượt mà.
   - **Piper TTS**: Chạy **Offline 100%** không cần internet, tốc độ tức thì.
5. **Nhận diện người nói & Lồng tiếng đa nhân vật (Speaker Diarization)**:
   - Tích hợp `pyannote-audio` tự động phân tách từng người nói trong video.
   - Gán giọng riêng cho từng nhân vật, tự động phân vai (Role bucketing: nam, nữ, nhân vật chính, phụ).
6. **Bộ trộn âm thanh chuẩn phòng thu (Audio Mixing)**:
   - Hỗ trợ các preset: `dubbing` (tắt tiếng gốc, lồng tiếng 100%), `voiceover` (thuyết minh giữ 25% tiếng gốc).
   - Chế độ **Custom**: Tự do điều chỉnh tỉ lệ âm lượng nhạc nền (`0.0` - `1.0`) và giọng lồng tiếng (`0.0` - `2.0`).
   - Xử lý qua FFmpeg với `normalize=0` (giữ trọn vẹn 100% tỉ lệ đã chọn) và `alimiter=0.95` (chống vỡ tiếng, rè loa khi nhạc nền và giọng đọc cùng cao trào).
7. **Tự động đồng bộ Timeline (Auto-fit Timeline)**:
   - Tự động tăng tốc giọng đọc một cách tự nhiên (`max-speed=1.25x`) và cắt khoảng lặng thừa để câu đọc không bị đè lên nhau.
   - **Đồng bộ ngược**: Sau khi xuất giọng lồng tiếng, phụ đề tiếng Việt tự động co giãn khớp 100% với giọng đọc thực tế.
8. **Định dạng phụ đề & Trình chỉnh vị trí Canvas kéo thả**:
   - Trực tiếp kéo thả phụ đề và vùng che mờ (mask/blur) trên màn hình Canvas trực quan.
   - Che/làm mờ phụ đề cũ: Hỗ trợ `--mask-style box` hoặc `blur`, kèm tính năng làm mờ nhiều vùng bổ sung (`--extra-blur`).
   - Hỗ trợ xuất ảnh xem trước kiểu chữ tức thì mà không cần render cả video.
9. **Tải video từ link trực tuyến (Loại bỏ Watermark / Logo)**:
   - Hỗ trợ tải video từ **Douyin, TikTok, YouTube (Shorts), Facebook (Reels), Kuaishou, Bilibili...**
   - **Tự động loại bỏ Watermark**: Tự động bóc tách và lấy nguồn video sạch logo gốc từ Douyin & TikTok.
   - Nhận diện thông minh: Cho phép dán trực tiếp link rút gọn hoặc toàn bộ đoạn văn bản chia sẻ từ app điện thoại (VD: `7.12 复制打开抖音... https://v.douyin.com/...`).
   - Tích hợp trơn tru trên cả Giao diện GUI (nút **"⬇ Tải từ link..."**) và Dòng lệnh CLI (`download` hoặc truyền link thẳng vào lệnh `auto`).

---

## 1. Cài đặt (Làm 1 lần)

### Cách 1: Tự động (Khuyên dùng)
Yêu cầu duy nhất: Đã cài **Python 3.9+** (khi cài trên Windows nhớ **tick chọn "Add python.exe to PATH"**).

- **Windows**: Bấm đúp vào file `install.bat`.
- **Mac / Linux**: Mở Terminal tại thư mục này, chạy `./install.sh`.

Tool sẽ tự động tạo môi trường ảo `.venv`, cài đặt các thư viện cần thiết và thiết lập FFmpeg.
Sau khi cài xong:
- Windows: Bấm đúp `run_gui.bat` để mở giao diện.
- Mac / Linux: Chạy `./run_gui.sh`.

### Cách 2: Cài đặt thủ công
Cần có: Python 3.9+ và **FFmpeg** đã thêm vào PATH hệ thống.

```bash
# Tạo môi trường ảo (khuyên dùng)
python -m venv .venv
# Kích hoạt môi trường ảo:
# Windows: .venv\Scripts\activate
# Linux/Mac: source .venv/bin/activate

# Cài đặt thư viện phụ thuộc:
pip install -r requirements.txt

# (Tùy chọn) Cài thêm nếu muốn dùng tính năng nhận diện người nói (Diarization):
pip install -r requirements-diarization.txt
```

---

## 2. Thiết lập API Key Dịch Thuật

Để sử dụng tính năng dịch phụ đề tự động, bạn có thể dùng **Google Gemini** hoặc **Groq Cloud** (cả hai đều cung cấp hạn mức miễn phí rất thoải mái):

1. **Google Gemini API Key**:
   - Lấy key miễn phí tại: https://aistudio.google.com/apikey
   - Dán vào ô "Gemini API key" trên giao diện tool, hoặc thêm `--api-key KEY` vào CLI.
   - Đặt biến môi trường (khuyên dùng): `set GEMINI_API_KEY=key_cua_ban`
2. **Groq Cloud API Key** (Dịch siêu tốc):
   - Lấy key miễn phí tại: https://console.groq.com/keys
   - Dán vào ô "Groq API key" trên giao diện tool, hoặc thêm `--groq-api-key KEY` vào CLI.
   - Đặt biến môi trường: `set GROQ_API_KEY=key_cua_ban`

---

## 3. Hướng dẫn sử dụng Giao diện Đồ Họa (GUI)

Mở giao diện bằng cách chạy `run_gui.bat` hoặc lệnh:
```bash
python gui.py
```

Giao diện được thiết kế hiện đại, bố cục 5 Tab rõ ràng:
1. **Tab 1: Video & Nạp**: Kéo thả hoặc chọn file video đầu vào.
2. **Tab 2: Phân tích & Phụ đề**:
   - Trình chỉnh sửa phụ đề phân trang mượt mà (chống giật lag khi danh sách câu dài).
   - Nút phát thử từng đoạn audio/câu thoại.
   - Chỉnh sửa văn bản, ghép câu, tách câu trực tiếp.
3. **Tab 3: Dịch & AI**:
   - Lựa chọn nguồn phụ đề: **🎙 Nhận diện giọng nói (Whisper)** hoặc **👁 Quét phụ đề cứng (RapidOCR)**.
   - Tùy chọn model Whisper (`small`, `medium`, `large-v3`), thiết bị (CUDA/CPU), nhận diện người nói (`Diarization`).
   - Chọn engine dịch (`Gemini` hoặc `Groq`), model dịch, kiểm tra hạn mức API.
4. **Tab 4: Giọng đọc & Lồng tiếng**:
   - Chọn công nghệ TTS: **CapCut TTS** (nhiều giọng biểu cảm), **Edge-TTS** hoặc **Piper TTS**.
   - Thiết lập tốc độ đọc (`CapCut Rate`), chế độ đơn giọng hoặc đa nhân vật theo vai.
   - **Bộ trộn âm (Audio Mix)**: Chọn `voiceover`, `dubbing` hoặc `custom` (chỉnh chính xác % nhạc gốc và % giọng đọc AI).
5. **Tab 5: Xuất video & Kiểu chữ**:
   - Thiết lập Font chữ, kích thước, màu sắc, viền, bóng, nền box.
   - **Trình chỉnh Canvas trực quan**: Kéo thả khung phụ đề và thanh trượt vùng che mờ (Mask) trực tiếp trên ảnh chụp khung hình.
   - Nút **Xem trước phụ đề** (render nhanh 1 ảnh xem trước trong 1-2 giây).
   - Nút chạy hành động: **Chỉ lồng tiếng**, **Chỉ gắn phụ đề**, hoặc **Quy trình đầy đủ (Auto)**.

---

## 4. Hướng dẫn sử dụng Dòng Lệnh (CLI)

### 4.1. Quy trình tự động hoàn toàn (`auto`)

**A. Nguồn từ Giọng nói (Whisper):**
```bash
# Tự động nghe, dịch, dừng lại để bạn kiểm tra câu chữ
python dub_tool.py auto video.mp4 -o output.mp4 --script-out viet.srt --pause-for-edit

# Sau khi sửa xong viet.srt, xuất video hoàn chỉnh:
python dub_tool.py all video.mp4 viet.srt -o output.mp4
```

**B. Nguồn từ Phụ đề cứng trên màn hình (RapidOCR):**
```bash
# Dùng OCR quét chữ trên khung hình thay vì nghe âm thanh:
python dub_tool.py auto video.mp4 -o output.mp4 --ocr --crop-top 0.72 --crop-bottom 0.95
```

**C. Tải video trực tiếp từ link (TikTok, Douyin, YouTube, Facebook...):**
```bash
# Tải video từ link (tự động loại bỏ Watermark / Logo):
python dub_tool.py download "https://v.douyin.com/xxxxxx/" -o my_video.mp4

# Hoặc truyền link trực tiếp vào lệnh auto (tool tự động tải sạch logo -> dịch -> lồng tiếng -> xuất video):
python dub_tool.py auto "https://v.douyin.com/xxxxxx/" -o output.mp4 --voice co-gai
```

---

### 4.2. Toàn bộ danh sách lệnh có sẵn

| Lệnh | Mô tả |
|---|---|
| `download` (hoặc `dl`) | Tải video từ link (TikTok, Douyin, YouTube, Facebook...) tự động loại bỏ Watermark / Logo |
| `auto` | Tự động toàn bộ quy trình: Trích xuất (Whisper/OCR) → Dịch → Lồng tiếng AI → Gắn phụ đề (hỗ trợ nhập cả link trực tuyến) |
| `transcribe` | Nhận diện giọng nói thành phụ đề `.srt` bằng Faster-Whisper + Silero VAD |
| `ocr` | Trích xuất phụ đề cứng (hardsub) từ video thành `.srt` bằng RapidOCR |
| `translate` | Dịch file phụ đề `.srt` bằng Gemini hoặc Groq Cloud |
| `dub` | Sinh giọng đọc AI từ `.srt` và ghép vào audio của video (không gắn phụ đề) |
| `burn` | Khắc phụ đề cứng vào video (giữ nguyên 100% âm thanh gốc, không lồng tiếng) |
| `all` | Kết hợp `dub` (lồng tiếng) + `burn` (gắn phụ đề) trong 1 lệnh (thêm `--no-dub` để chỉ gắn sub) |
| `voices` | Liệt kê toàn bộ danh sách giọng đọc khả dụng (CapCut, Edge-TTS, Piper) |
| `check-quota`| Kiểm tra tính hợp lệ và hạn mức còn lại của Gemini/Groq API Key |
| `template` | Tạo khung phụ đề rỗng chia đều theo giây để tự biên kịch |

---

### 4.3. Các tùy chọn chi tiết theo nhóm chức năng

#### A. Giọng đọc & Lồng tiếng (`dub`, `all`, `auto`)
* `--tts-engine capcut|edge|piper`:
  * `capcut` (khuyên dùng): Giọng lồng tiếng siêu tự nhiên, nhiều sắc thái cảm xúc.
  * `edge`: Giọng đọc mượt mà từ Microsoft Edge TTS (`nu-hoaimy`, `nam-namminh`,...).
  * `piper`: Chạy ngoại tuyến hoàn toàn (offline).
* `--voice <tên_giọng>`:
  * CapCut: `co-gai`, `thanh-nien`, `nu-pho-thong`, `nho-ngot`, `mai`, `alex`, `ban-mai`, `ban-tin`, `gai-moi-lon`, `nam-tram`, `robot`,...
  * Edge-TTS: `nu-hoaimy`, `nam-namminh`.
  * Piper: `vi-vais1000` (giọng chuẩn tốt nhất).
* `--capcut-rate 1.0`: Tốc độ giọng đọc CapCut (ví dụ `1.1` hoặc `1.2` để đọc nhanh hơn).
* `--mix-preset dubbing|voiceover`:
  * `dubbing`: Tắt hẳn tiếng gốc (0%), chỉ phát giọng lồng tiếng (100%).
  * `voiceover`: Thuyết minh, giữ 25% tiếng gốc, 100% giọng lồng tiếng.
* `--bg-volume <float>` & `--dub-volume <float>`: Chế độ Custom chỉnh tay tỉ lệ âm lượng:
  * `--bg-volume`: Âm lượng video gốc (`0.0` - `1.0`, khuyên dùng `0.10` - `0.18` cho nhạc nền).
  * `--dub-volume`: Âm lượng giọng lồng tiếng (`0.0` - `2.0`, khuyên dùng `1.0` - `1.2`).
* `--speaker-voices "Người 1:thanh-nien,Người 2:co-gai"`: Gán giọng riêng cho từng nhân vật.
* `--merge-speakers "Người 3:Người 1"`: Gộp nhân vật khi lồng tiếng.
* `--single-voice`: Ép chỉ dùng 1 giọng đọc duy nhất cho toàn bộ video.
* `--max-speed 1.25`: Giới hạn tốc độ tăng tối đa khi câu đọc dài hơn thời lượng phụ đề (mặc định 1.25x, bảo đảm không méo giọng).

#### B. Nhận diện giọng nói (`transcribe`, `auto`)
* `--model tiny|base|small|medium|large-v3`: Kích thước mô hình Whisper (khuyên dùng `small` cho video ngắn, `large-v3` khi cần độ chính xác cao nhất).
* `--device auto|cuda|cpu`: Thiết bị xử lý (tự động ưu tiên GPU CUDA).
* `--compute-type auto|float16|int8`: Kiểu dữ liệu tính toán (float16 cho CUDA, int8 cho CPU).
* `--preset fast|balanced|quality`: Cấu hình nhanh tương ứng model `small`, `medium` hoặc `large-v3`.
* `--word-timestamps`: Bật tính timestamp từng từ (mặc định BẬT, giúp neo mốc chính xác).
* `--min-silence-ms 500`: Khoảng lặng tối thiểu để tách câu.
* `--diarize`: Bật nhận diện người nói (yêu cầu cài đặt `requirements-diarization.txt` và HuggingFace token).
* `--hf-token <token>`: HuggingFace Token (nếu không đặt biến môi trường `HF_TOKEN`).
* `--sub-delay-ms <ms>`: Bù trừ độ trễ mốc thời gian phụ đề (ms, mặc định 0). Ví dụ: `100` hoặc `150` để lùi phụ đề lại nếu chữ xuất hiện trước tiếng nói.

#### C. Trích xuất phụ đề cứng bằng OCR (`ocr`, `auto`)
* `--crop-top 0.70` & `--crop-bottom 0.98`: Tọa độ đỉnh và đáy vùng phụ đề (tỉ lệ 0.0 - 1.0 theo chiều cao video).
* `--crop-left 0.05` & `--crop-right 0.95`: Tọa độ mép trái và mép phải vùng quét.
* `--ocr-fps 1.5`: Tần suất trích xuất khung hình (1.5 khung hình/giây giúp quét siêu tốc mà không bỏ sót chữ).

#### D. Dịch thuật AI (`translate`, `auto`)
* `--translate-engine gemini|groq`: Chọn engine dịch.
* `--translate-model <tên>`: Tên model dịch (Gemini: `gemini-2.5-flash`; Groq: `qwen/qwen3.8-27b`, `llama-3.3-70b-versatile`).
* `--batch-size 30`: Số dòng dịch mỗi nhóm (tự động chia nhỏ xử lý chống sót/lệch dòng).

#### E. Kiểu dáng phụ đề & Che mờ phụ đề cũ (`burn`, `all`, `auto`)
* `--font-name`: Tên font chữ đã cài trong hệ thống (VD: `Arial`, `Be Vietnam Pro`, `Montserrat`).
* `--font-size`: Cỡ chữ (mặc định `16`).
* `--font-color`: Màu chữ (VD: `white`, `yellow`, `#FFD700`).
* `--outline-color` & `--outline-width`: Màu và độ dày viền chữ.
* `--position top|middle|bottom`: Vị trí hiển thị phụ đề.
* `--pos-x` & `--pos-y`: Tọa độ vị trí tự do theo tỉ lệ (0.0 đến 1.0) khi kéo thả từ Canvas.
* `--box` & `--box-color`: Bật hộp nền kiểu caption TikTok.
* `--mask-original`: Bật vùng che/mờ phụ đề cũ.
* `--mask-style box|blur`: Kiểu che (`box` = khối màu đặc; `blur` = làm mờ tự nhiên).
* `--mask-top`, `--mask-bottom`, `--mask-blur`: Tọa độ và bán kính mờ.
* `--extra-blur "top,bottom,strength[,left,right]"`: Làm mờ thêm các vùng logo, watermark khác.
* `--no-dub` (hoặc `--sub-only`): Chế độ chỉ gắn phụ đề vào video gốc, giữ nguyên 100% âm thanh gốc và bỏ qua hoàn toàn bước lồng tiếng AI TTS (áp dụng cho `auto` và `all`).
* `--preview` & `--preview-time <sec>`: Xuất 1 ảnh xem trước kiểu chữ tại giây chỉ định mà không render cả video.

---

## 5. Cơ chế khôi phục lỗi & Bộ đệm (Cache)

* **Bộ đệm TTS (`.dubcache_<tên_srt>`)**: Tool tự động ghi nhớ các câu đọc đã sinh thành công. Nếu xảy ra ngắt mạng hoặc hết quota giữa chừng, bạn chỉ cần bấm chạy lại lệnh, tool sẽ tự động bỏ qua các câu đã xong và tiếp tục phần còn lại mà không cần tải lại từ đầu.
* **Tự động thử lại (Retry with backoff)**: Tự động phục hồi khi gặp sự cố mạng tạm thời hoặc chạm ngưỡng rate-limit của API.
* **Khởi động ứng dụng sạch (Clean Startup)**: Giao diện mở lên ngay lập tức, không nạp lại video cũ của phiên trước giúp loại bỏ hoàn toàn độ trễ mở app; đồng thời lưu trữ nguyên vẹn 100% các cài đặt API, font, giọng đọc và thông số bạn đã cấu hình trong `user_settings.json`.

---

## 6. Mẹo để làm video hay & chuyên nghiệp

1. **Âm lượng hài hòa**: Khi dùng trộn âm `custom`, hãy đặt **Nhạc gốc: 0.12 - 0.15** và **Giọng lồng: 1.00 - 1.10**. Mức này đảm bảo giữ được hiệu ứng âm thanh môi trường và nhạc nền sống động của phim mà giọng thuyết minh AI vẫn rõ ràng, sắc nét.
2. **Câu dịch ngắn gọn**: Lời thoại tiếng Việt càng gãy gọn, súc tích thì giọng đọc AI càng tự nhiên, thong thả, không bị ép phải đọc dồn dập để kịp khuôn hình.
3. **Phụ đề Douyin mờ nhẹ**: Với video có chữ Trung Quốc ở đáy màn hình, sử dụng `--mask-style blur` kết hợp độ mờ `20 - 30` sẽ mang lại cảm giác mờ ảo tự nhiên hơn nhiều so với việc che một dải đen đặc.
4. **Kiểm tra nhanh trước khi render**: Luôn bấm nút **"Xem trước kiểu chữ"** trên GUI để chắc chắn màu sắc và cỡ chữ ưng ý trước khi bấm render toàn bộ video.

---

## 7. Giấy phép & Bản quyền
Công cụ này được phát triển phục vụ mục đích học tập, nghiên cứu và hỗ trợ sáng tạo nội dung cá nhân. Khi sử dụng tư liệu của bên thứ ba, vui lòng tuân thủ luật bản quyền và chính sách sử dụng hợp lý (Fair Use) của nền tảng sở tại.
