// Rasterise the UI mockup icons (design/ui/mockups/_src/icons.svg) to white-on-transparent PNGs in
// game/assets/ui/icons/, at 2x their viewBox (so they are 1:1 at 2160p). Tint them in Bevy with
// ImageNode.color. Symbols with hard-coded #0b0e13 detail get that detail cut out (tools/ui_shapes.py).
//
//   PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers node game/tools/ui_raster.cjs
const fs = require('fs');
const path = require('path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || '/opt/node22/lib/node_modules/playwright');

const root = path.resolve(__dirname, '..', '..');
const svg = fs.readFileSync(path.join(root, 'design/ui/mockups/_src/icons.svg'), 'utf8');
const out = path.join(root, 'game/assets/ui/icons');
fs.mkdirSync(out, { recursive: true });

const symbols = [...svg.matchAll(/<symbol id="([^"]+)" viewBox="0 0 (\d+) (\d+)"/g)].map(m => ({
  id: m[1], w: +m[2], h: +m[3],
}));

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ deviceScaleFactor: 2 });
  for (const s of symbols) {
    const html = `<!doctype html><html><body style="margin:0;background:transparent">
      <div style="display:none">${svg}</div>
      <svg id="icon" width="${s.w}" height="${s.h}" style="color:#fff;display:block"><use href="#${s.id}"/></svg>
      </body></html>`;
    await page.setContent(html);
    const el = await page.$('#icon');
    await el.screenshot({ path: path.join(out, `${s.id.replace(/^i-/, '')}.png`), omitBackground: true });
  }
  await browser.close();
  console.log(`${symbols.length} icons -> ${out}`);
})();
