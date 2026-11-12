// Рендер кадров в видео: node render.js out.mp4 from to [workers]
// Кадры рисует Chromium (Playwright), ffmpeg собирает их в H.264 1080x1920, 30 fps (без звука).
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const FPS = 30;
async function renderRange(browser, out, f0, f1, tag) {
  const page = await browser.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: 1 });
  page.on('pageerror', (e) => { console.error('PAGE ERROR', e.message); process.exit(1); });
  await page.goto('file://' + path.resolve(__dirname, 'frame.html'));
  await page.evaluate(() => document.fonts.ready);
  const ff = spawn('ffmpeg', ['-v', 'error', '-y', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'mjpeg', '-i', '-',
    '-c:v', 'libx264', '-preset', 'medium', '-crf', '17', '-pix_fmt', 'yuv420p', '-r', String(FPS), out], { stdio: ['pipe', 'inherit', 'inherit'] });
  const t0 = Date.now();
  for (let i = f0; i < f1; i++) {
    await page.evaluate((t) => window.renderAt(t), i / FPS);
    const buf = await page.screenshot({ type: 'jpeg', quality: 94 });
    if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once('drain', r));
    if ((i - f0) % 150 === 0) console.log(`[${tag}] кадр ${i}/${f1} (${((Date.now() - t0) / 1000).toFixed(0)} c)`);
  }
  ff.stdin.end();
  await new Promise((r) => ff.on('close', r));
  await page.close();
}
(async () => {
  const [, , out, from, to, workers] = process.argv;
  const f0 = Math.round(Number(from) * FPS), f1 = Math.round(Number(to) * FPS), n = Number(workers || 1);
  const browser = await chromium.launch();
  const tmp = path.join(path.dirname(path.resolve(out)), 'parts');
  fs.mkdirSync(tmp, { recursive: true });
  const step = Math.ceil((f1 - f0) / n), parts = [];
  for (let k = 0; k < n; k++) parts.push([f0 + k * step, Math.min(f1, f0 + (k + 1) * step), path.join(tmp, `part${k}.mp4`)]);
  await Promise.all(parts.map(([a, b, p], k) => renderRange(browser, p, a, b, 'w' + k)));
  await browser.close();
  fs.writeFileSync(path.join(tmp, 'list.txt'), parts.map((p) => `file '${p[2]}'`).join('\n'));
  await new Promise((r, j) => spawn('ffmpeg', ['-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', path.join(tmp, 'list.txt'), '-c', 'copy', out], { stdio: 'inherit' }).on('close', (c) => (c ? j(c) : r())));
  console.log('готово', out);
})();
