import sys, os
sys.stdout.reconfigure(encoding='utf-8')
from faster_whisper import WhisperModel
import subprocess

vid = r'C:\Users\This PC\Downloads\SaveTik.io_7658488718621216027.mp4'
raw_wav = 'test_snap_words.wav'
subprocess.run(['ffmpeg', '-y', '-ss', '90', '-to', '100', '-i', vid, '-ac', '1', '-ar', '16000', raw_wav], capture_output=True)

model = WhisperModel('large-v3', device='cuda', compute_type='int8_float16')
segs, _ = model.transcribe(raw_wav, beam_size=5, vad_filter=False, word_timestamps=True)

for s in segs:
    print(f'SEGMENT: [{s.start:.2f} -> {s.end:.2f}] {s.text}')
    if s.words:
        for w in s.words:
            print(f'   WORD: [{w.start:.2f} -> {w.end:.2f}] (dur {w.end-w.start:.2f}s) "{w.word}" prob={w.probability:.2f}')

if os.path.exists(raw_wav):
    os.remove(raw_wav)
