// «Аномальная жара» — визуальный мир серии: палитра, персонажи, реквизит, фоны.
// Всё рисуется кодом в SVG. Функции возвращают строки SVG, их можно вставлять друг в друга.
// Персонажи собраны из отдельных частей (голова, руки, ноги), чтобы потом их анимировать.
(function (global) {
  let _id = 0;
  const uid = (p) => `${p || 'g'}${++_id}`;
  function rng(seed) {
    return function () {
      seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
      let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  const f = (n) => Math.round(n * 10) / 10;

  // ---------- ПАЛИТРА ----------
  // Тёмная, выжженная, тревожная. Холодный голубой — только у чистой воды.
  const P = {
    ink: '#110b09', night: '#1a1210', bg: '#16100d',
    soil: '#3b2619', soilD: '#291a11', dust: '#7a4f2a', dustL: '#94653a', ochre: '#a8692c',
    straw: '#b98b3a', strawD: '#7e5a24', strawL: '#d1a54e',
    skyTop: '#2b1510', skyMid: '#7b3417', skyLow: '#c4692a', skyHaze: '#e0a254',
    sun: '#fff2d2', sunGlow: '#ffd27a',
    ash: '#57504b', ashL: '#8a827b', smoke: '#2f2729', smokeL: '#4d4245',
    fire: '#ff5a1f', fireL: '#ffbb3d', fireD: '#b3240f', ember: '#ff8a2a',
    poison: '#9fb236', poisonD: '#5f6d1c',
    water: '#5fd6ea', waterD: '#2a8fa8',
    red: '#d4302a', led: '#ff2b2b',
    wall: '#8c7155', wallD: '#5f4a37', roof: '#5e3220', roofD: '#3f2015',
    shutter: '#3c5560', window: '#1a1210',
    wood: '#5a3a24', woodD: '#3b2516', woodL: '#77502f',
    stone: '#675a50', stoneD: '#3e352f', stoneL: '#857669',
    metal: '#77766f', metalD: '#4b4a45', metalL: '#a3a29a', rust: '#8a4624',
    paper: '#c9b38a', paperD: '#9b8562', paperInk: '#3a2a1c',
  };

  // ---------- ЧЕЛОВЕЧКИ ----------
  // Капсула-сегмент от (0,0) вниз на len; правая половина в тени (свет слева, от солнца).
  function capsule(len, w, col, colD) {
    const r = w / 2;
    return `<rect x="${-r}" y="${-r}" width="${w}" height="${len + w}" rx="${r}" fill="${col}"/>` +
      `<path d="M0 ${-r} A${r} ${r} 0 0 1 ${r} 0 L${r} ${len} A${r} ${r} 0 0 1 0 ${len + r} Z" fill="${colD}"/>`;
  }
  // Рука/нога из двух сегментов. a1 — поворот в плече/бедре, a2 — в локте/колене (градусы, + по часовой).
  function limb2(o) {
    const end = o.end || '';
    return `<g transform="rotate(${o.a1 || 0})">${capsule(o.l1, o.w, o.c1, o.c1d)}` +
      `<g transform="translate(0 ${o.l1}) rotate(${o.a2 || 0})">${capsule(o.l2, o.w2 || o.w, o.c2, o.c2d)}` +
      `<g transform="translate(0 ${o.l2})">${end}</g></g></g>`;
  }

  const FACE = {
    neutral: { brow: 0, open: 1, mouth: 'line' },
    worried: { brow: 14, open: 1, mouth: 'frown' },
    sick: { brow: 12, open: 0.75, mouth: 'frown', bags: true },
    shock: { brow: 22, open: 1.35, mouth: 'open' },
    whisper: { brow: 10, open: 0.85, mouth: 'o', bags: true },
    grim: { brow: -12, open: 0.8, mouth: 'line' },
    hope: { brow: 8, open: 1.15, mouth: 'smallopen' },
    pain: { brow: 18, open: 0.35, mouth: 'teeth', bags: true },
  };

  function head(o) {
    const rx = o.rx, ry = o.ry, id = uid('hc');
    const e = Object.assign({}, FACE[o.face || 'neutral'], o.faceOver || {});
    const look = o.look || [0, 0];
    let s = o.hairBack || '';
    s += `<ellipse cx="${-rx + 2}" cy="8" rx="9" ry="14" fill="${o.skin}"/><ellipse cx="${rx - 2}" cy="8" rx="9" ry="14" fill="${o.skinD}"/>`;
    s += `<defs><clipPath id="${id}"><ellipse rx="${rx}" ry="${ry}"/></clipPath></defs>`;
    s += `<ellipse rx="${rx}" ry="${ry}" fill="${o.skin}"/>`;
    s += `<g clip-path="url(#${id})"><ellipse cx="${f(rx * 1.02)}" cy="${f(ry * 0.15)}" rx="${f(rx * 0.55)}" ry="${f(ry * 1.3)}" fill="${o.skinD}"/>`;
    if (o.cheeks) s += `<path d="M${-rx * 0.62} ${ry * 0.12} q 8 22 4 40 M${rx * 0.62} ${ry * 0.12} q -8 22 -4 40" stroke="${o.skinD}" stroke-width="4" fill="none" stroke-linecap="round"/>`;
    s += `</g>`;
    const ex = rx * 0.37, ey = -ry * 0.05;
    // мешки под глазами — болезнь
    if (e.bags) s += `<path d="M${-ex - 10} ${ey + 13} q 10 7 20 0 M${ex - 10} ${ey + 13} q 10 7 20 0" stroke="${o.bagCol || '#8a5a55'}" stroke-width="3.5" fill="none" stroke-linecap="round" opacity="0.8"/>`;
    // глаза
    for (const sx of [-1, 1]) {
      const cx = sx * ex + look[0], cy = ey + look[1];
      s += `<ellipse cx="${f(cx)}" cy="${f(cy)}" rx="6.5" ry="${f(8.5 * e.open)}" fill="${P.ink}"/>`;
      if (e.open > 0.5) s += `<circle cx="${f(cx - 2)}" cy="${f(cy - 3 * e.open)}" r="2" fill="#fff6e6" opacity="0.9"/>`;
    }
    // брови: brow>0 — внутренние концы вверх (тревога), <0 — вниз (угрюмость)
    const by = ey - 20 - (e.open > 1.2 ? 6 : 0);
    for (const sx of [-1, 1]) {
      const inner = [sx * (ex - 11), by - e.brow * 0.45];
      const outer = [sx * (ex + 13), by + e.brow * 0.25];
      s += `<path d="M${f(inner[0])} ${f(inner[1])} L${f(outer[0])} ${f(outer[1])}" stroke="${o.brow || P.ink}" stroke-width="${o.browW || 5}" stroke-linecap="round"/>`;
    }
    // нос
    s += `<path d="M3 ${ey + 4} L9 ${ey + 24} L1 ${ey + 26}" fill="${o.skinD}"/>`;
    // рот
    const my = ry * 0.5;
    const lip = o.lip || '#7a3b33';
    if (e.mouth === 'line') s += `<path d="M-11 ${my} L11 ${my}" stroke="${lip}" stroke-width="4.5" stroke-linecap="round"/>`;
    if (e.mouth === 'frown') s += `<path d="M-12 ${my + 3} Q0 ${my - 5} 12 ${my + 3}" stroke="${lip}" stroke-width="4.5" fill="none" stroke-linecap="round"/>`;
    if (e.mouth === 'open') s += `<ellipse cx="0" cy="${my + 4}" rx="10" ry="14" fill="${P.ink}"/>`;
    if (e.mouth === 'smallopen') s += `<ellipse cx="0" cy="${my + 2}" rx="8" ry="7" fill="${P.ink}"/>`;
    if (e.mouth === 'o') s += `<ellipse cx="0" cy="${my + 2}" rx="5" ry="6" fill="${P.ink}"/>`;
    if (e.mouth === 'teeth') s += `<rect x="-13" y="${my - 3}" width="26" height="10" rx="4" fill="#e8dccb"/><path d="M-13 ${my + 2} L13 ${my + 2}" stroke="${P.ink}" stroke-width="2"/>`;
    if (o.crackedLips) {
      s += `<path d="M-15 ${my} Q0 ${my - 4} 15 ${my}" stroke="#6e2a26" stroke-width="7" fill="none" stroke-linecap="round"/>`;
      s += `<path d="M-8 ${my - 3} l2 6 M-1 ${my - 4} l-1 6 M6 ${my - 3} l2 6" stroke="#e3c3a8" stroke-width="1.6"/>`;
    }
    if (o.sweat) s += `<path d="M${-rx + 10} ${-ry * 0.35} q -6 10 0 14 q 6 -4 0 -14 Z" fill="#f3e2c4" opacity="0.85"/>`;
    if (o.glasses) s += `<g fill="none" stroke="#2a201b" stroke-width="3.5"><circle cx="${-ex}" cy="${ey}" r="15"/><circle cx="${ex}" cy="${ey}" r="15"/><path d="M${-ex + 15} ${ey} Q0 ${ey - 6} ${ex - 15} ${ey}"/></g>`;
    s += o.hairFront || '';
    return s;
  }

  // Общий конструктор человечка. Начало координат — между ступнями на земле.
  function human(c, pose) {
    pose = Object.assign({ armL: [8, -6], armR: [-8, 6], legL: [3, 0], legR: [-3, 0], tilt: 0, bodyTilt: 0, face: 'neutral', look: [0, 0] }, pose || {});
    const hipY = -250, shY = -428, sw = c.sw, hw = c.hw;
    let s = '';
    // ноги
    const legX = hw * 0.48;
    for (const [sx, lg] of [[-1, pose.legL], [1, pose.legR]]) {
      const shoe = `<ellipse cx="${sx * 7}" cy="10" rx="24" ry="12" fill="${c.shoe}"/>`;
      s += `<g transform="translate(${f(sx * legX)} ${hipY})">` + limb2({ a1: lg[0], a2: lg[1], l1: 125, l2: 115, w: c.legW || 36, w2: (c.legW || 36) - 4, c1: c.thigh, c1d: c.thighD, c2: c.shin, c2d: c.shinD, end: shoe }) + `</g>`;
    }
    s += `<g transform="rotate(${pose.bodyTilt} 0 ${hipY})">`;
    if (c.back) s += c.back;
    // длинный халат / подол
    if (c.skirt) s += `<path d="M${-hw - 4} ${hipY - 10} L${hw + 4} ${hipY - 10} L${hw + 18} ${hipY + 120} L${-hw - 18} ${hipY + 120} Z" fill="${c.top}"/><path d="M${hw * 0.3} ${hipY - 10} L${hw + 4} ${hipY - 10} L${hw + 18} ${hipY + 120} L${hw * 0.4} ${hipY + 120} Z" fill="${c.topD}"/>`;
    // торс
    s += `<path d="M${-sw} ${shY + 22} Q${-sw} ${shY} ${-sw + 22} ${shY} L${sw - 22} ${shY} Q${sw} ${shY} ${sw} ${shY + 22} L${hw} ${hipY + 6} L${-hw} ${hipY + 6} Z" fill="${c.top}"/>`;
    s += `<path d="M${sw * 0.28} ${shY} L${sw - 22} ${shY} Q${sw} ${shY} ${sw} ${shY + 22} L${hw} ${hipY + 6} L${hw * 0.3} ${hipY + 6} Z" fill="${c.topD}"/>`;
    if (c.belt) s += `<rect x="${-hw}" y="${hipY - 8}" width="${hw * 2}" height="14" fill="${c.belt}"/>`;
    if (c.torsoDeco) s += c.torsoDeco;
    // шея и голова
    s += `<rect x="-13" y="${shY - 26}" width="26" height="34" fill="${c.skinD}"/>`;
    const hy = shY - 26 - c.ry + 10;
    s += `<g transform="translate(0 ${hy}) rotate(${pose.tilt})">` + head({ rx: c.rx, ry: c.ry, skin: c.skin, skinD: c.skinD, face: pose.face, faceOver: Object.assign({}, c.faceOver, pose.faceOver), look: pose.look, hairBack: c.hairBack, hairFront: c.hairFront, glasses: c.glasses, crackedLips: c.crackedLips, cheeks: c.cheeks, sweat: pose.sweat, brow: c.browCol, lip: c.lip }) + (pose.headOver || '') + `</g>`;
    if (c.neckDeco) s += c.neckDeco;
    // руки
    for (const [sx, ar, hand] of [[-1, pose.armL, pose.handL], [1, pose.armR, pose.handR]]) {
      const end = `<circle r="${c.handR || 15}" cy="4" fill="${c.skin}"/><path d="M0 -11 A15 15 0 0 1 0 19 Z" fill="${c.skinD}"/>` + (hand || '');
      s += `<g transform="translate(${sx * (sw - 13)} ${shY + 16})">` + limb2({ a1: ar[0], a2: ar[1], l1: 96, l2: 88, w: c.armW || 28, w2: (c.armW || 28) - 3, c1: c.upper, c1d: c.upperD, c2: c.fore, c2d: c.foreD, end }) + `</g>`;
    }
    if (pose.front) s += pose.front;
    s += `</g>`;
    return `<g transform="scale(${c.scale})">${s}</g>`;
  }

  // ----- Вика -----
  const VIKA = {
    scale: 1, sw: 56, hw: 48, rx: 54, ry: 63,
    skin: '#e3b99d', skinD: '#b8897a', lip: '#8a4a45', browCol: '#1c1412',
    top: '#4b6370', topD: '#34464f', upper: '#4b6370', upperD: '#34464f', fore: '#e3b99d', foreD: '#b8897a',
    thigh: '#3e3a2d', thighD: '#2a281f', shin: '#3e3a2d', shinD: '#2a281f', shoe: '#1d140f', belt: '#241a13',
  };
  VIKA.hairBack = `<ellipse cx="0" cy="-6" rx="62" ry="70" fill="#1c1412"/><path d="M28 -30 Q86 10 70 96 Q60 120 52 132 Q48 90 40 60 Q30 20 18 -10 Z" fill="#1c1412"/>`;
  VIKA.hairFront = `<path d="M-62 14 C-66 -78 62 -88 62 -6 L54 -14 Q30 -36 4 -40 Q-26 -26 -40 -6 Q-48 4 -52 26 Z" fill="#1c1412"/><path d="M-38 -10 q -10 30 -6 52" stroke="#1c1412" stroke-width="4" fill="none" stroke-linecap="round"/><path d="M24 -44 q 18 4 28 22" stroke="#3a2a24" stroke-width="3" fill="none" opacity="0.7"/>`;
  // стетоскоп на шее (ветеринар)
  VIKA.neckDeco = `<path d="M-26 -425 Q-30 -360 -6 -345 M26 -425 Q30 -372 14 -352" stroke="#262321" stroke-width="5" fill="none" stroke-linecap="round"/><circle cx="4" cy="-342" r="11" fill="#9a9a94"/><circle cx="4" cy="-342" r="6" fill="#5c5c58"/>`;
  VIKA.torsoDeco = `<path d="M-14 -428 L0 -404 L14 -428" fill="#2b3a41"/><rect x="-34" y="-392" width="22" height="20" rx="3" fill="#3f5560"/>`;

  // ----- Лида -----
  const LIDA = {
    scale: 0.92, sw: 70, hw: 66, rx: 57, ry: 62,
    skin: '#d39d7c', skinD: '#a67258', lip: '#7a3b33', browCol: '#4a403a', glasses: true,
    top: '#d3cbbb', topD: '#a19887', upper: '#d3cbbb', upperD: '#a19887', fore: '#d3cbbb', foreD: '#a19887', skirt: true,
    thigh: '#3a2f2c', thighD: '#2a2220', shin: '#3a2f2c', shinD: '#2a2220', shoe: '#2a1d17', legW: 32,
  };
  LIDA.hairBack = `<ellipse cx="0" cy="-10" rx="63" ry="66" fill="#6f655d"/><circle cx="0" cy="-82" r="28" fill="#6f655d"/><circle cx="8" cy="-84" r="18" fill="#5a5049"/>`;
  LIDA.hairFront = `<path d="M-60 10 C-66 -70 66 -70 60 10 L52 -10 Q30 -42 2 -44 Q-28 -42 -52 -10 Z" fill="#6f655d"/><path d="M2 -44 L2 -30" stroke="#4f4640" stroke-width="3"/>`;
  // халат: лацканы, сумка с красным крестом через плечо
  LIDA.torsoDeco = `<path d="M-16 -428 L0 -380 L16 -428" fill="#6b2a2a"/><path d="M-16 -428 L-34 -380 L0 -350 Z M16 -428 L34 -380 L0 -350 Z" fill="#bfb6a5"/>` +
    `<path d="M-60 -420 L56 -272" stroke="#4a3426" stroke-width="10"/><rect x="34" y="-292" width="76" height="62" rx="8" fill="#5a3f2c"/><rect x="34" y="-292" width="76" height="16" rx="6" fill="#4a3426"/><path d="M72 -270 v28 M58 -256 h28" stroke="${P.red}" stroke-width="8"/>`;

  // ----- Захар -----
  const ZAKHAR = {
    scale: 1.1, sw: 64, hw: 46, rx: 50, ry: 68, cheeks: true, faceOver: { mouth: 'none' },
    skin: '#a9704c', skinD: '#7a4b33', lip: '#5e2420', browCol: '#cfc6b6', browW: 6,
    top: '#8b8170', topD: '#625a4c', upper: '#a9704c', upperD: '#7a4b33', fore: '#a9704c', foreD: '#7a4b33',
    thigh: '#2e3236', thighD: '#1f2225', shin: '#2e3236', shinD: '#1f2225', shoe: '#1a1511', belt: '#3a2a1c', armW: 26,
  };
  // кепка с козырьком, седая борода
  ZAKHAR.hairBack = `<ellipse cx="0" cy="4" rx="54" ry="66" fill="#8f897f"/>`;
  ZAKHAR.hairFront = `<path d="M-50 10 Q-52 76 0 92 Q52 76 50 10 L40 14 Q38 48 16 50 Q0 40 -16 50 Q-38 48 -40 14 Z" fill="#8f897f"/>` +
    `<path d="M-24 38 Q0 28 24 38 Q12 44 0 40 Q-12 44 -24 38 Z" fill="#a8a196"/>` +
    `<path d="M-15 40 Q0 36 15 40" stroke="#5e2420" stroke-width="6" fill="none" stroke-linecap="round"/><path d="M-7 37 l2 5 M3 36 l-1 6" stroke="#e3c3a8" stroke-width="1.5"/>` +
    `<path d="M-58 -26 Q-56 -86 0 -88 Q56 -86 58 -26 Z" fill="#2a2723"/><path d="M-58 -26 L-104 -18 Q-96 -32 -50 -36 Z" fill="#1d1b18"/><path d="M-20 -86 L-14 -30" stroke="#3a3632" stroke-width="3"/>`;
  ZAKHAR.torsoDeco = `<path d="M-44 -428 Q0 -380 44 -428" fill="#a9704c"/><path d="M-30 -428 Q0 -400 30 -428" fill="#7a4b33"/>`;

  // ---------- РЕКВИЗИТ ----------
  // Бутылка: level 0..1 — сколько воды осталось
  function bottle(level, s) {
    level = level == null ? 0.25 : level; s = s || 1;
    const h = 110, wy = 40 + (h - 40) * (1 - level);
    return `<g transform="scale(${s})"><rect x="-16" y="-110" width="32" height="${h - 30}" rx="10" fill="#d9e6e6" opacity="0.28"/>` +
      `<rect x="-16" y="${-110 + wy - 30}" width="32" height="${h - wy}" rx="8" fill="${P.water}" opacity="0.85"/>` +
      `<path d="M-16 -110 L-8 -126 L8 -126 L16 -110" fill="#d9e6e6" opacity="0.35"/><rect x="-9" y="-140" width="18" height="15" rx="3" fill="#2f6f8a"/>` +
      `<rect x="-16" y="-80" width="32" height="18" fill="#c9c2b0" opacity="0.6"/><rect x="-12" y="-108" width="5" height="70" rx="2" fill="#ffffff" opacity="0.35"/></g>`;
  }
  function bandage(s) {
    s = s || 1;
    return `<g transform="scale(${s})"><rect x="-22" y="-16" width="44" height="32" rx="6" fill="#e6e0d2"/><ellipse cx="22" cy="0" rx="7" ry="16" fill="#c9c2b1"/><ellipse cx="22" cy="0" rx="3" ry="7" fill="#8e8778"/><path d="M-22 10 q -14 6 -24 22" stroke="#e6e0d2" stroke-width="10" fill="none"/></g>`;
  }
  function bucket(kind, s) { // kind: 'empty' | 'poison' | 'clean'
    s = s || 1;
    let liquid = '';
    if (kind === 'poison') liquid = `<ellipse cx="0" cy="-88" rx="44" ry="10" fill="${P.poison}"/><circle cx="-14" cy="-90" r="4" fill="#d6e06a"/><circle cx="12" cy="-87" r="3" fill="#d6e06a"/>`;
    if (kind === 'clean') liquid = `<ellipse cx="0" cy="-88" rx="44" ry="10" fill="${P.water}"/><ellipse cx="-10" cy="-90" rx="18" ry="3" fill="#d8fbff" opacity="0.8"/>`;
    const glow = kind === 'clean' ? `<circle cx="0" cy="-60" r="95" fill="${P.water}" opacity="0.13"/>` : '';
    return `<g transform="scale(${s})">${glow}<path d="M-46 -90 L46 -90 L36 0 L-36 0 Z" fill="${P.metal}"/><path d="M10 -90 L46 -90 L36 0 L8 0 Z" fill="${P.metalD}"/>` +
      `<ellipse cx="0" cy="-90" rx="46" ry="11" fill="${P.metalD}"/>${liquid}<path d="M-44 -70 L44 -70 M-40 -30 L40 -30" stroke="${P.metalL}" stroke-width="3" opacity="0.6"/>` +
      `<path d="M-46 -90 Q0 -170 46 -90" stroke="#3a3935" stroke-width="5" fill="none"/></g>`;
  }
  function chainLock(s) {
    s = s || 1;
    let c = '';
    for (let i = 0; i < 9; i++) c += `<ellipse cx="${-120 + i * 30}" cy="${Math.sin(i * 0.8) * 4}" rx="17" ry="9" fill="none" stroke="${i % 2 ? P.metalD : P.metal}" stroke-width="6"/>`;
    return `<g transform="scale(${s})">${c}<path d="M100 -6 q 0 -36 26 -36 q 26 0 26 36" stroke="${P.metalL}" stroke-width="9" fill="none"/><rect x="92" y="-8" width="68" height="56" rx="8" fill="#a3762f"/><rect x="126" y="-8" width="34" height="56" rx="8" fill="#7c5822"/><circle cx="126" cy="16" r="6" fill="${P.ink}"/><rect x="123" y="18" width="6" height="14" fill="${P.ink}"/></g>`;
  }
  function pitchfork(s) {
    s = s || 1;
    return `<g transform="scale(${s})"><rect x="-6" y="-360" width="12" height="420" rx="5" fill="${P.woodL}"/><rect x="0" y="-360" width="6" height="420" fill="${P.wood}"/>` +
      `<path d="M-40 -360 L40 -360" stroke="${P.metalD}" stroke-width="10" stroke-linecap="round"/><path d="M-36 -360 L-40 -470 M-12 -360 L-13 -478 M12 -360 L13 -478 M36 -360 L40 -470" stroke="${P.metal}" stroke-width="8" stroke-linecap="round"/></g>`;
  }
  function airCon(s, ledOn) {
    s = s || 1; ledOn = ledOn !== false;
    let g = '';
    for (let i = 0; i < 6; i++) g += `<path d="M-60 ${-26 + i * 9} L40 ${-26 + i * 9}" stroke="#5d5a52" stroke-width="3"/>`;
    return `<g transform="scale(${s})"><rect x="-74" y="-46" width="148" height="92" rx="6" fill="#a8a294"/><rect x="20" y="-46" width="54" height="92" rx="6" fill="#857f72"/>` +
      `<circle cx="-12" cy="0" r="30" fill="#3e3b35"/><circle cx="-12" cy="0" r="26" fill="none" stroke="#6b675d" stroke-width="3"/>${g}` +
      `<circle cx="56" cy="-30" r="5" fill="${ledOn ? P.led : '#3a1a18'}"/>${ledOn ? `<circle cx="56" cy="-30" r="12" fill="${P.led}" opacity="0.3"/>` : ''}` +
      `<rect x="-70" y="46" width="10" height="34" fill="#3a3a36"/><rect x="60" y="46" width="10" height="34" fill="#3a3a36"/></g>`;
  }
  function thermometer(s, val) {
    s = s || 1; val = val || '+44°';
    return `<g transform="scale(${s})"><rect x="-34" y="-170" width="68" height="250" rx="10" fill="#ccbfa2"/><rect x="-6" y="-150" width="12" height="190" rx="6" fill="#fff"/>` +
      `<rect x="-6" y="-128" width="12" height="168" rx="6" fill="${P.red}"/><circle cx="0" cy="48" r="16" fill="${P.red}"/>` +
      `<text x="0" y="-178" text-anchor="middle" font-family="Inter Display, Inter, sans-serif" font-weight="900" font-size="40" fill="${P.red}">${val}</text></g>`;
  }
  // Карта колодцев: crosses — сколько крестов уже нарисовано (0..7)
  function wellMap(s, crosses) {
    s = s || 1; crosses = crosses == null ? 7 : crosses;
    const wells = [[-170, -120], [-60, -170], [70, -110], [160, -10], [-140, 40], [10, 50], [-40, 150]];
    let w = '';
    wells.forEach(([x, y], i) => {
      w += `<circle cx="${x}" cy="${y}" r="14" fill="none" stroke="${P.paperInk}" stroke-width="4"/>`;
      if (i < crosses) w += `<path d="M${x - 22} ${y - 22} L${x + 22} ${y + 22} M${x + 22} ${y - 22} L${x - 22} ${y + 22}" stroke="${P.red}" stroke-width="8" stroke-linecap="round"/>`;
    });
    let houses = '';
    const R = rng(7);
    for (let i = 0; i < 16; i++) houses += `<rect x="${f(-200 + R() * 380)}" y="${f(-190 + R() * 360)}" width="16" height="12" fill="${P.paperD}"/>`;
    return `<g transform="scale(${s})"><path d="M-260 -260 L250 -250 L262 250 L-254 262 Z" fill="${P.paper}"/><path d="M-260 -260 L250 -250 L262 250 L-254 262 Z" fill="none" stroke="${P.paperD}" stroke-width="6"/>` +
      `<path d="M-250 -30 Q-60 -60 40 -10 T250 20 M-10 -250 Q10 -40 -20 250" stroke="${P.paperD}" stroke-width="10" fill="none"/>${houses}` +
      `<path d="M150 150 L230 150 L230 230 L150 230 Z" fill="none" stroke="${P.paperInk}" stroke-width="2" stroke-dasharray="6 6"/><path d="M190 216 L190 176 M178 176 L202 176 L198 160 L182 160 Z" stroke="${P.paperInk}" stroke-width="4" fill="${P.paperInk}"/>` +
      `${w}<text x="0" y="-210" text-anchor="middle" font-family="Inter Display, Inter, sans-serif" font-weight="800" font-size="30" fill="${P.paperInk}">КОЛОДЦЫ · с. Ковыльное</text></g>`;
  }

  // ---------- КОРОВА ----------
  function cow(state, s) { // state: 'stand' | 'down'
    s = s || 1;
    const body = '#6e4b33', bodyD = '#4e3424', spot = '#3a271b', muzzle = '#b48f78';
    if (state === 'down') {
      return `<g transform="scale(${s})"><ellipse cx="0" cy="0" rx="240" ry="16" fill="${P.ink}" opacity="0.35"/>` +
        `<path d="M40 -40 L150 -50 M60 -20 L180 -20" stroke="${bodyD}" stroke-width="26" stroke-linecap="round"/>` +
        `<rect x="-150" y="-120" width="300" height="120" rx="58" fill="${body}"/><path d="M-150 -40 Q0 -10 150 -40 L150 -20 Q150 0 120 0 L-120 0 Q-150 0 -150 -20 Z" fill="${bodyD}"/>` +
        `<ellipse cx="-40" cy="-80" rx="44" ry="26" fill="${spot}"/><ellipse cx="70" cy="-60" rx="30" ry="20" fill="${spot}"/>` +
        `<path d="M-140 -60 Q-200 -40 -230 -14" stroke="${body}" stroke-width="44" stroke-linecap="round" fill="none"/>` +
        `<rect x="-300" y="-46" width="96" height="58" rx="26" fill="${body}"/><rect x="-312" y="-30" width="44" height="40" rx="18" fill="${muzzle}"/>` +
        `<path d="M-246 -46 q -6 -22 -26 -26 M-216 -44 q 10 -22 30 -22" stroke="#c9b9a0" stroke-width="7" fill="none" stroke-linecap="round"/>` +
        `<path d="M-262 -26 q 8 4 16 0" stroke="${P.ink}" stroke-width="4" fill="none" stroke-linecap="round"/>` +
        `<path d="M150 -60 Q190 -50 200 -10" stroke="${bodyD}" stroke-width="7" fill="none"/><ellipse cx="202" cy="-6" rx="9" ry="12" fill="${spot}"/></g>`;
    }
    let legs = '';
    for (const x of [-110, -70, 70, 110]) legs += `<rect x="${x - 13}" y="-60" width="26" height="160" rx="10" fill="${x < 0 ? body : bodyD}"/><rect x="${x - 14}" y="86" width="28" height="16" rx="5" fill="${P.ink}"/>`;
    return `<g transform="translate(0 -100) scale(${s})">${legs}<rect x="-170" y="-150" width="340" height="140" rx="62" fill="${body}"/>` +
      `<path d="M-170 -60 Q0 -30 170 -60 L170 -40 Q170 -10 140 -10 L-140 -10 Q-170 -10 -170 -40 Z" fill="${bodyD}"/>` +
      `<ellipse cx="-20" cy="-110" rx="50" ry="30" fill="${spot}"/><ellipse cx="100" cy="-80" rx="32" ry="22" fill="${spot}"/><ellipse cx="30" cy="0" rx="26" ry="16" fill="#b0857a"/>` +
      `<path d="M170 -120 Q200 -100 196 -40" stroke="${bodyD}" stroke-width="7" fill="none"/><ellipse cx="196" cy="-34" rx="9" ry="13" fill="${spot}"/>` +
      `<path d="M-160 -110 L-210 -80" stroke="${body}" stroke-width="50" stroke-linecap="round"/>` +
      `<rect x="-290" y="-112" width="100" height="74" rx="30" fill="${body}"/><rect x="-306" y="-84" width="50" height="50" rx="20" fill="${muzzle}"/>` +
      `<circle cx="-292" cy="-64" r="4" fill="${P.ink}"/><circle cx="-272" cy="-64" r="4" fill="${P.ink}"/>` +
      `<ellipse cx="-248" cy="-92" rx="8" ry="9" fill="${P.ink}"/><circle cx="-250" cy="-95" r="2.5" fill="#fff"/>` +
      `<path d="M-232 -112 q -4 -30 -30 -40 M-206 -112 q 8 -30 34 -34" stroke="#c9b9a0" stroke-width="8" fill="none" stroke-linecap="round"/>` +
      `<ellipse cx="-196" cy="-100" rx="22" ry="11" fill="${bodyD}" transform="rotate(-20 -196 -100)"/></g>`;
  }

  // ---------- УГРОЗЫ (вместо монстров) ----------
  // Солнце-глаз: аномальное солнце, сквозной образ сериала
  function sunEye(r, opts) {
    r = r || 120; opts = opts || {};
    const id = uid('sg');
    const pupil = opts.pupil == null ? 0.22 : opts.pupil;
    return `<defs><radialGradient id="${id}"><stop offset="0" stop-color="${P.sun}" stop-opacity="0.9"/><stop offset="0.45" stop-color="${P.sunGlow}" stop-opacity="0.35"/><stop offset="1" stop-color="${P.sunGlow}" stop-opacity="0"/></radialGradient></defs>` +
      `<circle r="${r * 3.2}" fill="url(#${id})"/><circle r="${r * 1.25}" fill="${P.sun}" opacity="0.22"/><circle r="${r}" fill="${P.sun}"/>` +
      `<circle r="${r * 0.62}" fill="none" stroke="#f3cf8c" stroke-width="${r * 0.08}" opacity="0.8"/>` +
      `<ellipse rx="${r * pupil * 0.55}" ry="${r * pupil}" fill="#c96a2a" opacity="0.85"/><ellipse rx="${r * pupil * 0.25}" ry="${r * pupil * 0.62}" fill="#5a1d0e" opacity="0.9"/>`;
  }
  // Стена огня шириной w
  function fireWall(w, h, seed, opts) {
    opts = opts || {};
    const R = rng(seed || 3);
    let back = '', mid = '', front = '';
    const n = Math.round(w / 60);
    for (let i = 0; i <= n; i++) {
      const x = (i / n) * w + (R() - 0.5) * 30, hh = h * (0.3 + Math.pow(R(), 0.7) * 0.7), ww = 50 + R() * 70, lean = (R() - 0.5) * 70;
      back += `<path d="M${f(x - ww)} 0 Q${f(x - ww * 0.4)} ${f(-hh * 0.5)} ${f(x + lean)} ${f(-hh)} Q${f(x + ww * 0.5)} ${f(-hh * 0.45)} ${f(x + ww)} 0 Z"/>`;
      const h2 = hh * 0.7;
      mid += `<path d="M${f(x - ww * 0.7)} 0 Q${f(x - ww * 0.2)} ${f(-h2 * 0.5)} ${f(x + lean * 0.6)} ${f(-h2)} Q${f(x + ww * 0.35)} ${f(-h2 * 0.45)} ${f(x + ww * 0.7)} 0 Z"/>`;
      const h3 = hh * 0.4;
      front += `<path d="M${f(x - ww * 0.45)} 0 Q${f(x - ww * 0.1)} ${f(-h3 * 0.5)} ${f(x + lean * 0.3)} ${f(-h3)} Q${f(x + ww * 0.2)} ${f(-h3 * 0.45)} ${f(x + ww * 0.45)} 0 Z"/>`;
    }
    let embers = '';
    for (let i = 0; i < 40; i++) embers += `<circle cx="${f(R() * w)}" cy="${f(-R() * h * 1.6)}" r="${f(2 + R() * 4)}" fill="${P.ember}" opacity="${f(0.4 + R() * 0.6)}"/>`;
    return `<g fill="${P.fireD}">${back}</g><g fill="${P.fire}">${mid}</g><g fill="${P.fireL}">${front}</g>${opts.noEmbers ? '' : embers}`;
  }

  // ---------- ФОНЫ (1080×1920) ----------
  const W = 1080, H = 1920;
  function sky(stops) {
    const id = uid('sky');
    return `<defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1">${stops.map(([o, c]) => `<stop offset="${o}" stop-color="${c}"/>`).join('')}</linearGradient></defs><rect width="${W}" height="${H}" fill="url(#${id})"/>`;
  }
  function vignette(strength) {
    const id = uid('vg');
    return `<defs><radialGradient id="${id}" cx="0.5" cy="0.45" r="0.75"><stop offset="0.55" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity="${strength || 0.6}"/></radialGradient></defs><rect width="${W}" height="${H}" fill="url(#${id})"/>`;
  }
  function haze(y0, y1, seed, col) {
    const R = rng(seed || 1);
    let s = '';
    for (let y = y0; y < y1; y += 46) {
      const x = R() * 300 - 150;
      s += `<path d="M${f(x)} ${y} q 60 -10 120 0 t 120 0 t 120 0 t 120 0 t 120 0 t 120 0 t 120 0 t 120 0 t 120 0 t 120 0" stroke="${col || '#ffd9a0'}" stroke-width="3" fill="none" opacity="${f(0.05 + R() * 0.08)}"/>`;
    }
    return s;
  }
  function dust(n, seed, y0, y1, col) {
    const R = rng(seed || 2);
    let s = '';
    for (let i = 0; i < n; i++) s += `<circle cx="${f(R() * W)}" cy="${f(y0 + R() * (y1 - y0))}" r="${f(1.5 + R() * 3.5)}" fill="${col || '#f0c890'}" opacity="${f(0.15 + R() * 0.35)}"/>`;
    return s;
  }
  function cracks(y0, y1, seed, col) {
    const R = rng(seed || 5);
    let s = '';
    for (let i = 0; i < 26; i++) {
      let x = R() * W, y = y0 + R() * (y1 - y0), d = `M${f(x)} ${f(y)}`;
      for (let k = 0; k < 4; k++) { x += (R() - 0.5) * 120; y += (R() - 0.3) * 50; d += ` L${f(x)} ${f(y)}`; }
      s += `<path d="${d}" stroke="${col || P.soilD}" stroke-width="${f(2 + R() * 3)}" fill="none" stroke-linecap="round"/>`;
    }
    return s;
  }
  function pole(x, yBase, h, s) {
    s = s || 1;
    return `<g transform="translate(${x} ${yBase}) scale(${s})"><rect x="-9" y="${-h}" width="18" height="${h}" fill="${P.woodD}"/><rect x="-60" y="${-h + 30}" width="120" height="12" fill="${P.woodD}"/><circle cx="-50" cy="${-h + 26}" r="6" fill="#8a8a80"/><circle cx="50" cy="${-h + 26}" r="6" fill="#8a8a80"/></g>`;
  }
  function house(x, yBase, w, h, opts) {
    opts = opts || {};
    const roofH = h * 0.55;
    let s = `<g transform="translate(${x} ${yBase})">`;
    s += `<rect x="0" y="${-h}" width="${w}" height="${h}" fill="${opts.wall || P.wall}"/><rect x="${w * 0.68}" y="${-h}" width="${w * 0.32}" height="${h}" fill="${opts.wallD || P.wallD}"/>`;
    s += `<path d="M${-30} ${-h} L${w / 2} ${-h - roofH} L${w + 30} ${-h} Z" fill="${opts.roof || P.roof}"/><path d="M${w / 2} ${-h - roofH} L${w + 30} ${-h} L${w / 2} ${-h} Z" fill="${opts.roofD || P.roofD}"/>`;
    s += `<circle cx="${w / 2}" cy="${-h - roofH * 0.42}" r="${w * 0.06}" fill="${P.window}"/>`;
    const nw = opts.windows || 2;
    for (let i = 0; i < nw; i++) {
      const wx = w * (0.18 + i * (0.64 / Math.max(1, nw - 1))) - 36, wy = -h * 0.72;
      s += `<rect x="${f(wx - 22)}" y="${f(wy)}" width="22" height="110" fill="${P.shutter}"/><rect x="${f(wx + 72)}" y="${f(wy)}" width="22" height="110" fill="${P.shutter}"/>`;
      s += `<rect x="${f(wx)}" y="${f(wy)}" width="72" height="110" fill="${P.window}"/><path d="M${f(wx + 36)} ${f(wy)} v110 M${f(wx)} ${f(wy + 40)} h72" stroke="${P.wallD}" stroke-width="5"/>`;
      s += `<path d="M${f(wx - 26)} ${f(wy - 6)} h126 l-10 -20 h-106 Z" fill="${P.shutter}"/>`;
    }
    if (opts.ac) s += `<g transform="translate(${opts.ac[0]} ${opts.ac[1]})">${airCon(opts.acScale || 0.9, opts.acLed)}</g>`;
    s += `</g>`;
    return s;
  }
  function fence(x0, x1, yBase, h, col) {
    let s = '';
    for (let x = x0; x < x1; x += 34) s += `<path d="M${x} ${yBase} L${x} ${yBase - h} L${x + 12} ${yBase - h - 14} L${x + 24} ${yBase - h} L${x + 24} ${yBase} Z" fill="${col || P.woodD}"/>`;
    s += `<rect x="${x0 - 10}" y="${yBase - h * 0.75}" width="${x1 - x0 + 20}" height="12" fill="${col || P.woodD}"/><rect x="${x0 - 10}" y="${yBase - h * 0.3}" width="${x1 - x0 + 20}" height="12" fill="${col || P.woodD}"/>`;
    return s;
  }
  function waterTower(x, yBase, s) { // водонапорная башня: цилиндр-бак на трубе
    let rib = '';
    for (let i = 0; i < 5; i++) rib += `<path d="M${-100 + i * 50} -600 v170" stroke="#5a2c17" stroke-width="3" opacity="0.7"/>`;
    return `<g transform="translate(${x} ${yBase}) scale(${s || 1})"><rect x="-30" y="-440" width="60" height="440" fill="${P.rust}"/><rect x="2" y="-440" width="28" height="440" fill="#62311a"/>` +
      `<path d="M-14 -430 v420 M-4 -430 v420" stroke="#4a2414" stroke-width="2" stroke-dasharray="4 14"/>` +
      `<rect x="-110" y="-600" width="220" height="170" fill="${P.rust}"/><rect x="30" y="-600" width="80" height="170" fill="#62311a"/>${rib}` +
      `<path d="M-120 -600 L0 -650 L120 -600 Z" fill="#4a2414"/><path d="M-110 -436 h220" stroke="#4a2414" stroke-width="10"/></g>`;
  }
  function wheat(y0, y1, seed, cols) {
    const R = rng(seed || 9);
    cols = cols || [P.strawD, P.straw, P.strawL];
    let s = '';
    const rows = 26;
    for (let r = 0; r < rows; r++) {
      const y = y0 + (y1 - y0) * Math.pow(r / rows, 1.5), len = 14 + 70 * (r / rows), sw = 1.5 + 4 * (r / rows);
      for (let x = -20; x < W + 20; x += 10 + 22 * (1 - r / rows)) {
        const c = cols[Math.floor(R() * cols.length)], lean = (R() - 0.5) * len * 0.5;
        s += `<path d="M${f(x)} ${f(y)} q ${f(lean * 0.3)} ${f(-len * 0.5)} ${f(lean)} ${f(-len)}" stroke="${c}" stroke-width="${f(sw)}" fill="none" stroke-linecap="round"/>`;
      }
    }
    return s;
  }
  function wellHouse(x, yBase, s, opts) { // колодец-сруб с крышей и воротом
    opts = opts || {};
    let logs = '';
    for (let i = 0; i < 5; i++) logs += `<rect x="-130" y="${-40 - i * 40}" width="260" height="38" rx="18" fill="${i % 2 ? P.wood : P.woodL}"/><rect x="40" y="${-40 - i * 40}" width="90" height="38" rx="18" fill="${P.woodD}"/>`;
    return `<g transform="translate(${x} ${yBase}) scale(${s || 1})"><rect x="-120" y="-440" width="18" height="250" fill="${P.woodD}"/><rect x="102" y="-440" width="18" height="250" fill="${P.woodD}"/>` +
      `<path d="M-170 -420 L0 -540 L170 -420 L150 -404 L0 -510 L-150 -404 Z" fill="${P.roof}"/><path d="M0 -540 L170 -420 L150 -404 L0 -510 Z" fill="${P.roofD}"/>` +
      `<rect x="-112" y="-330" width="224" height="34" rx="16" fill="${P.woodL}"/><path d="M112 -313 h30 v50 h26" stroke="${P.metalD}" stroke-width="10" fill="none"/>` +
      `<path d="M-60 -296 v80" stroke="${P.metalD}" stroke-width="5" stroke-dasharray="10 5"/>` +
      `${logs}${opts.chained ? `<g transform="translate(-40 -150) rotate(-8)">${chainLock(0.9)}</g>` : ''}</g>`;
  }

  const BG = {
    // 1. Вид сверху в сухой колодец
    wellTop(o) {
      o = o || {};
      let s = `<rect width="${W}" height="${H}" fill="${P.soil}"/>` + cracks(0, H, 31, P.soilD);
      const cx = 540, cy = 900;
      const R = rng(4);
      for (let k = 0; k < 9; k++) {
        const r = 470 - k * 44, n = 22 - k, col = k % 2 ? P.stone : P.stoneL, dark = Math.min(0.85, k * 0.1);
        s += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${P.stoneD}"/>`;
        for (let i = 0; i < n; i++) {
          const a0 = (i / n) * Math.PI * 2 + k * 0.3, a1 = a0 + (Math.PI * 2 / n) * 0.86;
          const r0 = r - 40, p = (a, rr) => `${f(cx + Math.cos(a) * rr)} ${f(cy + Math.sin(a) * rr)}`;
          s += `<path d="M${p(a0, r0)} L${p(a0, r - 3)} A${r - 3} ${r - 3} 0 0 1 ${p(a1, r - 3)} L${p(a1, r0)} A${r0} ${r0} 0 0 0 ${p(a0, r0)} Z" fill="${R() > 0.5 ? col : P.stone}"/>`;
        }
        s += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="#000" opacity="${dark}"/>`;
      }
      s += `<circle cx="${cx}" cy="${cy}" r="80" fill="${P.dust}"/><circle cx="${cx}" cy="${cy}" r="80" fill="#000" opacity="0.35"/>`;
      s += `<g opacity="0.8">${[0, 1, 2, 3, 4].map((i) => `<path d="M${cx} ${cy} l ${f(Math.cos(i * 1.3) * 70)} ${f(Math.sin(i * 1.3) * 70)}" stroke="${P.soilD}" stroke-width="4"/>`).join('')}</g>`;
      s += `<path d="M${cx} 0 L${cx} ${cy - 90}" stroke="#4a3a2a" stroke-width="7"/>`;
      s += vignette(0.7);
      return s;
    },
    // 2. Улица деревни в мареве, кондиционеры
    street(o) {
      o = o || {};
      let s = sky([[0, P.skyTop], [0.35, P.skyMid], [0.58, P.skyLow], [0.66, P.skyHaze]]);
      s += `<g transform="translate(790 330)">${sunEye(70, { pupil: 0.18 })}</g>`;
      s += `<rect x="0" y="1180" width="${W}" height="${H - 1180}" fill="${P.dust}"/>`;
      s += `<path d="M0 1180 Q300 1150 540 1172 T1080 1165 L1080 1200 L0 1200 Z" fill="#5e3b22"/>`;
      s += pole(500, 1200, 300, 0.6) + pole(940, 1240, 520, 1);
      s += `<path d="M470 1032 Q700 1110 890 760 M530 1032 Q760 1100 990 760" stroke="#2a1a12" stroke-width="3" fill="none"/>`;
      s += house(-60, 1330, 520, 380, { windows: 2, ac: [400, -300], acScale: 0.8, acLed: o.led !== false });
      s += house(640, 1280, 420, 300, { windows: 1, ac: [80, -250], acScale: 0.7, acLed: o.led !== false, wall: '#7d644c', wallD: '#574433' });
      s += `<g transform="translate(980 1110)">${thermometer(0.55)}</g>`;
      s += fence(-10, 420, 1400, 90) + fence(660, 1090, 1360, 80);
      s += `<path d="M170 ${H} L470 1290 L620 1290 L940 ${H} Z" fill="${P.dustL}"/>`;
      s += `<path d="M330 ${H} L520 1290 M760 ${H} L585 1290" stroke="${P.dust}" stroke-width="16" opacity="0.6"/>`;
      s += cracks(1500, H, 12, '#5c3a20');
      s += haze(1000, 1450, 3) + dust(70, 6, 900, H);
      s += vignette(0.55);
      return s;
    },
    // 3. Ферма, загон
    farm(o) {
      let s = sky([[0, P.skyTop], [0.4, '#6c2f17'], [0.6, P.skyLow]]);
      s += `<g transform="translate(260 420)">${sunEye(60, { pupil: 0.2 })}</g>`;
      s += `<rect x="0" y="1100" width="${W}" height="${H - 1100}" fill="${P.dust}"/>`;
      s += `<g transform="translate(560 1130)"><rect x="0" y="-260" width="560" height="260" fill="${P.woodD}"/><path d="M-40 -260 L280 -420 L600 -260 Z" fill="${P.roofD}"/>` +
        `<rect x="200" y="-190" width="150" height="190" fill="#140d0a"/><path d="M200 -190 L350 0 M350 -190 L200 0" stroke="${P.wood}" stroke-width="10"/>` +
        `${[0, 1, 2, 3, 4, 5, 6].map((i) => `<path d="M${i * 80 + 20} -260 v260" stroke="#2c1c12" stroke-width="5"/>`).join('')}</g>`;
      for (const y of [1300, 1360]) s += `<rect x="-10" y="${y}" width="${W + 20}" height="18" fill="${P.wood}"/>`;
      for (let x = 30; x < W; x += 170) s += `<rect x="${x}" y="1270" width="22" height="150" fill="${P.woodD}"/>`;
      s += `<g transform="translate(260 1560)"><path d="M-170 -60 L170 -60 L140 0 L-140 0 Z" fill="${P.woodD}"/><path d="M-160 -60 L160 -60" stroke="${P.woodL}" stroke-width="10"/><ellipse cx="0" cy="-58" rx="150" ry="8" fill="#2a1a10"/></g>`;
      s += cracks(1420, H, 22, '#5c3a20') + haze(900, 1300, 8) + dust(80, 13, 900, H);
      s += vignette(0.6);
      return s;
    },
    // 4. Двор Захара: колодец на цепи
    yard(o) {
      o = o || {};
      let s = sky([[0, '#24110c'], [0.4, '#7a2e14'], [0.62, '#c45a22']]);
      s += `<g transform="translate(200 300)">${sunEye(55, { pupil: 0.24 })}</g>`;
      s += `<rect x="0" y="1060" width="${W}" height="${H - 1060}" fill="#5a3820"/>`;
      s += house(520, 1180, 620, 420, { windows: 1, ac: [120, -320], acScale: 0.9, acLed: o.led !== false, wall: '#6f5640', wallD: '#4b3a2b' });
      s += fence(-10, 520, 1200, 110, '#2e1d12');
      s += `<rect x="0" y="1200" width="${W}" height="${H - 1200}" fill="#6a4426"/>`;
      s += wellHouse(540, 1700, 1.55, { chained: o.chained !== false });
      s += cracks(1660, H, 41, '#4a2d18') + haze(950, 1250, 14) + dust(60, 17, 800, H);
      s += vignette(0.6);
      return s;
    },
    // 5. Поле и старая водокачка
    field(o) {
      let s = sky([[0, '#2a1410'], [0.35, '#83391a'], [0.5, '#d17a33'], [0.53, '#e8ad5c']]);
      s += `<g transform="translate(300 640)">${sunEye(85, { pupil: 0.2 })}</g>`;
      s += `<rect x="0" y="1010" width="${W}" height="${H - 1010}" fill="${P.strawD}"/>`;
      s += `<path d="M0 1010 Q270 990 540 1004 T1080 996 L1080 1030 L0 1030 Z" fill="#6a4a22"/>`;
      s += waterTower(800, 1022, 0.85);
      s += wheat(1010, H, 19);
      s += `<path d="M500 ${H} Q560 1400 640 1020 L660 1020 Q620 1400 640 ${H} Z" fill="#8a6230" opacity="0.7"/>`;
      s += haze(950, 1150, 21) + dust(50, 23, 700, H, '#ffd9a0');
      s += vignette(0.5);
      return s;
    },
    // 6. Пожар в поле
    fire(o) {
      let s = sky([[0, '#0d0807'], [0.35, '#3a120a'], [0.55, '#8a2a10'], [0.62, '#d0521f']]);
      const R = rng(55);
      for (let i = 0; i < 9; i++) {
        const x = R() * W, w = 200 + R() * 300;
        s += `<path d="M${f(x - w / 2)} 1060 C${f(x - w)} 700 ${f(x + w * 0.3)} 500 ${f(x + (R() - 0.5) * 300)} -50 L${f(x + w)} -50 C${f(x + w)} 500 ${f(x + w * 0.6)} 800 ${f(x + w / 2)} 1060 Z" fill="${i % 2 ? P.smoke : P.smokeL}" opacity="0.85"/>`;
      }
      s += `<rect x="0" y="1060" width="${W}" height="${H - 1060}" fill="#3a2010"/>`;
      s += `<g transform="translate(0 1080)">${fireWall(W, 520, 77, { noEmbers: true })}</g><g transform="translate(0 1100)">${fireWall(W, 300, 91)}</g>`;
      s += wheat(1080, H, 29, ['#3a2410', '#5a3618', '#2a1a0c']);
      s += dust(90, 61, 300, H, P.ember);
      s += vignette(0.7);
      return s;
    },
    // 7. Финал: дым, контровой свет
    smoke(o) {
      let s = `<rect width="${W}" height="${H}" fill="#1c1517"/>`;
      const id = uid('gl');
      s += `<defs><radialGradient id="${id}" cx="0.5" cy="0.55" r="0.5"><stop offset="0" stop-color="#e08a4a" stop-opacity="0.85"/><stop offset="0.5" stop-color="#8a3f2a" stop-opacity="0.45"/><stop offset="1" stop-color="#1c1517" stop-opacity="0"/></radialGradient></defs><rect width="${W}" height="${H}" fill="url(#${id})"/>`;
      const R = rng(71);
      for (let i = 0; i < 14; i++) s += `<ellipse cx="${f(R() * W)}" cy="${f(R() * H)}" rx="${f(200 + R() * 300)}" ry="${f(120 + R() * 200)}" fill="${i % 2 ? '#3d3336' : '#2a2124'}" opacity="${f(0.3 + R() * 0.4)}"/>`;
      s += `<rect x="0" y="1500" width="${W}" height="420" fill="#140f0f"/>`;
      s += dust(120, 73, 0, H, '#cfc2b5');
      s += vignette(0.75);
      return s;
    },
    // 8. Карта крупно
    mapClose(o) {
      o = o || {};
      let s = `<rect width="${W}" height="${H}" fill="#1a1311"/>`;
      s += `<g transform="translate(540 900) rotate(-4)">${wellMap(1.9, o.crosses)}</g>`;
      s += vignette(0.65);
      return s;
    },
  };

  global.AZ = { P, rng, uid, human, head, VIKA, LIDA, ZAKHAR, bottle, bandage, bucket, chainLock, pitchfork, airCon, thermometer, wellMap, cow, sunEye, fireWall, BG, W, H, wheat, dust, haze, vignette };
})(typeof window !== 'undefined' ? window : globalThis);
