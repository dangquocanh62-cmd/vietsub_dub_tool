"""
BENCHMARK & VERIFICATION THỰC TẾ CHO DUBBING PIPELINE
So sánh hiệu suất Sequential (Workers=1) vs Concurrent (Workers=4)
và kiểm tra tính nhất quán 100% của Autofit Timeline.
"""

import os
import shutil
import sys
import time
import tempfile
import argparse

from core.dubbing import build_dubbed_audio, cmd_dub
from core.config import VIETNAMESE_VOICES
from core.utils import run, get_cache_dir

TEST_VIDEO = "test_dummy.mp4"
TEST_SRT = "test_dummy.srt"
OUTPUT_A = "output_sequential.mp4"
OUTPUT_B = "output_concurrent.mp4"

SAMPLE_TEXTS = [
    "Chào mừng các bạn đã quay trở lại với kênh công nghệ của chúng tôi hôm nay.",
    "Hôm nay chúng ta sẽ cùng trải nghiệm hệ thống lồng tiếng AI tự động mới nhất.",
    "Tốc độ xử lý đã được cải thiện đáng kinh ngạc nhờ vào kiến trúc đa luồng.",
    "Toàn bộ dữ liệu được tải song song qua mạng nhưng vẫn giữ nguyên nhịp điệu.",
    "Mỗi dòng phụ đề sẽ được tính toán khung thời gian chuẩn xác nhất.",
    "Thuật toán Autofit sẽ tự động căn chỉnh tốc độ đọc nếu câu thoại quá dài.",
    "Điều này giúp giọng đọc không bao giờ bị dính vào nhau hoặc bị cắt lời.",
    "Hãy cùng kiểm tra tính năng tuyệt vời này trên thực tế ngay sau đây.",
    "Chúng tôi cam kết bảo toàn 100 phần trăm công thức tính toán thời gian.",
    "Không có bất kỳ sự sai lệch nào giữa phiên bản đơn luồng và đa luồng.",
    "Hãy chú ý quan sát bảng so sánh thời gian thực thi ở cuối bài thử nghiệm.",
    "Hệ thống tự động phát hiện và bỏ qua các file âm thanh đã được lưu trong cache.",
    "Nếu gặp lỗi mạng tạm thời, worker sẽ tự động thử lại mà không làm sập tool.",
    "Giao diện dòng lệnh hiển thị tiến độ công việc một cách trực quan và rõ ràng.",
    "Bạn có thể tùy chỉnh số lượng luồng xử lý bằng tham số max tts workers.",
    "Engine Edge-TTS mang lại chất lượng giọng đọc tự nhiên và truyền cảm.",
    "Engine Piper cho phép chạy hoàn toàn offline mà không cần kết nối internet.",
    "Engine CapCut mang tới bộ giọng phong phú đa dạng cho mọi thể loại video.",
    "Việc tối ưu hóa hiệu suất giúp tiết kiệm rất nhiều thời gian xuất video.",
    "Đặc biệt là đối với các tập phim dài có hàng trăm dòng thoại phức tạp.",
    "Tất cả các đoạn audio sau khi sinh ra sẽ được trộn âm hoàn hảo với video gốc.",
    "Bạn có thể điều chỉnh âm lượng giọng lồng và nhạc nền theo ý muốn.",
    "Công cụ này hỗ trợ đầy đủ trên cả hệ điều hành Windows Linux và macOS.",
    "Mã nguồn được cấu trúc sạch sẽ dễ dàng bảo trì và mở rộng về sau.",
    "Hãy chia sẻ công cụ này nếu bạn thấy nó hữu ích cho công việc của mình.",
    "Cảm ơn các bạn đã lắng nghe và đồng hành cùng dự án của chúng tôi.",
    "Chúc các bạn có những trải nghiệm sáng tạo nội dung tuyệt vời nhất.",
    "Bây giờ chúng ta sẽ bắt đầu quá trình so sánh đo đạc hiệu năng thực tế.",
    "Kiểm tra hoàn tất thành công xuất sắc mà không gặp phải bất kỳ lỗi nào.",
    "Xin chào tạm biệt và hẹn gặp lại các bạn trong những cập nhật tiếp theo."
]


def generate_test_assets():
    """Tạo video trống 40s và file SRT 30 câu."""
    print("→ Đang tạo video thử nghiệm 40s (test_dummy.mp4)...")
    cmd_video = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=black:s=640x360:d=40",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", "40",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        TEST_VIDEO
    ]
    run(cmd_video)

    print("→ Đang tạo file phụ đề 30 câu (test_dummy.srt)...")
    # 30 câu trải dài 39s (1.2s mỗi câu + gap)
    with open(TEST_SRT, "w", encoding="utf-8") as f:
        for idx, text in enumerate(SAMPLE_TEXTS, start=1):
            start_sec = (idx - 1) * 1.25
            end_sec = start_sec + 1.10
            
            sh, sm, ss = int(start_sec // 3600), int((start_sec % 3600) // 60), int(start_sec % 60)
            sms = int((start_sec - int(start_sec)) * 1000)
            
            eh, em, es = int(end_sec // 3600), int((end_sec % 3600) // 60), int(end_sec % 60)
            ems = int((end_sec - int(end_sec)) * 1000)

            f.write(f"{idx}\n")
            f.write(f"{sh:02d}:{sm:02d}:{ss:02d},{sms:03d} --> {eh:02d}:{em:02d}:{es:02d},{ems:03d}\n")
            f.write(f"{text}\n\n")

    print("✔ Đã tạo xong assets thử nghiệm.")


def clear_cache():
    cache_dir = get_cache_dir(TEST_SRT)
    if os.path.exists(cache_dir):
        shutil.rmtree(cache_dir)
        print(f"✔ Đã xóa sạch cache: {cache_dir}")


def run_single_benchmark(workers, out_video, clear_cache_before=True):
    if clear_cache_before:
        clear_cache()

    tmp_dir = tempfile.mkdtemp(prefix="bench_tmp_")
    try:
        t_start_total = time.time()
        
        # Gọi build_dubbed_audio trực tiếp để đo chuẩn xác Phase 1, Phase 2 và thu thập segments
        voice_name = VIETNAMESE_VOICES.get("nu-hoaimy", "vi-VN-HoaiMyNeural")
        timeline = build_dubbed_audio(
            srt_path=TEST_SRT,
            video_duration_ms=40000,
            voice=voice_name,
            tmp_dir=tmp_dir,
            fit_to_timing=True,
            max_speed=1.25,
            cache_dir=get_cache_dir(TEST_SRT),
            use_cache=not clear_cache_before,
            delay=0.1,
            tts_engine="edge",
            trim_silence=True,
            max_tts_workers=workers
        )
        t_end_build = time.time()

        # Render video
        t_start_render = time.time()
        dub_wav = os.path.join(tmp_dir, "dubbed.wav")
        timeline.export(dub_wav, format="wav")
        run([
            "ffmpeg", "-y", "-i", TEST_VIDEO, "-i", dub_wav,
            "-filter_complex", "[0:a]volume=0.15[bg];[1:a]volume=1.0[dub];[bg][dub]amix=inputs=2:duration=longest:dropout_transition=0[aout]",
            "-map", "0:v:0", "-map", "[aout]",
            "-c:v", "copy", out_video
        ])
        t_end_render = time.time()

        total_time = t_end_render - t_start_total
        render_time = t_end_render - t_start_render
        tts_time = timeline.phase_timing["phase1_tts"]
        autofit_time = timeline.phase_timing["phase2_autofit"]

        return {
            "tts": tts_time,
            "autofit": autofit_time,
            "render": render_time,
            "total": total_time,
            "dub_segments": timeline.dub_segments
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def compare_autofit_outputs(segs_a, segs_b, max_tolerance_ms=15):
    if len(segs_a) != len(segs_b):
        return False, f"Độ dài segments không khớp: Sequential={len(segs_a)}, Concurrent={len(segs_b)}"
    
    diffs = []
    for a, b in zip(segs_a, segs_b):
        if a["index"] != b["index"]:
            diffs.append(f"Index mismatch: #{a['index']} vs #{b['index']}")
        if abs(a["dub_start"] - b["dub_start"]) > max_tolerance_ms:
            diffs.append(f"#{a['index']} dub_start mismatch: {a['dub_start']}ms vs {b['dub_start']}ms (lệch > {max_tolerance_ms}ms)")
        if abs(a["dub_end"] - b["dub_end"]) > max_tolerance_ms:
            diffs.append(f"#{a['index']} dub_end mismatch: {a['dub_end']}ms vs {b['dub_end']}ms (lệch > {max_tolerance_ms}ms)")
        if abs(a["speed"] - b["speed"]) > 1e-3:
            diffs.append(f"#{a['index']} speed mismatch: {a['speed']} vs {b['speed']}")
        if a["status"] != b["status"]:
            diffs.append(f"#{a['index']} status mismatch: {a['status']} vs {b['status']}")

    if diffs:
        return False, "\n".join(diffs)
    return True, "100% IDENTICAL MATCH (within tolerance)"


def main():
    print("==================================================")
    print("  BENCHMARK & VERIFICATION DUBBING PIPELINE")
    print("==================================================\n")

    generate_test_assets()

    print("\n--------------------------------------------------")
    print("  RUNNING BENCHMARK A: SEQUENTIAL (Workers = 1)")
    print("--------------------------------------------------")
    res_a = run_single_benchmark(workers=1, out_video=OUTPUT_A)

    print("\n--------------------------------------------------")
    print("  RUNNING BENCHMARK B: CONCURRENT (Workers = 4)")
    print("--------------------------------------------------")
    res_b = run_single_benchmark(workers=4, out_video=OUTPUT_B)

    # Kiểm tra Autofit Identity
    is_match, match_msg = compare_autofit_outputs(res_a["dub_segments"], res_b["dub_segments"])

    speedup = res_a["total"] / res_b["total"] if res_b["total"] > 0 else 1.0

    print("\n==================================================")
    print("               BENCHMARK REPORT")
    print("==================================================")
    print(f"{'':20s} {'Sequential':<13s} {'Concurrent':<13s}")
    print(f"{'TTS':20s} {res_a['tts']:<12.2f}s {res_b['tts']:<12.2f}s")
    print(f"{'Autofit':20s} {res_a['autofit']:<12.2f}s {res_b['autofit']:<12.2f}s")
    print(f"{'Final render':20s} {res_a['render']:<12.2f}s {res_b['render']:<12.2f}s")
    print("--------------------------------------------------")
    print(f"{'TOTAL':20s} {res_a['total']:<12.2f}s {res_b['total']:<12.2f}s")
    print("--------------------------------------------------")
    print(f"Speedup: {speedup:.2f}x")
    print(f"Autofit Output Identity: {'PASSED (100% Match)' if is_match else 'FAILED'}")
    if not is_match:
        print(f"Chi tiết sai lệch:\n{match_msg}")
    print("==================================================\n")

    # Cleanup temp benchmark outputs
    for path in (TEST_VIDEO, TEST_SRT, OUTPUT_A, OUTPUT_B):
        if os.path.exists(path):
            os.remove(path)

    if not is_match:
        sys.exit(1)


if __name__ == "__main__":
    main()
