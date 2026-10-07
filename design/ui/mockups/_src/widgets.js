/* Shared widget generators for the mockups (inlined by build.py).
   bodySVG  : EFT-style body-zone health silhouette (4 zones, matches HALO_SHIELD_SPEC coverage zones)
   haloSVG  : the player's own halo as a top-down HUD icon (tier colour, coverage arcs, core shape,
              weight band, power cells, remaining shield)
   In Bevy both are layered ImageNodes (one white PNG per zone / arc, tinted via ImageNode.color)
   or one UiMaterial each; see UI_DESIGN.md section 9. */
const TIER = {t1:'#EDF1F6', t2:'#59B3FF', t3:'#C46CFF', t4:'#FFCE50'};
const HP = {ok:'#E6E2D8', dmg:'#FFA23A', crit:'#FF3B4E', dead:'#15171B'};
const ZONES = {
  head:  ['M42 4H58L64 12V26L58 34H42L36 26V12Z'],
  torso: ['M33 39H67L72 47L68 100H32L28 47Z'],
  arms:  ['M25 41L18 44L9 107L17 110L27 64Z', 'M75 41L82 44L91 107L83 110L73 64Z'],
  legs:  ['M32 104H49L48 195H35Z', 'M51 104H68L65 195H52Z'],
};
const ZB = {head:[4,34], torso:[39,100], arms:[41,110], legs:[104,195]};
let _uid = 0;
function hpState(p){ return p<=0?'dead': p<0.35?'crit': p<0.75?'dmg':'ok'; }
/* o = {hp:{head:1,torso:.6,arms:.2,legs:1}, bleed:['arms'], covered:['head','torso','arms'], tier:'t2',
        heal:['legs'], hit:'torso', w:84, broken:false} */
function bodySVG(o){
  const id = 'b'+(_uid++); const w = o.w||84, h = w*2;
  const tc = TIER[o.tier||'t2'];
  let s = `<svg viewBox="0 0 100 200" width="${w}" height="${h}" style="overflow:visible">`;
  s += `<defs><pattern id="${id}hatch" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="5" height="5" fill="${HP.dead}"/><rect width="1.4" height="5" fill="#FF3B4E" opacity=".55"/></pattern>`;
  s += `<filter id="${id}glow" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="2.2"/></filter></defs>`;
  // shield coverage outline (under everything)
  for (const z of (o.covered||[])) for (const d of ZONES[z]) {
    const op = o.broken? .25 : 1;
    s += `<path d="${d}" fill="none" stroke="${tc}" stroke-width="6" stroke-linejoin="round" opacity="${.55*op}" filter="url(#${id}glow)"/>`;
    s += `<path d="${d}" fill="none" stroke="${tc}" stroke-width="4.2" stroke-linejoin="round" opacity="${op}" ${o.broken?'stroke-dasharray="4 3"':''}/>`;
  }
  for (const z of Object.keys(ZONES)) {
    const p = (o.hp && o.hp[z]!==undefined)? o.hp[z] : 1;
    const st = hpState(p);
    const [y0,y1] = ZB[z]; const fillTop = y1 - (y1-y0)*Math.max(0,Math.min(1,p));
    s += `<clipPath id="${id}c${z}"><rect x="0" y="${fillTop}" width="100" height="${200-fillTop}"/></clipPath>`;
    for (const d of ZONES[z]) {
      if (st==='dead') { s += `<path d="${d}" fill="url(#${id}hatch)" stroke="#FF3B4E" stroke-width="1.6" stroke-linejoin="round"/>`; continue; }
      s += `<path d="${d}" fill="#2a2d33" stroke="#0b0e13" stroke-width="1.5" stroke-linejoin="round"/>`;
      const anim = st==='crit' ? 'style="animation:pulse 1.1s ease-in-out infinite"' : '';
      s += `<path d="${d}" fill="${HP[st]}" clip-path="url(#${id}c${z})" ${anim}/>`;
      if (o.hit===z) s += `<path d="${d}" fill="#fff" opacity=".55"/>`;
      if ((o.heal||[]).includes(z)) s += `<path d="${d}" fill="none" stroke="#9CF7C8" stroke-width="2" stroke-dasharray="3 3" style="animation:pulse 1.4s infinite"/>`;
    }
    if ((o.bleed||[]).includes(z)) {
      const pts = {arms:[[13,96],[87,96]], legs:[[42,170],[58,170]], head:[[50,28]], torso:[[50,86]]}[z];
      for (const c of pts) {
        s += `<g transform="translate(${c[0]-5},${c[1]})"><path d="M5 0c2 3 4 5 4 7.5a4 4 0 0 1-8 0C1 5 3 3 5 0z" fill="#E0162E" stroke="#0b0e13" stroke-width=".8" style="animation:drip 1.2s ease-in infinite"/></g>`;
      }
    }
  }
  return s + '</svg>';
}
/* o = {tier:'t2', core:'mender'|'bulwark'|'volt'|'phase', covered:['head','torso','arms'], weight:'light'|'medium'|'heavy',
        cells:2, shield:.6, state:'idle'|'hit'|'broken'|'regen', size:112, label:true, value:72} */
function haloSVG(o){
  const id='h'+(_uid++); const S=o.size||112; const tc=TIER[o.tier||'t2']; const cx=60, cy=60;
  const R = 34, core=o.core||'mender', st=o.state||'idle';
  const ang = {head:-90, legs:0, torso:90, arms:180};
  const bw = {bulwark:8, mender:4, volt:6, phase:5}[core];
  const hex = (t)=>{ const k=((t%60)+60)%60 - 30; return R*Math.cos(Math.PI/6)/Math.cos(k*Math.PI/180); };
  const pt = (a,r)=>[cx + r*Math.cos(a*Math.PI/180), cy + r*Math.sin(a*Math.PI/180)];
  const arc = (a0,a1,rr)=>{ let d=''; for(let i=0;i<=24;i++){ const a=a0+(a1-a0)*i/24; const r= core==='bulwark'? hex(a+90)*rr/R : rr; const p=pt(a,r); d+=(i?'L':'M')+p[0].toFixed(2)+' '+p[1].toFixed(2);} return d; };
  let s = `<svg viewBox="0 0 120 120" width="${S}" height="${S}" style="overflow:visible"><defs><filter id="${id}g" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="${st==='hit'?3.2:2}"/></filter></defs>`;
  // weight band
  if (o.weight==='medium') s += `<circle cx="60" cy="60" r="${R+11}" fill="none" stroke="#3a3f47" stroke-width="3"/><circle cx="60" cy="60" r="${R+11}" fill="none" stroke="${tc}" stroke-opacity=".25" stroke-width="1"/>`;
  if (o.weight==='heavy') s += `<circle cx="60" cy="60" r="${R+12}" fill="none" stroke="#3a3f47" stroke-width="7" stroke-dasharray="14 3"/><circle cx="60" cy="60" r="${R+12}" fill="none" stroke="${tc}" stroke-opacity=".3" stroke-width="1"/>`;
  // arcs
  const lit = o.covered||[]; const shield = o.shield===undefined?1:o.shield;
  for (const z of ['head','legs','torso','arms']) {
    const a=ang[z]; let segs=[[a-39,a+39]];
    if (core==='phase' && z==='torso') segs=[[a-39,a-8],[a+8,a+39]];
    const on = lit.includes(z) && st!=='broken';
    for (const [a0,a1] of segs) {
      const d = arc(a0,a1,R);
      if (on) {
        s += `<path d="${d}" fill="none" stroke="${tc}" stroke-width="${bw+3}" opacity="${st==='idle'?.35:.7}" filter="url(#${id}g)" stroke-linecap="butt"/>`;
        s += `<path d="${d}" fill="none" stroke="${tc}" stroke-width="${bw}" opacity="${st==='idle'?.85:1}"/>`;
        if (shield<1) { // remaining shield: dim the arc tail (each arc drains from its clockwise end)
          const cut = a0 + (a1-a0)*shield; s += `<path d="${arc(cut,a1,R)}" fill="none" stroke="#0b0e13" stroke-width="${bw+.5}" opacity=".62"/>`; }
        if (st==='hit') s += `<path d="${d}" fill="none" stroke="#fff" stroke-width="1.2" opacity=".9"/>`;
        if (core==='mender') s += `<path d="${arc(a0+3,a1-3,R-7)}" fill="none" stroke="${tc}" stroke-width="2.4" opacity=".8"/>`;
      } else {
        s += `<path d="${d}" fill="none" stroke="#27272C" stroke-width="${bw}"/><path d="${d}" fill="none" stroke="#fff" stroke-opacity=".13" stroke-width="1"/>`;
        if (core==='mender') s += `<path d="${arc(a0+3,a1-3,R-7)}" fill="none" stroke="#27272C" stroke-width="2.4"/>`;
      }
      if (core==='volt') for (const t of [a0+10,(a0+a1)/2,a1-10]) { const p1=pt(t,R+bw/2), p2=pt(t,R+bw/2+6); s += `<path d="M${p1[0]} ${p1[1]}L${p2[0]} ${p2[1]}" stroke="${on?tc:'#33363d'}" stroke-width="3.2"/>`; }
    }
  }
  if (st==='broken') { s += `<g stroke="${tc}" stroke-width="2" fill="none" opacity=".9"><path d="M30 34l6 4-2 6"/><path d="M88 30l-5 6 4 4"/><path d="M84 90l-6-3-1 6"/><path d="M33 86l6-2 1 6"/></g>`; }
  // zone glyph letters
  const L={head:'H',legs:'L',torso:'T',arms:'A'};
  if (o.value===undefined) for (const z in ang){ const p=pt(ang[z],R-(core==='mender'?15:12)); s += `<text x="${p[0]}" y="${p[1]+3.4}" text-anchor="middle" font-family="Barlow Condensed" font-weight="700" font-size="9.5" fill="${lit.includes(z)&&st!=='broken'?tc:'#5a6069'}">${L[z]}</text>`; }
  // power cells (orbit)
  const n=o.cells||1; s += `<g style="transform-origin:60px 60px;animation:orbit ${n===3?14:10}s linear infinite">`;
  for (let i=0;i<n;i++){ const p=pt(-60+i*(360/n), R+19); s += `<rect x="${p[0]-3}" y="${p[1]-5}" width="6" height="10" rx="3" fill="${tc}" opacity="${st==='broken'?.35:.95}"/>`; }
  s += `</g>`;
  if (o.label!==false) {
    s += `<text x="60" y="${o.value!==undefined?62:64}" text-anchor="middle" font-family="Barlow Condensed" font-weight="700" font-size="${o.value!==undefined?21:13}" fill="${st==='broken'?'#FF3B4E':'#F3F0E9'}">${o.value!==undefined?o.value:(o.tier||'t2').toUpperCase()}</text>`;
    if (o.value!==undefined) s += `<text x="60" y="73" text-anchor="middle" font-family="Barlow Condensed" font-weight="600" font-size="8" letter-spacing="1.2" fill="${tc}">${(o.tier||'t2').toUpperCase()} ${core.toUpperCase()}</text>`;
  }
  return s+'</svg>';
}
function mount(){ document.querySelectorAll('[data-body]').forEach(e=>{ e.innerHTML = bodySVG(JSON.parse(e.dataset.body)); });
  document.querySelectorAll('[data-halo]').forEach(e=>{ e.innerHTML = haloSVG(JSON.parse(e.dataset.halo)); }); }
document.addEventListener('DOMContentLoaded', mount);
