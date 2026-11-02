"""
Script kiểm thử Speaker Diarization trên nhiều video thực tế khác nhau
để kiểm tra độ ổn định của tỷ lệ CONFIDENT + UNCERTAIN và rà soát nguy cơ gộp nhiều người vào 1 câu.
"""

import os
import sys
import time
import subprocess
import re
import io

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

VIDEOS = [
    r"C:\Users\This PC\Downloads\snapdouyin.app-hd-1788256023320.mp4",
    r"C:\Users\This PC\Downloads\snapdouyin.app-hd-1788323442292.mp4",
    r"C:\Users\This PC\Downloads\snapdouyin.app-hd-1788601143740.mp4",
]

def analyze_debug_file(debug_file, srt_file):
    if not os.path.exists(debug_file):
        return {}

    with open(debug_file, "r", encoding="utf-8") as f:
        debug_content = f.read()

    with open(srt_file, "r", encoding="utf-8") as f:
        srt_content = f.read()

    # Thống kê tổng
    # Tổng: 8 câu | 🟢 CONFIDENT: 4 (50%) | 🟡 UNCERTAIN: 4 (50%) | 🔴 UNKNOWN: 0 (0%)
    m_summary = re.search(r"Tổng: (\d+) câu \| 🟢 CONFIDENT: (\d+) \(([0-9.]+)%\) \| 🟡 UNCERTAIN: (\d+) \(([0-9.]+)%\) \| 🔴 UNKNOWN: (\d+) \(([0-9.]+)%\)", debug_content)
    m_speakers = re.search(r"Phát hiện: (\d+) người nói", debug_content)

    # Đếm câu cảnh báo nghi vấn gộp giọng
    competing_lines = re.findall(r"⚠ Cảnh báo nghi vấn gộp giọng:.*", debug_content)

    # Đếm số câu có [Người 1], [Người 2] trong srt
    speaker_tags = re.findall(r"\[(Người \d+)\]", srt_content)
    spk_dist = {}
    for spk in speaker_tags:
        spk_dist[spk] = spk_dist.get(spk, 0) + 1

    total = int(m_summary.group(1)) if m_summary else len(speaker_tags)
    n_conf = int(m_summary.group(2)) if m_summary else 0
    n_unc = int(m_summary.group(4)) if m_summary else 0
    n_unk = int(m_summary.group(6)) if m_summary else 0
    n_spk = int(m_speakers.group(1)) if m_speakers else len(spk_dist)

    return {
        "total": total,
        "n_speakers": n_spk,
        "confident": n_conf,
        "uncertain": n_unc,
        "unknown": n_unk,
        "usable_ratio": (n_conf + n_unc) / total if total > 0 else 0,
        "multi_speaker_subs": len(competing_lines),
        "competing_details": competing_lines,
        "speaker_distribution": spk_dist,
    }


def main():
    hf_token = os.environ.get("HF_TOKEN", "")
    if not hf_token:
        print("⚠ Cảnh báo: Biến môi trường HF_TOKEN chưa được thiết lập. Diarization có thể thất bại.")

    results = []

    for i, vpath in enumerate(VIDEOS, 1):
        filename = os.path.basename(vpath)
        if not os.path.exists(vpath):
            print(f"Bỏ qua (không tìm thấy): {vpath}")
            continue

        print(f"\n{'='*70}")
        print(f"[{i}/{len(VIDEOS)}] BẮT ĐẦU TEST VIDEO: {filename}")
        print(f"{'='*70}")

        srt_out = f"benchmark_video_{i}.srt"
        debug_out = f"benchmark_video_{i}_diarization_debug.txt"

        cmd = [
            sys.executable,
            "dub_tool.py",
            "transcribe",
            vpath,
            "-o", srt_out,
            "--diarize",
            "--hf-token", hf_token,
        ]

        t0 = time.time()
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        duration = time.time() - t0

        print(proc.stdout)
        if proc.stderr:
            print("STDERR:")
            print(proc.stderr[-1000:])

        if proc.returncode != 0:
            print(f"✘ Lỗi khi xử lý {filename} (exit code {proc.returncode})")
            continue

        analysis = analyze_debug_file(debug_out, srt_out)
        analysis["filename"] = filename
        analysis["duration_sec"] = duration
        analysis["srt_out"] = srt_out
        analysis["debug_out"] = debug_out
        results.append(analysis)

    print("\n" + "="*85)
    print("BẢNG TỔNG HỢP KIỂM THỬ SPEAKER DIARIZATION TRÊN NHIỀU VIDEO")
    print("="*85)
    print(f"{'Video':<35} | {'Câu':<4} | {'Người':<6} | {'Tin cậy':<8} | {'Gộp giọng':<9} | {'Thời gian':<8}")
    print("-" * 85)
    for r in results:
        print(f"{r['filename'][:34]:<35} | {r['total']:<4} | {r['n_speakers']:<6} | {r['usable_ratio']*100:.1f}%    | {r['multi_speaker_subs']:<9} | {r['duration_sec']:.1f}s")
    print("-" * 85)

    print("\nCHI TIẾT PHÂN BỔ NGƯỜI NÓI & RÀ SOÁT GỘP GIỌNG:")
    for r in results:
        print(f"\n* Video: {r['filename']}")
        print(f"  - Phân bổ câu thoại: {r['speaker_distribution']}")
        print(f"  - Tỷ lệ: 🟢 CONFIDENT={r['confident']} ({r['confident']/r['total']*100:.0f}%), 🟡 UNCERTAIN={r['uncertain']} ({r['uncertain']/r['total']*100:.0f}%), 🔴 UNKNOWN={r['unknown']}")
        if r['multi_speaker_subs'] > 0:
            print(f"  - ⚠ Các câu bị nghi vấn gộp nhiều người ({r['multi_speaker_subs']} câu):")
            for c in r['competing_details'][:5]:
                print(f"      {c}")
        else:
            print("  - ✔ Tuyệt vời: KHÔNG có câu nào bị gộp nhiều người nói vào 1 câu!")

if __name__ == "__main__":
    main()
