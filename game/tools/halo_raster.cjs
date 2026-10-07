// Rasterise the halo widget (design/ui/mockups/_src/widgets.js haloSVG) into white-on-transparent layers,
// one element per PNG, for game/assets/ui/halo/. The Loadout screen stacks them and tints each with
// ImageNode.color (per-arc tier colours, unlit grey), so one set of layers draws any halo.
//
//   PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers node game/tools/halo_raster.cjs
//
// Geometry is copied from haloSVG: viewBox 120, arc radius 34, arcs at head -90 / legs 0 / torso 90 /
// arms 180 degrees, each +-39 degrees; band width per core (bulwark 8 on a pointy-top hexagon, mender 4
// plus an inner arc at r 27, volt 6 plus three spikes per arc, phase 5 with the torso arc split by 16
// degrees); weight bands at r 45 (3) and r 46 (7, dashed 14/3). Layers are 300x300 (2.5x the viewBox).
const fs = require('fs');
const path = require('path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || '/opt/node22/lib/node_modules/playwright');

const root = path.resolve(__dirname, '..', '..');
const out = path.join(root, 'game/assets/ui/halo');
fs.mkdirSync(out, { recursive: true });

const SIZE = 300;
const cx = 60, cy = 60, R = 34;
const ANG = { head: -90, legs: 0, torso: 90, arms: 180 };
const BW = { bulwark: 8, mender: 4, volt: 6, phase: 5 };

function shapes(core) {
  const hex = (t) => { const k = ((t % 60) + 60) % 60 - 30; return R * Math.cos(Math.PI / 6) / Math.cos(k * Math.PI / 180); };
  const pt = (a, r) => [cx + r * Math.cos(a * Math.PI / 180), cy + r * Math.sin(a * Math.PI / 180)];
  const arc = (a0, a1, rr) => {
    let d = '';
    for (let i = 0; i <= 24; i++) {
      const a = a0 + (a1 - a0) * i / 24;
      const r = core === 'bulwark' ? hex(a + 90) * rr / R : rr;
      const p = pt(a, r);
      d += (i ? 'L' : 'M') + p[0].toFixed(2) + ' ' + p[1].toFixed(2);
    }
    return d;
  };
  const segs = (z) => {
    const a = ANG[z];
    return core === 'phase' && z === 'torso' ? [[a - 39, a - 8], [a + 8, a + 39]] : [[a - 39, a + 39]];
  };
  return { pt, arc, segs, bw: BW[core] };
}

// Every layer: [file stem, svg body]
const layers = [];
for (const core of Object.keys(BW)) {
  const { pt, arc, segs, bw } = shapes(core);
  for (const z of Object.keys(ANG)) {
    const paths = (w, extra = '') => segs(z).map(([a0, a1]) =>
      `<path d="${arc(a0, a1, R)}" fill="none" stroke="#fff" stroke-width="${w}" ${extra}/>`).join('');
    layers.push([`${core}_${z}`, paths(bw)]);
    layers.push([`${core}_${z}_glow`, `<g filter="url(#g)">${paths(bw + 3, 'stroke-linecap="butt"')}</g>`]);
    layers.push([`${core}_${z}_hair`, paths(1)]);
    layers.push([`${core}_${z}_rim`, paths(1.2)]);
    if (core === 'mender') {
      layers.push([`${core}_${z}_inner`, segs(z).map(([a0, a1]) =>
        `<path d="${arc(a0 + 3, a1 - 3, R - 7)}" fill="none" stroke="#fff" stroke-width="2.4"/>`).join('')]);
    }
    if (core === 'volt') {
      let s = '';
      for (const [a0, a1] of segs(z)) {
        for (const t of [a0 + 10, (a0 + a1) / 2, a1 - 10]) {
          const p1 = pt(t, R + bw / 2), p2 = pt(t, R + bw / 2 + 6);
          s += `<path d="M${p1[0]} ${p1[1]}L${p2[0]} ${p2[1]}" stroke="#fff" stroke-width="3.2"/>`;
        }
      }
      layers.push([`${core}_${z}_ticks`, s]);
    }
  }
}
layers.push(['band_medium', `<circle cx="60" cy="60" r="${R + 11}" fill="none" stroke="#fff" stroke-width="3"/>`]);
layers.push(['band_medium_line', `<circle cx="60" cy="60" r="${R + 11}" fill="none" stroke="#fff" stroke-width="1"/>`]);
layers.push(['band_heavy', `<circle cx="60" cy="60" r="${R + 12}" fill="none" stroke="#fff" stroke-width="7" stroke-dasharray="14 3"/>`]);
layers.push(['band_heavy_line', `<circle cx="60" cy="60" r="${R + 12}" fill="none" stroke="#fff" stroke-width="1"/>`]);

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: SIZE, height: SIZE }, deviceScaleFactor: 1 });
  for (const [name, body] of layers) {
    const html = `<!doctype html><html><body style="margin:0;background:transparent">
      <svg id="h" viewBox="0 0 120 120" width="${SIZE}" height="${SIZE}" style="display:block;overflow:visible">
      <defs><filter id="g" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2"/></filter></defs>
      ${body}</svg></body></html>`;
    await page.setContent(html);
    const el = await page.$('#h');
    await el.screenshot({ path: path.join(out, `${name}.png`), omitBackground: true });
  }
  await browser.close();
  console.log(`${layers.length} halo layers -> ${out}`);
})();
