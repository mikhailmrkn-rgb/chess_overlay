// Контактный лист кадров для проверки: node stills.js out.png cols t1 t2 ...
const { chromium } = require('playwright');
const path = require('path');
(async () => {
  const [, , out, cols, ...ts] = process.argv;
  const times = ts.map(Number);
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: Math.max(1080, Number(cols) * 270), height: 1920 } });
  p.on('pageerror', (e) => { console.error('PAGE ERROR:', e.message); process.exit(1); });
  await p.goto('file://' + path.resolve(__dirname, 'frame.html'));
  await p.evaluate(() => document.fonts.ready);
  await p.evaluate(([t, c]) => window.contact(t, c, 270), [times, Number(cols)]);
  await (await p.$('svg')).screenshot({ path: out });
  await b.close();
  console.log('saved', out);
})();
