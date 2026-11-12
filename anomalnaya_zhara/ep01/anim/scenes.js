// «Аномальная жара», серия 1 — покадровая анимация.
// frameSVG(t) возвращает содержимое кадра 1080×1920 в момент t (секунды).
// Все действия привязаны к словам озвучки: S('слово', n) — начало n-го вхождения слова, E(...) — конец.
(function (global) {
  const A = global.AZ, P = A.P, W = 1080, H = 1920;
  const TM = global.TIMINGS;

  // ---------- время и слова ----------
  const norm = (s) => s.toLowerCase().replace(/ё/g, 'е').replace(/[«»"!?.,:;…—]/g, '');
  function wt(text, n, key) {
    n = n || 1; let c = 0;
    for (const w of TM) if (norm(w.w) === norm(text) && ++c === n) return w[key];
    throw new Error('Нет слова в озвучке: ' + text + ' #' + n);
  }
  const S = (t, n) => wt(t, n, 's'), E = (t, n) => wt(t, n, 'e');

  // ---------- математика ----------
  const clamp = (x, a, b) => Math.max(a == null ? 0 : a, Math.min(b == null ? 1 : b, x));
  const lerp = (a, b, k) => a + (b - a) * k;
  const prog = (t, a, b) => clamp((t - a) / (b - a));
  const ease = (k) => (k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2);
  const easeOut = (k) => 1 - Math.pow(1 - k, 3);
  const easeIn = (k) => k * k * k;
  const back = (k) => { const c1 = 1.9, c3 = c1 + 1; return 1 + c3 * Math.pow(k - 1, 3) + c1 * Math.pow(k - 1, 2); };
  const f = (n) => Math.round(n * 100) / 100;
  const noise = (t, s) => Math.sin(t * 12.9898 + s * 78.233) * 0.5 + Math.sin(t * 7.13 + s * 3.31) * 0.3 + Math.sin(t * 23.7 + s * 1.7) * 0.2;
  function shake(t, t0, dur, amp) {
    const k = prog(t, t0, t0 + dur);
    if (k <= 0 || k >= 1) return [0, 0];
    const a = amp * (1 - k);
    return [noise(t * 4, 1) * a, noise(t * 4, 2) * a];
  }
  const pulse = (t, t0, dur) => { const k = prog(t, t0, t0 + dur); return k <= 0 || k >= 1 ? 0 : 1 - k; };

  // ---------- сборка ----------
  const place = (svg, x, y, s, rot) => `<g transform="translate(${f(x)} ${f(y)})${rot ? ` rotate(${f(rot)})` : ''} scale(${f(s == null ? 1 : s)})">${svg}</g>`;
  // камера: (cx, cy) — точка мира в центре кадра, z — зум
  const cam = (svg, cx, cy, z, sh) => {
    z = Math.max(1, z);
    cx = clamp(cx, W / 2 / z, W - W / 2 / z); cy = clamp(cy, H / 2 / z, H - H / 2 / z);
    return camRaw(svg, cx, cy, z, sh);
  };
  const camRaw = (svg, cx, cy, z, sh) => `<g transform="translate(${f(W / 2 + (sh ? sh[0] : 0))} ${f(H / 2 + (sh ? sh[1] : 0))}) scale(${f(z)}) translate(${f(-cx)} ${f(-cy)})">${svg}</g>`;
  const sil = (svg, col) => svg.replace(/(fill|stroke)="#[0-9a-fA-F]{3,6}"/g, `$1="${col}"`);
  const rect = (col, op) => `<rect x="-200" y="-200" width="${W + 400}" height="${H + 400}" fill="${col}" opacity="${f(op)}"/>`;

  const cache = {};
  const once = (k, fn) => cache[k] || (cache[k] = fn());

  // прямая кинематика: где окажется кисть
  function handWorld(c, side, arm, ox, oy, s) {
    const sc = c.scale * s, r = (d) => (d * Math.PI) / 180;
    const x = side * (c.sw - 13) - Math.sin(r(arm[0])) * 96 - Math.sin(r(arm[0] + arm[1])) * 88;
    const y = -412 + Math.cos(r(arm[0])) * 96 + Math.cos(r(arm[0] + arm[1])) * 88;
    return [ox + x * sc, oy + y * sc];
  }
  // походка (плоская, «на месте» + покачивание)
  function walk(ph, amp) {
    amp = amp || 16; const s = Math.sin(ph);
    return { legL: [s * amp, Math.max(0, -s) * amp], legR: [-s * amp, Math.max(0, s) * amp], armL: [8 - s * amp * 0.8, -8], armR: [-8 + s * amp * 0.8, 8], bob: Math.abs(Math.cos(ph)) * 10 };
  }
  const tremble = (t, amp) => [noise(t * 9, 3) * amp, noise(t * 11, 4) * amp];

  // ---------- живые слои ----------
  function dustLayer(t, seed, n, col, vx, vy, rmax) {
    const R = A.rng(seed); let s = '';
    for (let i = 0; i < n; i++) {
      const x0 = R() * W, y0 = R() * H, sp = 0.4 + R(), r = 1.5 + R() * (rmax || 4), op = 0.15 + R() * 0.4;
      const x = ((x0 + (vx || 18) * sp * t + Math.sin(t * 0.8 + i) * 12) % W + W) % W;
      const y = ((y0 + (vy || -10) * sp * t) % H + H) % H;
      s += `<circle cx="${f(x)}" cy="${f(y)}" r="${f(r)}" fill="${col}" opacity="${f(op * (0.7 + 0.3 * Math.sin(t * 2 + i)))}"/>`;
    }
    return s;
  }
  function hazeLayer(t, y0, y1, op) {
    let s = '';
    for (let y = y0, i = 0; y < y1; y += 52, i++) {
      const ph = t * 60 + i * 37;
      s += `<path d="M${f(-200 + (ph % 240))} ${f(y + Math.sin(t * 1.7 + i) * 6)} q 60 -12 120 0 t 120 0 t 120 0 t 120 0 t 120 0 t 120 0 t 120 0 t 120 0 t 120 0 t 120 0 t 120 0" stroke="#ffe0b0" stroke-width="3" fill="none" opacity="${f((op || 0.08) * (0.6 + 0.4 * Math.sin(t * 2.3 + i)))}"/>`;
    }
    return s;
  }
  function emberLayer(t, seed, n) {
    const R = A.rng(seed); let s = '';
    for (let i = 0; i < n; i++) {
      const x0 = R() * W, sp = 80 + R() * 220, ph = R() * 10, r = 2 + R() * 5;
      const y = H - (((t + ph) * sp) % (H + 200));
      const x = x0 + Math.sin(t * 2 + i) * 30;
      s += `<circle cx="${f(x)}" cy="${f(y)}" r="${f(r)}" fill="${i % 3 ? P.ember : P.fireL}" opacity="${f(0.5 + 0.5 * Math.sin(t * 15 + i))}"/>`;
    }
    return s;
  }
  function ashLayer(t, seed, n) {
    const R = A.rng(seed); let s = '';
    for (let i = 0; i < n; i++) {
      const x0 = R() * W, sp = 40 + R() * 90, ph = R() * 30, r = 2 + R() * 4;
      const y = ((t + ph) * sp) % (H + 100) - 50;
      s += `<ellipse cx="${f(x0 + Math.sin(t * 1.3 + i) * 40)}" cy="${f(y)}" rx="${f(r)}" ry="${f(r * 0.6)}" fill="#cfc2b5" opacity="${f(0.25 + 0.3 * R())}"/>`;
    }
    return s;
  }
  function puff(t, t0, x, y, col, size) {
    const k = prog(t, t0, t0 + 0.7);
    if (k <= 0 || k >= 1) return '';
    let s = '';
    for (let i = 0; i < 9; i++) {
      const a = (i / 9) * Math.PI * 2, d = easeOut(k) * (size || 160);
      s += `<circle cx="${f(x + Math.cos(a) * d * 1.6)}" cy="${f(y + Math.sin(a) * d * 0.5 - k * 40)}" r="${f(30 + k * 40)}" fill="${col || '#b88a58'}" opacity="${f(0.55 * (1 - k))}"/>`;
    }
    return s;
  }
  function sparkle(t, t0, x, y, size) {
    const k = prog(t, t0, t0 + 0.45);
    if (k <= 0 || k >= 1) return '';
    const s = (size || 40) * Math.sin(k * Math.PI);
    return `<g transform="translate(${f(x)} ${f(y)}) rotate(${f(k * 90)})"><path d="M0 ${-s} L${s * 0.18} ${-s * 0.18} L${s} 0 L${s * 0.18} ${s * 0.18} L0 ${s} L${-s * 0.18} ${s * 0.18} L${-s} 0 L${-s * 0.18} ${-s * 0.18} Z" fill="#fff6dc"/></g>`;
  }
  function fan(t, x, y, r, speed) {
    const a = (t * (speed || 900)) % 360;
    let s = `<g transform="translate(${f(x)} ${f(y)}) rotate(${f(a)})">`;
    for (let i = 0; i < 3; i++) s += `<path d="M0 0 Q${f(r * 0.5)} ${f(-r * 0.4)} 0 ${f(-r * 0.95)} Q${f(-r * 0.25)} ${f(-r * 0.45)} 0 0 Z" fill="#8a857a" transform="rotate(${i * 120})"/>`;
    return s + `<circle r="${f(r * 0.18)}" fill="#55524b"/></g>`;
  }
  function led(t, x, y, on, phase) {
    const lit = on && ((t * 1.4 + (phase || 0)) % 1) < 0.55;
    return `<circle cx="${x}" cy="${y}" r="4.5" fill="${lit ? P.led : '#3a1a18'}"/>` + (lit ? `<circle cx="${x}" cy="${y}" r="14" fill="${P.led}" opacity="0.35"/>` : '');
  }
  function humWaves(t, x, y, amp) {
    let s = '';
    for (let i = 0; i < 3; i++) {
      const k = (t * 1.2 + i / 3) % 1, r = 60 + k * 120;
      s += `<path d="M${f(x - r)} ${f(y - r * 0.3)} A${f(r)} ${f(r)} 0 0 1 ${f(x + r)} ${f(y - r * 0.3)}" stroke="#ffd9a8" stroke-width="4" fill="none" opacity="${f((1 - k) * 0.35 * amp)}"/>`;
    }
    return s;
  }
  function bigText(txt, x, y, size, col, k) {
    const sc = back(clamp(k));
    return `<g transform="translate(${x} ${y}) scale(${f(sc)})" opacity="${f(clamp(k * 3))}"><text text-anchor="middle" font-family="Inter Display, Inter, sans-serif" font-weight="900" font-size="${size}" fill="${col}" stroke="#140a06" stroke-width="${size * 0.12}" paint-order="stroke" stroke-linejoin="round">${txt}</text></g>`;
  }

  // ---------- готовые фоны (кэш) ----------
  const bg = {
    well: () => once('well', () => A.BG.wellTop()),
    street: () => once('street', () => A.BG.street({ led: false })),
    farm: () => once('farm', () => A.BG.farm()),
    yard: () => once('yard', () => A.BG.yard({ led: false })),
    yardOpen: () => once('yardOpen', () => A.BG.yard({ led: false, chained: false })),
    field: () => once('field', () => A.BG.field()),
    fireSky: () => once('fireSky', () => { const s = A.BG.fire(); return s.slice(0, s.indexOf('<g transform="translate(0 1080)">')); }),
    smoke: () => once('smoke', () => A.BG.smoke()),
    ground: () => once('ground', () => {
      let s = `<rect width="${W}" height="${H}" fill="#4a2d18"/>`;
      const R = A.rng(88);
      for (let i = 0; i < 40; i++) {
        let x = R() * W, y = R() * H, d = `M${f(x)} ${f(y)}`;
        for (let k = 0; k < 5; k++) { x += (R() - 0.5) * 160; y += (R() - 0.5) * 160; d += ` L${f(x)} ${f(y)}`; }
        s += `<path d="${d}" stroke="#2b190d" stroke-width="${f(3 + R() * 5)}" fill="none" stroke-linecap="round"/>`;
      }
      return s;
    }),
  };
  // стебли травы у лужи (горят от яда)
  function tufts(t, burnK) {
    const R = A.rng(99); let s = '';
    const col = burnK > 0 ? `rgb(${Math.round(lerp(185, 25, burnK))},${Math.round(lerp(139, 20, burnK))},${Math.round(lerp(58, 15, burnK))})` : P.straw;
    for (let i = 0; i < 18; i++) {
      const a = (i / 18) * Math.PI * 2 + R() * 0.3, rr = 330 + R() * 60;
      const x = 540 + Math.cos(a) * rr, y = 1150 + Math.sin(a) * rr * 0.62;
      for (let k = 0; k < 4; k++) {
        const len = 40 + R() * 50, lean = (R() - 0.5) * 40 + Math.sin(t * 2 + i) * 4;
        s += `<path d="M${f(x + k * 8)} ${f(y)} q ${f(lean * 0.3)} ${f(-len * 0.5)} ${f(lean)} ${f(-len * (1 - burnK * 0.35))}" stroke="${col}" stroke-width="5" fill="none" stroke-linecap="round"/>`;
      }
    }
    return s;
  }

  // пучок колосьев перед ногами (герой «в пшенице»)
  function tuftsAt(x, y, w, sc, seed) {
    const R = A.rng(seed); let s = '';
    for (let i = 0; i < 22; i++) {
      const xx = x - w + R() * w * 2, len = (40 + R() * 50) * sc * 1.6, lean = (R() - 0.5) * len * 0.5;
      s += `<path d="M${f(xx)} ${f(y + 8 * sc)} q ${f(lean * 0.3)} ${f(-len * 0.5)} ${f(lean)} ${f(-len)}" stroke="${R() > 0.5 ? P.straw : P.strawL}" stroke-width="${f(Math.max(1.5, 6 * sc))}" fill="none" stroke-linecap="round"/>`;
    }
    return s;
  }

  // ---------- персонажи с готовыми настройками ----------
  const vika = (pose, x, y, s) => place(A.human(A.VIKA, pose), x, y, s);
  const lida = (pose, x, y, s) => place(A.human(A.LIDA, pose), x, y, s);
  const zakhar = (pose, x, y, s) => place(A.human(A.ZAKHAR, pose), x, y, s);
  function vikaHead(face, opts) {
    const V = A.VIKA;
    return A.head(Object.assign({ rx: V.rx, ry: V.ry, skin: V.skin, skinD: V.skinD, face, hairBack: V.hairBack, hairFront: V.hairFront, lip: V.lip, brow: V.browCol }, opts || {}));
  }
  function zakharHead(face, front, opts) {
    const Z = A.ZAKHAR;
    return A.head(Object.assign({ rx: Z.rx, ry: Z.ry, skin: Z.skin, skinD: Z.skinD, face, faceOver: { mouth: 'none' }, hairBack: Z.hairBack, hairFront: front, cheeks: true, brow: Z.browCol, browW: 6 }, opts || {}));
  }
  // крупный план: голова в точке (x, y), тело уходит за нижний край
  const headY = (c) => -428 - 26 - c.ry + 10;
  const closeUp = (c, pose, x, y, s) => place(A.human(c, pose), x, y - headY(c) * c.scale * s, s);
  const pitch = (arm) => `<g transform="rotate(${f(-(arm[0] + arm[1]))}) translate(0 110)">${A.pitchfork(0.8)}</g>`;

  // ---------- ТАЙМЛАЙН ----------
  const T1b = S('Я') - 0.15;              // небо и солнце
  const T2 = S('На') - 0.2;               // улица
  const T3 = S('Руки') - 0.25;            // Вика
  const T4 = S('Лида') - 0.2;             // Лида
  const T5 = S('На', 2) - 0.2;            // ферма
  const T6 = S('пошла') - 0.25;           // двор Захара
  const T7 = S('Сама') - 0.2;             // поле, бутылка
  const T8 = S('через') - 0.2;            // пожар
  const T9 = S('сорвала') - 0.3;          // ночь у колодца
  const T10 = S('Он') - 0.15;             // яд
  const T11 = S('дыма') - 0.55;              // дым, Лида
  const T12 = S('карте') - 0.3;           // карта
  const TEND = E('одному', 2) - 0.25;     // титр
  const SCENES = { T1b, T2, T3, T4, T5, T6, T7, T8, T9, T10, T11, T12, TEND };

  // 1а. Ведро падает в сухой колодец
  function sWell(t) {
    const tHit = S('по');
    const k = prog(t, 0.0, tHit), d = Math.pow(k, 1.7);
    const sc = t < tHit ? lerp(2.4, 0.3, d) : 0.3;
    const sp = (t < tHit ? 1 - d : 0) * 40;
    const bx = 540 + Math.sin(t * 5) * sp, by = 900 + Math.cos(t * 4) * sp * 0.5;
    const rot = t < tHit ? t * 160 : tHit * 160 + 12;
    const bucketTop = `<circle r="70" fill="${P.metalD}"/><circle r="58" fill="#26231f"/><circle r="58" fill="none" stroke="${P.metal}" stroke-width="6"/><path d="M-70 0 Q0 -95 70 0" stroke="#3a3935" stroke-width="7" fill="none"/>`;
    let s = bg.well();
    s += place(bucketTop, bx, by, sc, rot);
    s += puff(t, tHit, 540, 905, '#a8784a', 70);
    s += dustLayer(t, 11, 40, '#e9c690', 6, 14, 3);
    const z = 1 + 0.12 * prog(t, 0, T1b);
    return cam(s, 540, 900, z, shake(t, tHit, 0.35, 16));
  }
  // 1б. Солнце-глаз сужает зрачок
  function sSun(t) {
    const kz = prog(t, S('думала'), E('жара'));
    let s = `<defs><linearGradient id="skyS" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${P.skyTop}"/><stop offset="0.55" stop-color="${P.skyMid}"/><stop offset="1" stop-color="${P.skyLow}"/></linearGradient></defs><rect x="-200" y="-200" width="${W + 400}" height="${H + 400}" fill="url(#skyS)"/>`;
    s += place(A.sunEye(200, { pupil: lerp(0.26, 0.08, ease(kz)) }), 540, 820, 1 + 0.03 * Math.sin(t * 3) + 0.12 * pulse(t, S('жара'), 0.8));
    s += hazeLayer(t, 1150, 1900, 0.12);
    const kt = easeOut(prog(t, S('просто') - 0.1, S('просто') + 0.35));
    s += place(A.thermometer(), lerp(1300, 900, kt), 1180, 1.25);
    s += dustLayer(t, 12, 30, '#ffe2b0', 10, -14, 3);
    s += rect('#fff2d2', 0.45 * pulse(t, S('жара'), 0.5));
    return cam(s, 540, 960, 1 + 0.1 * prog(t, T1b, T2));
  }
  // 2. Улица: ДЕНЬ 10, гудят кондиционеры
  function sStreet(t) {
    let s = bg.street();
    s += fan(t, 330, 1030, 22) + fan(t, 712, 1030, 19);
    s += led(t, 385, 1006, true, 0) + led(t, 759, 1009, true, 0.37);
    const hum = prog(t, S('гудели') - 0.2, S('гудели') + 0.3);
    s += humWaves(t, 340, 990, hum) + humWaves(t + 0.4, 720, 995, hum);
    s += hazeLayer(t, 1000, 1500, 0.1) + dustLayer(t, 21, 60, '#f0c890', 20, -6);
    const kd = prog(t, S('десятый') - 0.05, S('десятый') + 0.3), out = 1 - prog(t, S('деревня') + 0.2, S('деревня') + 0.5);
    if (kd > 0 && out > 0) s += `<g opacity="${f(out)}">${bigText('ДЕНЬ 10', 540, 600, 190, '#ff8a3a', kd)}</g>`;
    const kz = ease(prog(t, S('кондиционеры') - 0.1, S('кондиционеры') + 0.5));
    const cx = lerp(540, 345, kz), cy = lerp(1000, 1025, kz), z = lerp(1 + 0.05 * prog(t, T2, T3), 2.3, kz);
    const jit = kz > 0.5 ? [noise(t * 30, 5) * 2.5, noise(t * 30, 6) * 2.5] : [0, 0];
    return cam(s, cx, cy, z, jit);
  }
  // 3. Вика прячет дрожащие руки
  function sVika(t) {
    let s = bg.street();
    s += fan(t, 330, 1030, 22) + fan(t, 712, 1030, 19) + led(t, 385, 1006, true, 0) + led(t, 759, 1009, true, 0.37);
    s += hazeLayer(t, 1000, 1500, 0.09) + dustLayer(t, 22, 50, '#f0c890', 20, -6);
    const trem = pulse(t, S('дрожали') - 0.05, 1.7) > 0 ? 7 : 2.5;
    const tr = tremble(t, trem);
    const kp = ease(prog(t, S('прятала') - 0.05, E('карман')));
    const kup = ease(prog(t, T3, S('Руки') + 0.35));
    const armR = [lerp(lerp(-8, 10, kup), 3, kp) + tr[0] * (1 - kp), lerp(lerp(6, 150, kup), 2, kp) + tr[1] * (1 - kp)];
    const hide = prog(t, S('прятала'), S('прятала') + 0.2) * (1 - prog(t, E('карман'), E('карман') + 0.3));
    const look = [lerp(-3, Math.sin(t * 5) * 6, hide), lerp(5, 2, kp)];
    const tl = tremble(t + 3, 1.5);
    const pose = { armL: [10 + tl[0], -4 + tl[1]], armR, face: 'sick', look, sweat: true, front: A.VIKA.pocket(0.25) };
    const VX = 540, VY = 1640, VS = 1.45;
    s += vika(pose, VX, VY, VS);
    const hp = handWorld(A.VIKA, 1, armR, VX, VY, VS);
    if (trem > 3) {
      s += `<g stroke="#ffe0b0" stroke-width="4" fill="none" opacity="0.8" stroke-linecap="round"><path d="M${f(hp[0] - 40)} ${f(hp[1] - 20)} q -10 20 0 40"/><path d="M${f(hp[0] - 56)} ${f(hp[1] - 28)} q -12 28 0 56"/><path d="M${f(hp[0] + 40)} ${f(hp[1] - 20)} q 10 20 0 40"/></g>`;
    }
    const pocket = [VX + 48 * VS, VY - 270 * VS];
    s += sparkle(t, S('воды') - 0.05, pocket[0] - 2, pocket[1] - 30, 46);
    const k1 = ease(prog(t, T3, S('дрожали') + 0.3)), k2 = ease(prog(t, S('последней') - 0.1, S('воды') + 0.1));
    let cx = lerp(540, 560, k1), cy = lerp(1200, 1100, k1), z = lerp(1.0, 1.6, k1);
    const kback = ease(prog(t, S('прятала') - 0.2, S('прятала') + 0.4));
    cx = lerp(cx, 560, kback); cy = lerp(cy, 1250, kback); z = lerp(z, 1.15, kback);
    cx = lerp(cx, pocket[0], k2); cy = lerp(cy, pocket[1] + 10, k2); z = lerp(z, 3.0, k2);
    return cam(s, cx, cy, z);
  }
  // 4. Лида считает бинты
  function sLida(t) {
    let s = bg.street();
    s += fan(t, 330, 1030, 22) + fan(t, 712, 1030, 19) + led(t, 385, 1006, true, 0) + led(t, 759, 1009, true, 0.37);
    s += hazeLayer(t, 1000, 1500, 0.09) + dustLayer(t, 23, 50, '#f0c890', 20, -6);
    const tr = tremble(t, 1.5);
    s += vika({ armL: [10 + tr[0], -4 + tr[1]], armR: [3, 2], face: 'sick', look: [lerp(0, 6, prog(t, T4 + 0.3, T4 + 0.7)), 2], sweat: true, front: A.VIKA.pocket(0.25) }, 330, 1660, 1.35);
    const kw = prog(t, T4, S('соседка-медсестра') + 0.6);
    const x = lerp(1250, 770, easeOut(kw));
    let pose;
    if (kw < 1) {
      const w = walk(t * 9, 14);
      pose = { legL: w.legL, legR: w.legR, armL: w.armL, armR: w.armR, face: 'worried', look: [-4, 2] };
      s += lida(pose, x, 1660 - w.bob, 1.35);
    } else {
      const tap = Math.sin(t * 18) * 5 * prog(t, S('шепотом'), S('шепотом') + 0.1);
      const talking = t > S('шепотом') && t < E('бинты') && Math.sin(t * 22) > 0;
      pose = { armL: [0, -74], armR: [0, 70 + tap], face: talking ? 'whisper' : 'neutral', look: [0, 6], handL: `<g transform="rotate(74) translate(-6 -4)">${A.bandage(0.9)}</g>` };
      s += lida(pose, x, 1660, 1.35);
    }
    for (const [wd, txt, dx] of [['пересчитывала', '41…', -90], ['бинты', '42…', 90]]) {
      const k = prog(t, S(wd), S(wd) + 0.25), o = 1 - prog(t, S(wd) + 0.9, S(wd) + 1.3);
      if (k > 0 && o > 0) s += `<g opacity="${f(o)}" transform="translate(0 ${f(-40 * prog(t, S(wd), S(wd) + 1.3))})">${bigText(txt, 770 + dx, 860, 110, '#f2e2c6', k)}</g>`;
    }
    return cam(s, 560, 1180, 1.02 + 0.05 * prog(t, T4, T5));
  }
  // 5. Ферма: корова падает и дрожит
  function sFarm(t) {
    const tF = S('падали'), tDown = tF + 0.45, tClose = S('точь-в-точь') - 0.05;
    if (t >= tClose) { // крупно: дрожащая рука Вики
      let s = bg.farm() + hazeLayer(t, 900, 1300, 0.1) + dustLayer(t, 31, 50, '#f0c890', 20, -6);
      const tr = tremble(t, 4);
      s += closeUp(A.VIKA, { armL: [-10 + tr[0], -150 + tr[1]], armR: [-6, 4], face: 'sick', look: [-2, 6], sweat: true }, 560, 860, 2.4);
      return cam(s, 540, 1050, 1.0 + 0.06 * prog(t, tClose, T6));
    }
    let s = bg.farm() + hazeLayer(t, 900, 1300, 0.1) + dustLayer(t, 32, 70, '#f0c890', 22, -6);
    const tr2 = tremble(t, 1.5);
    s += place(A.cow('down'), 250 + tr2[0], 1335 + tr2[1], 0.6);
    if (t < tDown) {
      const k = easeIn(prog(t, tF, tDown));
      s += place(A.cow('stand'), 640 + k * 40, 1420 + k * 50, 1.15, Math.sin(t * 7) * 1.2 + k * 28);
    } else {
      const amp = t > S('дрожали', 2) - 0.05 ? 5 : 1.5;
      const tr = tremble(t * 1.5, amp);
      s += place(A.cow('down'), 620 + tr[0], 1460 + tr[1], 1.15);
    }
    s += puff(t, tDown, 620, 1450, '#b88a58', 200);
    return cam(s, 560, 1250, 1 + 0.06 * prog(t, T5, tClose), shake(t, tDown, 0.35, 14));
  }
  // 6. Двор Захара: цепь и треснувшие губы
  function sYard(t) {
    const tClose = S('сам') - 0.12;
    if (t >= tClose) {
      let s = cam(bg.yard(), 600, 1100, 1.5) + rect('#000', 0.35) + dustLayer(t, 41, 40, '#f0c890', 16, -8);
      const kl = prog(t, S('облизывал'), E('облизывал') + 0.1);
      const lick = kl > 0 && kl < 1 ? lerp(-13, 13, kl) : null;
      const tr = tremble(t, 0.8);
      s += closeUp(A.ZAKHAR, { face: 'grim', hairFront: A.ZAKHAR.front({ lick }), look: [lerp(0, -6, prog(t, S('треснувшие'), S('треснувшие') + 0.3)), 0], armL: [4, -2], armR: [-4, 2] }, 540 + tr[0], 820 + tr[1], 3.0);
      return cam(s, 540, lerp(960, 1010, prog(t, tClose, T7)), 1 + 0.14 * ease(prog(t, tClose, T7)));
    }
    let s = bg.yard() + fan(t, 629, 860, 24) + led(t, 690, 833, true, 0.2) + hazeLayer(t, 950, 1300, 0.08) + dustLayer(t, 42, 50, '#f0c890', 18, -6);
    const kv = prog(t, S('пошла') - 0.1, E('колодцу'));
    const vx = lerp(-160, 230, easeOut(kv));
    if (kv < 1) { const w = walk(t * 9, 14); s += vika({ legL: w.legL, legR: w.legR, armL: w.armL, armR: w.armR, face: 'worried', look: [5, 1], front: A.VIKA.pocket(0.25) }, vx, 1810 - w.bob, 1.2); }
    else s += vika({ face: 'worried', look: [5, 1], front: A.VIKA.pocket(0.25) }, vx, 1810, 1.2);
    const kz = prog(t, S('Захар') - 0.15, S('Захар') + 0.35);
    if (kz > 0) {
      const zx = lerp(1250, 850, easeOut(kz));
      const armR = [-24, -48];
      if (kz < 1) { const w = walk(t * 10, 12); s += zakhar({ legL: w.legL, legR: w.legR, armL: w.armL, armR, face: 'grim', look: [-5, 0], handR: pitch(armR) }, zx, 1810 - w.bob, 1.05); }
      else s += zakhar({ armL: [6, -4], armR, face: 'grim', look: [-5, 0], handR: pitch(armR) }, zx, 1810, 1.05);
    }
    s += sparkle(t, S('цепь') - 0.05, 690, 1445, 50);
    const kc = ease(prog(t, S('замкнул') - 0.1, S('замкнул') + 0.45));
    return cam(s, lerp(540, 650, kc), lerp(1250, 1450, kc), lerp(1, 2.0, kc), shake(t, S('цепь'), 0.25, 8));
  }
  // 7. Поле: последняя бутылка
  function sField(t) {
    const tClose = S('Себе') - 0.1;
    if (t >= tClose) {
      let s = cam(bg.field(), 450, 1300, 1.6) + rect('#000', 0.3) + dustLayer(t, 51, 40, '#ffd9a0', 14, -8);
      const sw = Math.sin(t * 1.6) * 2;
      s += `<g transform="rotate(${f(sw)} 540 1400)">` + closeUp(Object.assign({}, A.VIKA, { crackedLips: true, faceOver: { mouth: 'none' } }), { face: 'sick', sweat: true, look: [0, 4], front: A.VIKA.pocket(0) }, 540, 820, 2.8) + `</g>`;
      s += rect('#3a3a3a', 0.22 * prog(t, tClose, tClose + 0.8));
      return cam(s, 540, 960, 1 + 0.1 * prog(t, tClose, T8));
    }
    let s = bg.field() + hazeLayer(t, 950, 1150, 0.1) + dustLayer(t, 52, 40, '#ffd9a0', 16, -8);
    const tGive = S('отдала'), tTake = S('бутылку') + 0.05, tRun = S('Беги');
    const kv = ease(prog(t, tGive - 0.05, tGive + 0.35)) * (1 - ease(prog(t, tTake + 0.1, tTake + 0.5)));
    const vArm = [lerp(-8, -50, kv), lerp(6, -10, kv)];
    const vHand = t < tTake ? `<g transform="rotate(${f(-(vArm[0] + vArm[1]))}) translate(0 50)">${A.bottle(0.25, 0.7)}</g>` : '';
    s += vika({ armL: [10, -4], armR: vArm, face: 'sick', look: [5, 2], sweat: true, bodyTilt: Math.sin(t * 2) * 2.5, handR: vHand }, 330, 1770, 1.25);
    const kl = ease(prog(t, S('Лиде') - 0.05, S('Лиде') + 0.35));
    if (t < tRun) {
      const lArm = t < tTake ? [lerp(8, 45, kl), lerp(-8, 10, kl)] : [lerp(45, 10, prog(t, tTake, tTake + 0.4)), lerp(10, -70, prog(t, tTake, tTake + 0.4))];
      const lHand = t >= tTake ? `<g transform="rotate(${f(-(lArm[0] + lArm[1]))}) translate(0 50)">${A.bottle(0.25, 0.7)}</g>` : '';
      s += lida({ armL: lArm, armR: [-8, 6], face: 'worried', look: [-5, 2], handL: lHand }, 760, 1770, 1.25);
    } else {
      const k = prog(t, tRun + 0.05, tClose + 0.2), ke = easeOut(k);
      const w = walk(t * 13, 20);
      const lx = lerp(760, 790, ke), ly = lerp(1770, 1068, ke), ls = lerp(1.25, 0.16, ke);
      const fig = lida({ back: true, legL: w.legL, legR: w.legR, armL: w.armL, armR: w.armR }, lx, ly - w.bob * ls, ls);
      const clipY = ly - lerp(0, 210, clamp(k * 4)) * ls * 0.92;
      s += `<defs><clipPath id="lidaClip"><rect x="0" y="-100" width="${W}" height="${f(clipY + 100)}"/></clipPath></defs><g clip-path="url(#lidaClip)">${fig}</g>`;
      s += tuftsAt(lx, clipY, 150 * ls, ls, 7);
    }
    return cam(s, 540, 1250, 1 + 0.05 * prog(t, T7, tClose) + 0.12 * ease(prog(t, tRun, tClose)));
  }
  // 8. Поле вспыхнуло
  function sFire(t) {
    const tF = S('вспыхнуло');
    if (t < tF) {
      let s = bg.field() + rect('#3a0d05', 0.45) + dustLayer(t, 61, 30, '#ffb070', 14, -8);
      s += place(sil(A.human(A.LIDA, { back: true }), '#1a0f0c'), 800, 1066, 0.13);
      return cam(s, 560, 1150, 1.05 + 0.04 * prog(t, T8, tF));
    }
    const k = easeOut(prog(t, tF, tF + 0.7));
    let s = bg.fireSky();
    s += `<rect x="-200" y="1060" width="${W + 400}" height="900" fill="#3a2010"/>`;
    const seed = Math.floor(t * 14);
    s += `<g transform="translate(0 1085) scale(1 ${f(k)})">${A.fireWall(W, 560, 300 + (seed % 5), { noEmbers: true })}</g>`;
    const kl = prog(t, S('Лида', 2) - 0.1, S('Лида', 2) + 0.2);
    s += `<g transform="translate(0 1100) scale(1 ${f(k)})">${A.fireWall(W, 300, 400 + (seed % 7), { noEmbers: true })}</g>`;
    if (kl > 0) {
      s += `<g opacity="${f(kl * (0.8 + 0.2 * Math.sin(t * 20)))}">${place(sil(A.human(A.LIDA, { back: true, armL: [30, -20], armR: [-30, 20] }), '#140a08'), 770, 1095, 0.24)}</g>`;
      s += `<g transform="translate(560 1100)">${A.fireWall(420, 70, 500 + (seed % 3), { noEmbers: true })}</g>`;
    }
    s += once('fireWheat', () => A.wheat(1100, H, 29, ['#3a2410', '#5a3618', '#2a1a0c']));
    s += `<rect x="-200" y="1100" width="${W + 400}" height="900" fill="#ff5a1f" opacity="${f(0.08 + 0.04 * Math.sin(t * 17))}"/>`;
    s += emberLayer(t, 62, 70);
    s += rect('#fff0d0', 0.8 * pulse(t, tF, 0.35));
    const kp = ease(prog(t, S('Лида', 2) - 0.3, E('там') + 0.2));
    return cam(s, lerp(540, 760, kp), lerp(1100, 1050, kp), lerp(1.0, 1.9, kp), shake(t, tF, 0.6, 22));
  }
  // 9. Ночь у колодца: цепь, ведро, «Не пей!»
  const yardNight = () => once('yardNight', () => bg.yardOpen() + `<rect width="${W}" height="${H}" fill="#1a0505" opacity="0.5"/><defs><radialGradient id="ynG" cx="0.1" cy="0.55" r="0.7"><stop offset="0" stop-color="#ff5a1f" stop-opacity="0.45"/><stop offset="1" stop-color="#ff5a1f" stop-opacity="0"/></radialGradient></defs><rect width="${W}" height="${H}" fill="url(#ynG)"/>`);
  function sNight(t) {
    const tYank = S('сорвала'), tHit = S('выбил') + 0.1, tShout = S('Не', 2) - 0.08;
    if (t >= tShout) {
      let s = cam(yardNight(), 600, 1100, 1.5) + emberLayer(t, 71, 30);
      const op = clamp((t - tShout) / 0.12);
      s += closeUp(A.ZAKHAR, { face: 'shock', hairFront: A.ZAKHAR.front({ mouth: 'open', open: 0.6 + 0.4 * Math.abs(Math.sin(t * 9)) }), armL: [60, -40], armR: [-60, 40] }, 540, 820, 3.0);
      s += rect('#c4180c', 0.25 * pulse(t, tShout, 0.5)) + rect('#000', 0.2 * (1 - op));
      return cam(s, 540, 950, 1.0 + 0.08 * prog(t, tShout, T10), shake(t, tShout, 0.7, 26));
    }
    let s = yardNight() + emberLayer(t, 72, 40) + ashLayer(t, 73, 25);
    // цепь падает
    const kc = prog(t, tYank + 0.1, tYank + 0.55);
    if (kc < 1) s += `<g opacity="${f(1 - prog(t, tYank + 0.45, tYank + 0.6))}">${place(A.chainLock(), 478 + kc * 30, 1467 + easeIn(kc) * 300, 1.395, -8 + kc * 40)}</g>`;
    // Вика: рывок, потом ведро
    const kUp = ease(prog(t, S('цепь', 2) - 0.05, S('цепь', 2) + 0.35));
    let vArm = [-8, 6];
    if (t < S('цепь', 2)) { const ky = prog(t, tYank - 0.1, tYank + 0.3); vArm = [lerp(-8, -70, Math.sin(ky * Math.PI)), lerp(6, -20, Math.sin(ky * Math.PI))]; }
    else vArm = [lerp(-8, -38, kUp), lerp(6, -78, kUp)];
    const hasBucket = t >= S('цепь', 2) && t < tHit;
    const vHand = hasBucket ? `<g transform="rotate(${f(-(vArm[0] + vArm[1]))}) translate(0 95)">${A.bucket('poison', 0.75)}</g>` : '';
    const VX = 330, VY = 1810, VS = 1.2;
    s += vika({ armL: [10, -4], armR: vArm, face: t > tHit ? 'shock' : 'worried', look: [5, 0], handR: vHand, front: A.VIKA.pocket(0) }, VX, VY, VS);
    // Захар врывается
    const kz = prog(t, S('Захар', 2) - 0.2, S('Захар', 2) + 0.15);
    if (kz > 0) {
      const zx = lerp(1250, 700, easeOut(kz));
      const ks = prog(t, S('выбил') - 0.05, S('выбил') + 0.12);
      const zArm = [lerp(10, 100, Math.sin(Math.min(1, ks) * Math.PI / 2) * (1 - prog(t, tHit + 0.3, tHit + 0.7))), lerp(-10, 0, ks)];
      if (kz < 1) { const w = walk(t * 14, 18); s += zakhar({ legL: w.legL, legR: w.legR, armL: w.armL, armR: [-10, 10], face: 'shock', look: [-6, 0] }, zx, VY - w.bob, 1.0); }
      else s += zakhar({ armL: zArm, armR: [-10, 10], face: 'shock', look: [-6, 0] }, zx, VY, 1.0);
    }
    // ведро летит, яд разливается
    if (t >= tHit) {
      const h0 = handWorld(A.VIKA, 1, [-38, -78], VX, VY, VS);
      const kf = prog(t, tHit, tHit + 0.7);
      const bx = lerp(h0[0], h0[0] - 260, kf), by = h0[1] + 30 - Math.sin(kf * Math.PI) * 260 + kf * (1830 - h0[1] - 30);
      if (kf < 1) {
        s += place(A.bucket('empty', 0.75), bx, by, 1, -kf * 520);
        for (let i = 0; i < 8; i++) s += `<circle cx="${f(bx + 40 + i * 18 * kf)}" cy="${f(by - 40 + i * 14 * kf + Math.sin(i) * 10)}" r="${f(9 - i * 0.7)}" fill="${P.poison}" opacity="0.9"/>`;
      } else s += place(A.bucket('empty', 0.75), h0[0] - 260, 1840, 1, 100);
      const kp = easeOut(prog(t, tHit + 0.55, tHit + 1.2));
      if (kp > 0) s += `<ellipse cx="${f(h0[0] - 200)}" cy="1850" rx="${f(220 * kp)}" ry="${f(45 * kp)}" fill="${P.poison}" opacity="0.85"/><ellipse cx="${f(h0[0] - 200)}" cy="1846" rx="${f(150 * kp)}" ry="${f(22 * kp)}" fill="#d6e06a" opacity="0.5"/>`;
    }
    return cam(s, 540, 1350, 1.08, [...shake(t, tYank + 0.1, 0.3, 10)].map((v, i) => v + shake(t, tHit, 0.4, 16)[i]));
  }
  // 10. Яд и правда о болезни
  function sPoison(t) {
    const tFace = S('и', 2) - 0.1;
    if (t >= tFace) {
      let s = cam(yardNight(), 500, 1200, 1.6) + rect('#000', 0.35) + ashLayer(t, 81, 30);
      s += closeUp(Object.assign({}, A.VIKA, { crackedLips: true, faceOver: { mouth: 'none' } }), { face: 'pain', sweat: true, look: [-5, 6], tilt: -4 }, 610, 720, 2.4);
      const tr = tremble(t, 5);
      const hand = `<rect x="-55" y="0" width="110" height="900" rx="55" fill="${A.VIKA.skin}"/><path d="M0 0 h55 v900 h-55 Z" fill="${A.VIKA.skinD}"/><circle r="105" fill="${A.VIKA.skin}"/><path d="M0 -105 A105 105 0 0 1 0 105 Z" fill="${A.VIKA.skinD}"/>` +
        [-70, -25, 20, 62].map((dx, i) => `<rect x="${dx - 17}" y="-185" width="34" height="${i === 0 ? 110 : 120}" rx="17" fill="${A.VIKA.skin}"/>`).join('');
      s += place(hand, 340 + tr[0] * 2, 1350 + tr[1] * 2, 1, 18);
      let hb = 0;
      for (const wd of ['три', 'дня', 'назад']) hb = Math.max(hb, pulse(t, S(wd), 0.4));
      s += `<defs><radialGradient id="hbV" cx="0.5" cy="0.5" r="0.75"><stop offset="0.45" stop-color="#b3140c" stop-opacity="0"/><stop offset="1" stop-color="#b3140c" stop-opacity="0.85"/></radialGradient></defs><rect width="${W}" height="${H}" fill="url(#hbV)" opacity="${f(0.35 + 0.65 * hb)}"/>`;
      return cam(s, 540, 960, 1 + 0.05 * prog(t, tFace, T11) + 0.03 * hb);
    }
    let s = bg.ground();
    const kp = 0.85 + 0.15 * prog(t, T10, tFace);
    const R = A.rng(5);
    let blob = 'M';
    for (let i = 0; i <= 24; i++) { const a = (i / 24) * Math.PI * 2, r = (300 + (R() - 0.5) * 70 + Math.sin(t * 2 + i) * 6) * kp; blob += `${f(540 + Math.cos(a) * r)} ${f(1150 + Math.sin(a) * r * 0.62)} ${i < 24 ? 'L' : 'Z'}`; }
    const glow = 0.3 + 0.25 * Math.sin(t * 5) + 0.4 * pulse(t, S('яд'), 0.8);
    s += `<path d="${blob}" fill="${P.poisonD}"/><g transform="translate(540 1150) scale(0.86) translate(-540 -1150)"><path d="${blob}" fill="${P.poison}"/></g><ellipse cx="480" cy="1110" rx="120" ry="30" fill="#e3ef8a" opacity="${f(clamp(glow, 0, 1) * 0.6)}"/>`;
    for (let i = 0; i < 16; i++) {
      const ph = (t * (0.8 + (i % 5) * 0.2) + i * 0.37) % 1, bx = 540 + Math.cos(i * 2.4) * 220 * ((i % 7) / 7), by = 1150 + Math.sin(i * 1.7) * 110 * ((i % 5) / 5);
      s += `<circle cx="${f(bx)}" cy="${f(by)}" r="${f(6 + ph * 14)}" fill="none" stroke="#e3ef8a" stroke-width="3" opacity="${f((1 - ph) * 0.8)}"/>`;
    }
    const burn = ease(prog(t, S('яд') - 0.1, S('яд') + 0.8));
    s += tufts(t, burn);
    if (burn > 0) for (let i = 0; i < 7; i++) { const ph = (t * 0.5 + i / 7) % 1; s += `<path d="M${f(380 + i * 55)} ${f(1100 - ph * 500)} q 30 -40 0 -80 q -30 -40 0 -80" stroke="#cfd7a0" stroke-width="10" fill="none" opacity="${f(burn * (1 - ph) * 0.35)}" stroke-linecap="round"/>`; }
    s += `<defs><radialGradient id="pvg" cx="0.5" cy="0.6" r="0.7"><stop offset="0.5" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity="0.7"/></radialGradient></defs><rect width="${W}" height="${H}" fill="url(#pvg)"/>`;
    return cam(s, 540, lerp(1050, 1150, prog(t, T10, tFace)), lerp(1.0, 1.25, ease(prog(t, T10, tFace))));
  }
  // 11. Из дыма выходит Лида
  function sSmoke(t) {
    let s = bg.smoke();
    for (let i = 0; i < 5; i++) { const x = ((i * 300 + t * (30 + i * 12)) % 1600) - 260; s += `<ellipse cx="${f(x)}" cy="${f(500 + i * 260)}" rx="320" ry="140" fill="#2a2124" opacity="0.35"/>`; }
    const k = easeOut(prog(t, T11 + 0.1, S('ведром') + 0.5));
    const w = walk(t * 7, lerp(8, 14, k));
    const ls = lerp(0.42, 1.6, k), ly = lerp(1230, 1840, k) - w.bob * ls * 0.5;
    const km = ease(prog(t, S('картой') - 0.15, S('картой') + 0.35));
    const armL = [lerp(w.armL[0], -30, km), lerp(w.armL[1], -100, km)];
    const armR = [-4 + Math.sin(t * 7) * 3, 2];
    const mapH = km > 0 ? `<g transform="rotate(${f(-(armL[0] + armL[1]))})"><rect x="-16" y="-80" width="32" height="130" rx="14" fill="${P.paper}"/><rect x="-16" y="-80" width="32" height="14" rx="7" fill="${P.paperD}"/></g>` : '';
    const pose = { legL: w.legL, legR: w.legR, armL, armR, face: 'hope', headOver: A.LIDA.mask, handL: mapH, handR: `<g transform="rotate(${f(-(armR[0] + armR[1]))}) translate(0 120)">${A.bucket('clean', 0.75)}</g>` };
    const fig = A.human(A.LIDA, pose);
    s += place(fig, 540, ly, ls);
    s += `<g opacity="${f(clamp(1 - k * 1.3))}">${place(sil(fig, '#0e0a0b'), 540, ly, ls)}</g>`;
    const hp = handWorld(A.LIDA, 1, armR, 540, ly, ls);
    const gk = 0.15 + 0.5 * prog(t, S('чистой') - 0.1, S('чистой') + 0.4) + 0.2 * Math.sin(t * 4);
    s += `<defs><radialGradient id="cwG"><stop offset="0" stop-color="${P.water}" stop-opacity="0.9"/><stop offset="1" stop-color="${P.water}" stop-opacity="0"/></radialGradient></defs><circle cx="${f(hp[0])}" cy="${f(hp[1] + 70 * ls)}" r="${f(190 * ls)}" fill="url(#cwG)" opacity="${f(clamp(gk, 0, 0.7) * 0.6)}"/>`;
    s += ashLayer(t, 91, 45);
    return cam(s, 540, lerp(1150, 1250, k), 1 + 0.12 * ease(prog(t, S('картой') - 0.2, T12)));
  }
  // 12. Карта: колодцы зачёркнуты по одному
  function sMap(t) {
    let s = `<rect x="-200" y="-200" width="${W + 400}" height="${H + 400}" fill="#1a1311"/>`;
    s += `<defs><radialGradient id="mapG" cx="0.5" cy="0.45" r="0.6"><stop offset="0" stop-color="#5a2a18" stop-opacity="0.6"/><stop offset="1" stop-color="#1a1311" stop-opacity="0"/></radialGradient></defs><rect width="${W}" height="${H}" fill="url(#mapG)"/>`;
    const ct = [S('все'), S('наши'), S('колодцы', 2), S('были'), S('зачеркнуты'), S('красным'), S('одному', 2)];
    const crosses = ct.map((c) => (t < c ? 0 : back(prog(t, c, c + 0.2))));
    const tr = tremble(t, 1.2);
    const sleeve = (x, y, rot) => `<g transform="translate(${x} ${y}) rotate(${rot})"><rect x="-62" y="40" width="124" height="700" rx="40" fill="#d3cbbb"/><rect x="0" y="40" width="62" height="700" rx="30" fill="#a19887"/><rect x="-46" y="-20" width="92" height="90" rx="40" fill="${A.LIDA.skin}"/><rect x="-60" y="-60" width="34" height="80" rx="17" fill="${A.LIDA.skin}" transform="rotate(-25)"/><path d="M0 -20 h46 v90 h-46 Z" fill="${A.LIDA.skinD}" opacity="0.6"/></g>`;
    s += `<g transform="translate(${f(tr[0])} ${f(tr[1])})">` + place(A.wellMap(1.85, crosses), 540, 920, 1, -4) + sleeve(120, 1390, 20) + sleeve(960, 1360, -20) + `</g>`;
    s += ashLayer(t, 95, 25);
    const fl = pulse(t, ct[6], 0.5);
    s += rect('#c4180c', 0.22 * fl);
    s += `<defs><radialGradient id="mvg" cx="0.5" cy="0.48" r="0.72"><stop offset="0.5" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity="0.75"/></radialGradient></defs><rect width="${W}" height="${H}" fill="url(#mvg)"/>`;
    return cam(s, 540, 940, 1.0 + 0.18 * ease(prog(t, T12, TEND)) + 0.06 * fl);
  }
  // 13. Титр
  function sTitle(t) {
    const k = prog(t, TEND, TEND + 0.25);
    let s = `<rect width="${W}" height="${H}" fill="#0d0807"/>`;
    s += place(A.sunEye(70, { pupil: lerp(0.3, 0.1, prog(t, TEND, 60)) }), 540, 620, 1);
    const fl = 0.85 + 0.15 * Math.sin(t * 23);
    s += `<g opacity="${f(k)}">`;
    s += `<text x="540" y="900" text-anchor="middle" font-family="Inter Display, Inter, sans-serif" font-weight="900" font-size="112" fill="#ff8a3a" opacity="${f(fl)}" letter-spacing="2">АНОМАЛЬНАЯ</text>`;
    s += `<text x="540" y="1020" text-anchor="middle" font-family="Inter Display, Inter, sans-serif" font-weight="900" font-size="112" fill="#ff8a3a" opacity="${f(fl)}" letter-spacing="2">ЖАРА</text>`;
    s += `<text x="540" y="1180" text-anchor="middle" font-family="Inter Display, Inter, sans-serif" font-weight="800" font-size="56" fill="#f2e2c6">Кто зачеркнул колодцы?</text>`;
    s += `<text x="540" y="1270" text-anchor="middle" font-family="Inter Display, Inter, sans-serif" font-weight="700" font-size="44" fill="#b49a7c">Серия 2 — скоро</text>`;
    s += `</g>` + emberLayer(t, 99, 25);
    return s;
  }

  // ---------- СУБТИТРЫ ----------
  const KEY = {
    orange: ['колодцы', 'колодцу', 'жара', 'жары', 'кондиционеры', 'поле', 'вспыхнуло', 'водокачке', 'полем', 'десятый'],
    red: ['дрожали', 'глотка', 'ни', 'пей', 'зачеркнуты', 'красным', 'три', 'дня', 'назад', 'коровы', 'падали', 'цепь'],
    cyan: ['бутылке', 'бутылку', 'воды', 'воду', 'чистой'],
    green: ['яд'],
    gold: ['лида', 'лиде', 'захар', 'картой', 'карте'],
  };
  const COL = { orange: '#ff8a3a', red: '#ff4a3d', cyan: '#5fd6ea', green: '#c6dc3c', gold: '#ffd27a' };
  function wordColor(w, i) {
    const n = norm(w);
    if (n === 'не' && TM[i + 1] && norm(TM[i + 1].w) === 'пей') return COL.red;
    if (n === 'по' || n === 'одному') return i > 100 ? COL.red : COL.orange;
    for (const k in KEY) if (KEY[k].includes(n)) return COL[k];
    return '#ffffff';
  }
  const clean = (w) => w.replace(/[«»"]/g, '').replace(/[.,:;—]+$/g, '').toUpperCase();
  let mEl = null; const mCache = {};
  function measure(txt, fs) {
    const key = txt;
    if (mCache[key] == null) {
      if (!mEl) {
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('style', 'position:absolute;left:-9999px;top:0');
        mEl = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        mEl.setAttribute('font-family', 'Inter Display, Inter, sans-serif'); mEl.setAttribute('font-weight', '900'); mEl.setAttribute('font-size', '100');
        svg.appendChild(mEl); document.body.appendChild(svg);
      }
      mEl.textContent = txt; mCache[key] = mEl.getComputedTextLength() / 100;
    }
    return mCache[key] * fs;
  }
  const SUB_Y = 1530;
  const SHORT = ['на', 'по', 'к', 'в', 'у', 'и', 'а', 'не', 'ни', 'с', 'из', 'за', 'но', 'бы', 'его'];
  const chunks = (() => {
    const out = []; let cur = [];
    const len = (ids) => ids.reduce((a, j) => a + clean(TM[j].w).length, 0);
    TM.forEach((w, i) => {
      const prev = TM[i - 1];
      const brk = cur.length && (cur.length >= 3 || len(cur) + clean(w.w).length > 17 || prev.br || /[.,:;!?…»]$/.test(prev.w) || w.s - prev.e > 0.35);
      if (brk) { out.push(cur); cur = []; }
      cur.push(i);
    });
    if (cur.length) out.push(cur);
    // предлог/союз не оставляем в конце строки — переносим к следующему слову
    for (let k = 0; k < out.length - 1; k++) {
      const c = out[k], lw = TM[c[c.length - 1]];
      if (c.length > 1 && SHORT.includes(norm(lw.w)) && !lw.br && !/[.,:;!?…»]$/.test(lw.w)) out[k + 1].unshift(c.pop());
    }
    return out.map((idx) => ({ idx, s: TM[idx[0]].s - 0.06, e: 0 }));
  })();
  chunks.forEach((c, i) => {
    const last = TM[c.idx[c.idx.length - 1]];
    const nxt = chunks[i + 1];
    c.e = Math.min(nxt ? nxt.s : 999, last.e + 0.5);
  });
  function subtitles(t) {
    if (t >= TEND) return '';
    const c = chunks.find((c) => t >= c.s && t < c.e);
    if (!c) return '';
    let fs = 92;
    const words = c.idx.map((i) => clean(TM[i].w));
    const gap = 0.34;
    let widths = words.map((w) => measure(w, fs)), tot = widths.reduce((a, b) => a + b, 0) + gap * fs * (words.length - 1);
    if (tot > 960) { const k = 960 / tot; fs *= k; widths = widths.map((x) => x * k); tot = 960; }
    let x = 540 - tot / 2, s = '';
    c.idx.forEach((i, j) => {
      const w = TM[i], vis = t >= w.s - 0.04;
      const kpop = prog(t, w.s - 0.04, w.s + 0.1);
      const active = t >= w.s - 0.04 && t < w.e + 0.05;
      const sc = vis ? lerp(1.22, 1, easeOut(kpop)) : 1;
      const cx = x + widths[j] / 2;
      if (vis) {
        s += `<g transform="translate(${f(cx)} ${SUB_Y}) scale(${f(sc)})" opacity="${f(clamp(kpop * 2.5))}">` +
          `<text x="0" y="8" text-anchor="middle" font-family="Inter Display, Inter, sans-serif" font-weight="900" font-size="${f(fs)}" fill="#000" opacity="0.45">${words[j]}</text>` +
          `<text x="0" y="0" text-anchor="middle" font-family="Inter Display, Inter, sans-serif" font-weight="900" font-size="${f(fs)}" fill="${wordColor(w.w, i)}" stroke="#140a06" stroke-width="${f(fs * 0.17)}" paint-order="stroke" stroke-linejoin="round">${words[j]}</text></g>`;
      }
      x += widths[j] + gap * fs;
    });
    return s;
  }

  // ---------- КАДР ----------
  function frameSVG(t) {
    let s;
    if (t < T1b) s = sWell(t);
    else if (t < T2) s = sSun(t);
    else if (t < T3) s = sStreet(t);
    else if (t < T4) s = sVika(t);
    else if (t < T5) s = sLida(t);
    else if (t < T6) s = sFarm(t);
    else if (t < T7) s = sYard(t);
    else if (t < T8) s = sField(t);
    else if (t < T9) s = sFire(t);
    else if (t < T10) s = sNight(t);
    else if (t < T11) s = sPoison(t);
    else if (t < T12) s = sSmoke(t);
    else if (t < TEND) s = sMap(t);
    else s = sTitle(t);
    // лёгкое мерцание плёнки
    s += `<rect width="${W}" height="${H}" fill="#000" opacity="${f(0.03 + 0.03 * Math.abs(noise(t * 7, 9)))}"/>`;
    s += subtitles(t);
    return s;
  }

  global.EP1 = { frameSVG, SCENES, chunks, S, E, DURATION: 60 };
})(typeof window !== 'undefined' ? window : globalThis);
