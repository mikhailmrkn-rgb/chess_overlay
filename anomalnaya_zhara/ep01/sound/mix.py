"""Звук серии 1: голос + ровный мрачный фон (синтез) + редкие тихие эффекты (CC0, OpenGameArt).

Запуск: python3 mix.py
Вход:   ../audio/voice_trim.wav, ../anim/timings.json, cc0/*.ogg (звуки CC0, см. ИСТОЧНИКИ.txt)
Выход:  out/bed.wav (фон), out/sfx.wav (эффекты), out/voice.wav, out/mix_raw.wav (сумма до мастеринга)
Громкость фона: на 19 LU тише голоса (замер EBU R128 по ffmpeg ebur128).
"""
import json, os, re, subprocess
import numpy as np

SR = 48000
DUR = 60.0
N = int(SR * DUR)
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out'); os.makedirs(OUT, exist_ok=True)
CC0 = os.path.join(HERE, 'cc0')
rng = np.random.default_rng(7)


# ---------- ввод/вывод ----------
def load(path, start=0.0, dur=None):
    cmd = ['ffmpeg', '-v', 'error', '-ss', str(start)] + (['-t', str(dur)] if dur else []) + ['-i', path, '-f', 'f32le', '-ac', '2', '-ar', str(SR), '-']
    a = np.frombuffer(subprocess.run(cmd, capture_output=True, check=True).stdout, dtype=np.float32)
    return a.reshape(-1, 2).copy()


def save(path, x):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'f32le', '-ar', str(SR), '-ac', '2', '-i', '-', '-c:a', 'pcm_s24le', path],
                   input=np.ascontiguousarray(x, dtype=np.float32).tobytes(), check=True)


def lufs(x):
    """Интегральная громкость по EBU R128 (ffmpeg ebur128)."""
    r = subprocess.run(['ffmpeg', '-nostats', '-hide_banner', '-f', 'f32le', '-ar', str(SR), '-ac', '2', '-i', '-', '-af', 'ebur128=framelog=quiet', '-f', 'null', '-'],
                       input=np.ascontiguousarray(x, dtype=np.float32).tobytes(), capture_output=True)
    m = re.findall(r'I:\s+(-?[\d.]+) LUFS', r.stderr.decode())
    return float(m[-1])


def db(g):
    return 10 ** (g / 20)


def fade(x, fi=0.01, fo=0.05):
    x = x.copy(); n = len(x)
    a, b = min(n, int(fi * SR)), min(n, int(fo * SR))
    if a: x[:a] *= np.linspace(0, 1, a)[:, None]
    if b: x[-b:] *= np.linspace(1, 0, b)[:, None]
    return x


def active_rms_db(x):
    m = x.mean(axis=1); h = int(0.05 * SR)
    w = np.array([np.sqrt(np.mean(m[i:i + h] ** 2) + 1e-12) for i in range(0, len(m) - h, h)])
    d = 20 * np.log10(w)
    act = d[d > d.max() - 20]
    return 10 * np.log10(np.mean(10 ** (act / 10)))


def fft_filter(x, lo=None, hi=None):
    """Мягкий полосовой фильтр в частотной области (для синтеза)."""
    X = np.fft.rfft(x, axis=0); f = np.fft.rfftfreq(len(x), 1 / SR)
    g = np.ones_like(f)
    if lo: g *= 1 / np.sqrt(1 + (lo / np.maximum(f, 1e-3)) ** 4)
    if hi: g *= 1 / np.sqrt(1 + (f / hi) ** 4)
    return np.fft.irfft(X * (g[:, None] if x.ndim == 2 else g), n=len(x), axis=0)


# ---------- тайминги слов ----------
TM = json.load(open(os.path.join(HERE, '..', 'anim', 'timings.json'), encoding='utf-8'))
norm = lambda s: re.sub(r'[«»"!?.,:;…—]', '', s.lower().replace('ё', 'е'))


def S(word, n=1):
    c = 0
    for w in TM:
        if norm(w['w']) == norm(word):
            c += 1
            if c == n: return w['s']
    raise KeyError(word)


# ---------- ГОЛОС ----------
voice = np.zeros((N, 2), np.float32)
v = load(os.path.join(HERE, '..', 'audio', 'voice_trim.wav'))
v = fft_filter(v, lo=70)
voice[:min(N, len(v))] = v[:N]
L_voice = lufs(voice)

# ---------- ФОН: ровный мрачный гул (синтез, CC0) ----------
t = np.arange(N) / SR
bed = np.zeros(N)
for f0, amp, det in [(36.71, 1.0, 0.07), (73.42, 0.7, 0.11), (110.0, 0.35, 0.09), (146.83, 0.18, 0.13), (155.56, 0.05, 0.05)]:
    for d in (-det, det):
        ph = rng.uniform(0, 2 * np.pi)
        bed += amp * np.sin(2 * np.pi * (f0 + d) * t + ph)
bed *= 1 + 0.12 * np.sin(2 * np.pi * 0.05 * t) + 0.06 * np.sin(2 * np.pi * 0.13 * t + 1)
bed = np.tanh(bed * 0.6)
air = fft_filter(rng.standard_normal(N), lo=150, hi=900) * (1 + 0.3 * np.sin(2 * np.pi * 0.07 * t))
bed = bed / np.max(np.abs(bed)) + 0.35 * air / np.max(np.abs(air))
bed = np.stack([bed, np.roll(bed, int(0.011 * SR))], axis=1)  # лёгкая ширина стерео

# Гул кондиционеров: 50 Гц и гармоники + шум вентилятора. Обрывается, когда вспыхивает поле.
T_FIRE = S('вспыхнуло')
f_hum = np.where(t < T_FIRE, 50.0, 50.0 * np.maximum(0.4, 1 - (t - T_FIRE) / 0.35))
ph = 2 * np.pi * np.cumsum(f_hum) / SR
hum = sum(a * np.sin(k * ph) for k, a in [(1, 1.0), (2, 0.6), (3, 0.35), (4, 0.15), (6, 0.08)])
hum = hum * (1 + 0.15 * np.sin(2 * np.pi * 7.5 * t))
fanN = fft_filter(rng.standard_normal(N), lo=120, hi=1800)
hum = hum / np.max(np.abs(hum)) + 0.5 * fanN / np.max(np.abs(fanN))
env = np.zeros(N)


def seg(a, b, lvl, fi=0.4, fo=0.4):
    e = np.zeros(N); i0, i1 = int(a * SR), int(b * SR)
    e[i0:i1] = lvl
    k = int(fi * SR); e[i0:i0 + k] *= np.linspace(0, 1, k)
    k = int(fo * SR); e[i1 - k:i1] *= np.linspace(1, 0, k)
    return e


T2, T3, T5, T6, T7 = S('На') - 0.2, S('Руки') - 0.25, S('На', 2) - 0.2, S('пошла') - 0.25, S('Сама') - 0.2
env += seg(0.0, T2, 0.25)                 # колодец, небо — едва слышно
env += seg(T2 - 0.2, T5, 1.0)             # улица: громче всего
env[int(S('гудели') * SR):int(T3 * SR)] *= 1.6  # «гудели только кондиционеры»
env += seg(T5, T6, 0.35)                  # ферма — издалека
env += seg(T6, T7, 0.8)                   # двор Захара
env += seg(T7, T_FIRE + 0.4, 0.3, fo=0.05)  # поле — издалека
env[int((T_FIRE + 0.35) * SR):] = 0       # гул оборвался
hum = np.stack([hum * env] * 2, axis=1)

bed_all = bed + 0.55 * hum
# весь фон: мягкое появление и уход в конце
bed_all *= np.clip(t / 0.4, 0, 1)[:, None] * np.clip((DUR - t) / 1.2, 0, 1)[:, None]
L_bed = lufs(bed_all)
bed_all *= db((L_voice - 19.0) - L_bed)   # ровно на 19 LU тише голоса
# в начале голос тихий (шёпот) — фон тоже убираем, чтобы разница везде была около 19 дБ
duck = np.ones(N); i1, i2 = int((T2 - 0.6) * SR), int((T2 + 0.4) * SR)
duck[:i1] = db(-6); duck[i1:i2] = np.linspace(db(-6), 1, i2 - i1)
bed_all *= duck[:, None]

# ---------- ЭФФЕКТЫ ----------
sfx = np.zeros((N, 2), np.float32)
V_RMS = active_rms_db(voice)
log = []


def put(x, at, rel_db, name, pan=0.0):
    """Кладёт эффект в момент at; громкость — на rel_db дБ тише голоса (по активной части)."""
    x = fade(x, 0.005, 0.08) * db(V_RMS - rel_db - active_rms_db(x))
    x = x * np.array([np.sqrt(0.5 - pan / 2) * 1.41, np.sqrt(0.5 + pan / 2) * 1.41])
    i = int(at * SR); n = min(len(x), N - i)
    sfx[i:i + n] += x[:n]
    log.append(f'{at:6.2f} c  -{rel_db} дБ  {name}')


def synth_thud(f0=55, dur=0.6, noise=0.4):
    tt = np.arange(int(dur * SR)) / SR
    f = f0 * (1 + 1.5 * np.exp(-tt * 30))
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 7)
    x += noise * fft_filter(rng.standard_normal(len(tt)), hi=400) * np.exp(-tt * 18)
    return np.stack([x, x], 1)


def synth_clank(dur=0.8):
    tt = np.arange(int(dur * SR)) / SR
    x = sum(a * np.sin(2 * np.pi * f * tt) * np.exp(-tt * d) for f, a, d in [(523, 1, 6), (1347, 0.6, 9), (2210, 0.4, 12), (3170, 0.25, 16), (4410, 0.15, 20)])
    return np.stack([x, x], 1)


def synth_boom(dur=2.2):
    tt = np.arange(int(dur * SR)) / SR
    f = 48 * (1 - 0.35 * tt / dur)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 1.8) * (1 - np.exp(-tt * 60))
    x += 0.3 * fft_filter(rng.standard_normal(len(tt)), hi=250) * np.exp(-tt * 3)
    return np.stack([x, x], 1)


def loop_to(x, dur):
    out = x
    while len(out) < dur * SR:
        k = int(0.3 * SR)
        a, b = out[:-k], out[-k:] * np.linspace(1, 0, k)[:, None] + x[:k] * np.linspace(0, 1, k)[:, None]
        out = np.concatenate([a, b, x[k:]])
    return out[:int(dur * SR)]


C = lambda name: os.path.join(CC0, name)
# 1. ведро бьётся о сухое дно
put(synth_thud(70, 0.7, 0.6), S('по'), 10, 'синтез: глухой удар ведра о дно')
# 2. Лида подходит: шаги по песку
put(load(C('sand_footsteps.ogg'), 0.15, 1.9), S('Лида') - 0.15, 16, 'шаги по песку', pan=0.4)
# 3. корова падает
put(synth_thud(45, 0.9, 0.8), S('падали') + 0.45, 9, 'синтез: падение коровы')
# 4. Вика идёт к колодцу
put(load(C('footsteps_grass_sand.ogg'), 0.4, 1.4), S('пошла') - 0.05, 17, 'шаги по сухой траве', pan=-0.4)
# 5. скрип колодезного ворота
put(load(C('tree_creak.ogg'), 0.2, 1.7), S('замкнул') - 0.1, 17, 'деревянный скрип')
# 6. цепь
put(load(C('chain_winch.ogg'), 0.1, 0.9), S('цепь') - 0.05, 15, 'цепь звякнула')
# 7. ветер над полем
put(fade(load(C('wind_long.ogg'), 8.0, T_FIRE - T7 + 0.5), 1.0, 0.3), T7, 22, 'ветер над полем')
# 8. поле вспыхнуло: порыв + треск огня
put(load(C('wind_gust.ogg'), 1.0, 2.6), T_FIRE - 1.55, 12, 'порыв огня')
fire = loop_to(load(C('fire_crackle.ogg')), 6.6)
put(fade(fire, 0.05, 1.5), T_FIRE, 16, 'треск огня')
# 9. цепь сорвана
put(load(C('chain_winch.ogg'), 0.1, 1.3), S('сорвала') - 0.05, 13, 'цепь сорвана')
# 10. удар по ведру и всплеск яда
put(synth_clank(), S('выбил') + 0.1, 14, 'синтез: металлический удар ведра')
put(load(C('splash.ogg')), S('выбил') + 0.7, 14, 'всплеск')
# 11. яд шипит
put(fade(load(C('bubbles.ogg'), 0, 2.4), 0.2, 0.8), S('яд') - 0.2, 20, 'бульканье/шипение яда')
# 12. сердце: «три… дня… назад»
hb = load(C('heartbeat.ogg'), 0.1, 0.8)
put(hb, S('три') - 0.05, 9, 'удар сердца («три»)')
put(hb, S('назад') + 0.3, 9, 'удар сердца (после «назад»)')
# 13. дым: далёкий треск
put(fade(loop_to(load(C('fire_crackle.ogg')), 4.0), 0.8, 1.2), S('дыма') - 0.6, 24, 'далёкий треск огня')
# 14. шорох карты
put(load(C('paper_flip.ogg')), S('карте') - 0.3, 17, 'шорох бумаги')
# 15. финальный удар на «по одному»
put(synth_boom(), S('одному', 2), 8, 'синтез: низкий финальный удар')

save(os.path.join(OUT, 'voice.wav'), voice)
save(os.path.join(OUT, 'bed.wav'), bed_all)
save(os.path.join(OUT, 'sfx.wav'), sfx)
mix = voice + bed_all + sfx
save(os.path.join(OUT, 'mix_raw.wav'), mix)
L_bed2 = lufs(bed_all)
open(os.path.join(OUT, 'mix_report.txt'), 'w', encoding='utf-8').write(
    f'Голос: {L_voice:.1f} LUFS\nФон: {L_bed2:.1f} LUFS (разница {L_voice - L_bed2:.1f} LU)\n\nЭффекты:\n' + '\n'.join(log) + '\n')
print(f'voice {L_voice:.1f} LUFS, bed {L_bed2:.1f} LUFS, diff {L_voice - L_bed2:.1f} LU, effects {len(log)}')


# ---------- МАСТЕРИНГ: −14 LUFS, пики не выше −1,5 dBTP ----------
def master(src, dst, target=-14.0):
    g = target - lufs(mix)
    for _ in range(4):
        af = f'volume={g:.2f}dB,alimiter=limit=0.84:attack=3:release=60:level=false'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', src, '-af', af, '-ar', str(SR), '-c:a', 'pcm_s24le', dst], check=True)
        r = subprocess.run(['ffmpeg', '-nostats', '-hide_banner', '-i', dst, '-af', 'ebur128=peak=true:framelog=quiet', '-f', 'null', '-'], capture_output=True).stderr.decode()
        I = float(re.findall(r'I:\s+(-?[\d.]+) LUFS', r)[-1]); tp = float(re.findall(r'Peak:\s+(-?[\d.]+) dBFS', r)[-1])
        if abs(I - target) <= 0.1: break
        g += target - I
    return I, tp


I, TP = master(os.path.join(OUT, 'mix_raw.wav'), os.path.join(OUT, 'mix_master.wav'))
with open(os.path.join(OUT, 'mix_report.txt'), 'a', encoding='utf-8') as fh:
    fh.write(f'\nИтог после мастеринга: {I:.1f} LUFS, true peak {TP:.1f} dBTP\n')
print(f'master: {I:.1f} LUFS, true peak {TP:.1f} dBTP')
