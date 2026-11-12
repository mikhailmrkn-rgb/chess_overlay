// Рендер HTML-листа в PNG: node render_sheet.js <file.html> <out.png> [scale]
const { chromium } = require('playwright');
const path = require('path');
(async () => {
  const [, , html, out, scale] = process.argv;
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 900, height: 600 }, deviceScaleFactor: Number(scale || 2) });
  page.on('pageerror', (e) => { console.error('PAGE ERROR:', e.message); process.exitCode = 1; });
  await page.goto('file://' + path.resolve(html));
  await page.waitForTimeout(300);
  const el = await page.$('svg');
  await el.screenshot({ path: out });
  await browser.close();
  console.log('saved', out);
})();
