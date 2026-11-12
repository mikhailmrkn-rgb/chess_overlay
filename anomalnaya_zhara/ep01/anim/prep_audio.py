"""Укорачивает две длинные паузы в озвучке и пересчитывает тайминги слов.

Вход:  ../audio/voice_raw.mp3, words_raw.json (тайминги слов от ElevenLabs)
Выход: ../audio/voice_trim.wav, timings.js (window.TIMINGS) и timings.json
"""
import json, re, subprocess, sys
import numpy as np

SR = 44100
CUTS = [(2.30, 2.65), (49.00, 49.40)]  # вырезаем тишину внутри пауз (секунды исходника)
XF = 0.015  # кроссфейд на стыке

raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', '../audio/voice_raw.mp3', '-f', 'f32le', '-ac', '1', '-ar', str(SR), '-'],
                     capture_output=True, check=True).stdout
a = np.frombuffer(raw, dtype=np.float32).copy()

pieces, prev = [], 0
for s, e in CUTS:
    pieces.append(a[int(prev * SR):int(s * SR)])
    prev = e
pieces.append(a[int(prev * SR):])
out = pieces[0]
n = int(XF * SR)
ramp = np.linspace(0, 1, n, dtype=np.float32)
for p in pieces[1:]:
    out = np.concatenate([out[:-n], out[-n:] * (1 - ramp) + p[:n] * ramp, p[n:]])

subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'f32le', '-ar', str(SR), '-ac', '1', '-i', '-', '-c:a', 'pcm_s16le', '../audio/voice_trim.wav'],
               input=out.tobytes(), check=True)


def shift(t):
    d = 0.0
    for s, e in CUTS:
        if t >= e:
            d += (e - s) - XF
        elif t > s:
            return s - d
    return t - d


words = json.load(open('words_raw.json', encoding='utf-8'))['words']
clean = []
for w in words:
    txt = w['text'].strip()
    if not txt or txt.startswith('[') or txt.endswith(']') or txt in ('—',):
        # тире и паузы — граница фразы для субтитров
        if clean and (txt == '—' or 'pause' in txt):
            clean[-1]['br'] = 1
        continue
    clean.append({'w': txt, 's': round(shift(w['start']), 3), 'e': round(shift(w['end']), 3)})

json.dump(clean, open('timings.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
open('timings.js', 'w', encoding='utf-8').write('window.TIMINGS = ' + json.dumps(clean, ensure_ascii=False) + ';\n')
print('words:', len(clean), 'audio:', round(len(out) / SR, 3), 's, last word ends', clean[-1]['e'])
