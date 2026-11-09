// Suburb benchmark scorer: reads run records (runs/*.json, format in README.md) and the truth sheets (sites/<site>.json), prints
// five scores per run (truth, reach, cost, trace, consistency) and, with --write, the table in docs/handoffs/suburb-bench-latest.md.
// Usage: node research/benchmark/score.mjs [--write] [run files...]   |   node research/benchmark/score.mjs --selftest
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const LATEST = path.join(HERE, '..', '..', 'docs', 'handoffs', 'suburb-bench-latest.md');

// the fixed 15-item reach list: an item counts when the answer gives it with a value (any source)
export const REACH = ['lot_id', 'lot_area', 'address', 'lot_boundary', 'footprints', 'heights', 'height_basis', 'zones', 'overlays', 'heritage',
  'ground_levels', 'kerbs', 'street_trees', 'transport', 'shadows'];
// facts compared with the truth sheet; consistency counts the ones that differ between runs of the same site and mode
const FACTS = ['lot_id', 'lot_area_m2', 'position', 'zones', 'overlays', 'heritage', 'nearest_station', 'official_kerb', 'tallest_neighbour'];
const TOL = {area: (t) => Math.max(2, 0.02 * t), position_m: 1.0, height_m: 1.0, station: (t) => Math.max(50, 0.15 * t)};

const norm = s => String(s ?? '').toUpperCase().replace(/\s+/g, ' ').trim();
// lot ids in any spelling ("Lot 1 TP128421", "1\TP128421", "1//DP724850", "Lot 1 DP 724850") -> "1/TP128421"
export function lotKey(s){
  const t = norm(s).replace(/^LOT\s*/, '').replace(/\bON\b/g, ' ');
  const plan = ([...t.matchAll(/(?:^|[^A-Z])(CP|DP|LP|PC|PS|RP|SP|TP|CS)\s*-?\s*(\d{3,})/g)].pop() || []).slice(1).join('');
  const lot = (t.match(/^([A-Z0-9]+)[\s\\/]/) || [])[1] || (/^(CM|CP|SP)/.test(plan) ? '' : '');
  return (lot && !/^(CM|CP|DP|LP|PC|PS|RP|SP|TP|CS)\d/.test(lot) ? lot : '') + '/' + plan;
}
// overlay schedules and areas count as the code itself: "DDO61-A2", "DDO61 (Area 2)" -> DDO61
const codeSet = a => [...new Set((a || []).map(c => norm(c).replace(/\s*\(AREA\s*\d+\)|-A\d+$/g, '').replace(/\s+/g, '')))].sort();
// NSW LEP map families from an answer's codes in any spelling ("FSR 10:1", "FSR:10", "HOB:CA", "Height of Buildings")
const LEP = {HOB: /HOB|HEIGHT/, FSR: /FSR|FLOOR SPACE/, LSZ: /LSZ|LOT SIZE|MLS/, LRA: /LRA|ACQUISITION|RESERVATION/};
export const lepFamilies = a => Object.keys(LEP).filter(f => (a || []).some(c => LEP[f].test(norm(c)))).sort();
const sameSet = (a, b) => JSON.stringify(codeSet(a)) === JSON.stringify(codeSet(b));
const d2 = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);

// position error: mean distance from each answered corner to the truth corner of the same name (NE, SE, SW, NW), or the nearest one if unnamed; else the answered centre to the truth centre
export function positionError(fact, truth){
  const T = truth.lot.corners_mga, tc = Object.values(T), B = truth.lot.boundary_mga;
  const given = fact?.corners_mga ? Object.entries(fact.corners_mga).filter(([, p]) => Array.isArray(p) && p.length === 2 && p.every(Number.isFinite)) : [];
  // with the whole boundary in the sheet: each answered corner's distance to the nearest real lot vertex, so which vertex an answer calls "NE" on an odd-shaped lot does not matter
  if (given.length && B) return given.reduce((s, [, p]) => s + Math.min(...B.map(q => d2(p, q))), 0) / given.length;
  if (given.length) return given.reduce((s, [k, p]) => s + (T[k] ? d2(p, T[k]) : Math.min(...tc.map(q => d2(p, q)))), 0) / given.length;
  if (Array.isArray(fact?.centre_mga)) return d2(fact.centre_mga, truth.lot.centre_mga);
  return null;
}

// one fact against the truth: {ok: true|false|null (not answered), why}
export function check(key, f, t){
  const facts = f || {};
  switch (key){
    case 'lot_id': {
      if (facts.lot_id == null) return {ok: null};
      // a strata building: the site point sits on common property (CM), so any lot of the same plan names the site
      const a = lotKey(facts.lot_id), b = lotKey(t.lot.id), strata = /^CM/i.test(String(t.lot.id));
      return {ok: strata ? a.split('/')[1] === b.split('/')[1] : a === b, why: facts.lot_id + ' vs ' + t.lot.id + (strata ? ' (strata: plan compared)' : '')};
    }
    case 'lot_area_m2': return facts.lot_area_m2 == null ? {ok: null} : {ok: Math.abs(facts.lot_area_m2 - t.lot.area_m2) <= TOL.area(t.lot.area_m2), why: facts.lot_area_m2 + ' vs ' + t.lot.area_m2 + ' m²'};
    case 'position': { const e = positionError(facts.position, t); return e == null ? {ok: null} : {ok: e <= TOL.position_m, error_m: +e.toFixed(2), why: e.toFixed(2) + ' m off the lot'}; }
    case 'zones': return facts.zones == null ? {ok: null} : {ok: sameSet(facts.zones, t.zones.codes), why: codeSet(facts.zones).join('/') + ' vs ' + t.zones.codes.join('/')};
    case 'overlays': {
      if (facts.overlays == null) return {ok: null};
      if (t.region === 'nsw' && t.overlays.families){
        // NSW: the primary LEP maps compared by family; other maps an answer names (acid sulfate, flood, clauses) are not checked
        const opt = t.overlays.optional_families || [], got = lepFamilies(facts.overlays).filter(f => !opt.includes(f)), want = t.overlays.families.filter(f => !opt.includes(f));
        return {ok: sameSet(got, want), why: (got.join('/') || 'none') + ' vs ' + want.join('/') + ' (LEP map families)'};
      }
      const opt = codeSet(t.overlays.optional), drop = a => codeSet(a).filter(c => !opt.includes(c));
      return {ok: sameSet(drop(facts.overlays), drop(t.overlays.codes)), why: drop(facts.overlays).join('/') + ' vs ' + drop(t.overlays.codes).join('/')};
    }
    case 'heritage': {
      if (facts.heritage == null) return {ok: null};
      const h = facts.heritage, want = t.region === 'nsw' ? (t.heritage.items.length ? norm(t.heritage.grading) : null) : t.heritage.grading;
      const got = h.grading == null || /^(NONE|NOT (GRADED|LISTED|PUBLISHED)|NO GRADING)/.test(norm(h.grading)) ? null : norm(h.grading);
      // NSW significance is compared by its level word: "Local significance", "LOCAL (ITEM - GENERAL)" and "Local" are the same
      const lvl = g => t.region === 'nsw' && g ? (g.match(/\b(LOCAL|STATE|NATIONAL)\b/) || [g])[0] : g;
      const opt = codeSet(t.heritage.optional), dropHo = a => codeSet(a).filter(c => !opt.includes(c));
      const hoOk = t.region === 'nsw' || sameSet(dropHo(h.overlay || []), dropHo(t.heritage.overlay));
      return {ok: hoOk && (want == null ? got == null : lvl(got) === lvl(norm(want))), why: 'grading ' + (got ?? 'none') + ' vs ' + (want ?? 'none') + (hoOk ? '' : ', HO ' + codeSet(h.overlay).join('/') + ' vs ' + t.heritage.overlay.join('/'))};
    }
    case 'nearest_station': {
      const s = facts.nearest_station; if (s == null || !t.nearest_station) return {ok: null};
      const stn = n => norm(n).replace(/\s+(RAILWAY\s+|TRAIN\s+)?STATION$/, '');
      const nameOk = stn(s.name) === stn(t.nearest_station.name);
      const distOk = s.distance_m == null || Math.abs(s.distance_m - t.nearest_station.distance_m) <= TOL.station(t.nearest_station.distance_m);
      return {ok: nameOk && distOk, why: s.name + ' ' + s.distance_m + ' m vs ' + t.nearest_station.name + ' ' + t.nearest_station.distance_m + ' m'};
    }
    case 'official_kerb': return typeof facts.official_kerb !== 'boolean' ? {ok: null} : {ok: facts.official_kerb === t.official_kerb.exists, why: facts.official_kerb + ' vs ' + t.official_kerb.exists};
    case 'tallest_neighbour': {
      const n = facts.tallest_neighbour; if (n == null) return {ok: null};
      if (t.tallest_neighbour.value_m == null) return {ok: !(n.basis === 'official' && n.height_m != null), why: 'no official height here; answer ' + (n.height_m ?? 'none') + ' (' + (n.basis || 'basis not said') + ')'};
      if (n.height_m == null) return {ok: false, why: 'missed the official height ' + t.tallest_neighbour.value_m + ' m'};
      const e = Math.abs(n.height_m - t.tallest_neighbour.value_m);
      return {ok: e <= TOL.height_m, error_m: +e.toFixed(2), why: n.height_m + ' vs ' + t.tallest_neighbour.value_m + ' m'};
    }
  }
  throw new Error('unknown fact ' + key);
}

const factValue = (key, f) => {
  const v = f?.[key]; if (v == null) return null;
  if (key === 'lot_id') return lotKey(v);
  if (key === 'zones' || key === 'overlays') return codeSet(v).join('/');
  if (key === 'nearest_station') return norm(v.name) + '@' + Math.round((v.distance_m ?? 0) / 25) * 25;
  if (key === 'tallest_neighbour') return (v.height_m == null ? 'none' : Math.round(v.height_m * 2) / 2) + '|' + (v.basis || '');
  if (key === 'position') return JSON.stringify(v.corners_mga ? Object.values(v.corners_mga).map(p => p.map(Math.round)) : (v.centre_mga || []).map(Math.round));
  if (key === 'heritage') return norm(v.grading) + '|' + codeSet(v.overlay).join('/');
  if (key === 'lot_area_m2') return Math.round(v);
  return JSON.stringify(v);
};

export function scoreRun(run, truth){
  const res = Object.fromEntries(FACTS.map(k => [k, check(k, run.facts, truth)]));
  const wrong = FACTS.filter(k => res[k].ok === false);
  const nums = run.numbers || [];
  return {
    site: run.site, mode: run.mode, run: run.run, date: run.date,
    truth: {wrong: wrong.length, wrong_facts: wrong.map(k => k + ': ' + res[k].why), position_m: res.position.error_m ?? null, height_m: res.tallest_neighbour.error_m ?? null, unanswered: FACTS.filter(k => res[k].ok === null)},
    reach: REACH.filter(k => run.reach?.[k] === true).length,
    cost: {tool_calls: run.cost?.tool_calls ?? null, minutes: run.cost?.minutes ?? null},
    trace: nums.length ? Math.round(100 * nums.filter(n => n.source && n.source.stamp).length / nums.length) : null
  };
}

// consistency: per site and mode, count the facts whose value differs between runs (0 = same answer every time)
export function consistency(runs){
  const out = {};
  for (const r of runs){ (out[r.site + '|' + r.mode] ||= []).push(r); }
  return Object.fromEntries(Object.entries(out).map(([k, rs]) => [k, rs.length < 2 ? null : FACTS.filter(f => new Set(rs.map(r => JSON.stringify(factValue(f, r.facts)))).size > 1).length]));
}

function table(scored, cons){
  const rows = scored.map(s => `| ${s.site} | ${s.mode} | ${s.run} | ${s.date || ''} | ${s.truth.wrong} | ${s.truth.position_m ?? '–'} | ${s.truth.height_m ?? '–'} | ${s.reach}/15 | ${s.cost.tool_calls ?? '–'} | ${s.cost.minutes ?? '–'} | ${s.trace == null ? '–' : s.trace + '%'} | ${cons[s.site + '|' + s.mode] ?? '–'} |`);
  return '| Site | Mode | Run | Date | Wrong facts | Position m | Height m | Reach | Calls | Minutes | Trace | Differing facts (consistency) |\n|---|---|---|---|---|---|---|---|---|---|---|---|\n' + rows.join('\n');
}

function selftest(){
  const t = JSON.parse(fs.readFileSync(path.join(HERE, 'sites', 'footscray.json'), 'utf8'));
  const perfect = {site: t.site, mode: 'with', run: 1, facts: {lot_id: 'Lot ' + t.lot.id.replace('\\', ' '), lot_area_m2: t.lot.area_m2, position: {corners_mga: t.lot.corners_mga},
    zones: t.zones.codes, overlays: t.overlays.codes, heritage: {overlay: t.heritage.overlay, grading: null}, nearest_station: {name: t.nearest_station.name + ' Station', distance_m: t.nearest_station.distance_m},
    official_kerb: t.official_kerb.exists, tallest_neighbour: {height_m: 12, basis: 'OpenStreetMap'}}, reach: Object.fromEntries(REACH.map(k => [k, true])), cost: {tool_calls: 10, minutes: 5},
    numbers: [{what: 'area', value: t.lot.area_m2, source: {stamp: 'x'}}]};
  const a = scoreRun(perfect, t);
  const shifted = JSON.parse(JSON.stringify(perfect));
  for (const p of Object.values(shifted.facts.position.corners_mga)){ p[0] += 1.2; p[1] += 0.9; }
  shifted.facts.zones = ['GRZ1']; shifted.facts.tallest_neighbour = {height_m: 12, basis: 'official'}; shifted.numbers.push({what: 'height', value: 12});
  const b = scoreRun(shifted, t), c = consistency([perfect, shifted]);
  const ok = [a.truth.wrong === 0, a.reach === 15, a.trace === 100, b.truth.wrong === 3, b.truth.position_m > 1.0 && b.truth.position_m <= 1.5, b.trace === 50, c['footscray|with'] === 3,
    lotKey('1\\TP128421') === lotKey('Lot 1 on TP 128421'), lotKey('1//DP724850') === lotKey('Lot 1 DP724850'), lotKey('CM3\\PS810967').endsWith('/PS810967'), lotKey('Lot 101 PS810967') === '101/PS810967'];
  ok.forEach((v, i) => { if (!v) { console.log('selftest ' + i + ' FAILED', JSON.stringify({a, b, c})); process.exitCode = 1; } });
  if (!process.exitCode) console.log('selftest OK (' + ok.length + ' checks)');
}

if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])){
  const args = process.argv.slice(2);
  if (args.includes('--selftest')) selftest();
  else {
    const files = args.filter(a => !a.startsWith('--'));
    const dir = path.join(HERE, 'runs');
    const list = files.length ? files : (fs.existsSync(dir) ? fs.readdirSync(dir).filter(f => f.endsWith('.json') && !f.startsWith('_')).map(f => path.join(dir, f)) : []);
    const runs = list.map(f => JSON.parse(fs.readFileSync(f, 'utf8')));
    const scored = runs.map(r => scoreRun(r, JSON.parse(fs.readFileSync(path.join(HERE, 'sites', r.site + '.json'), 'utf8'))));
    const cons = consistency(runs);
    for (const s of scored) console.log(JSON.stringify(s));
    if (args.includes('--write')){
      const head = fs.readFileSync(LATEST, 'utf8').split('<!-- table -->')[0];
      fs.writeFileSync(LATEST, head + '<!-- table -->\n' + (scored.length ? table(scored, cons) : 'No runs yet.') + '\n');
      console.log('wrote ' + path.relative(process.cwd(), LATEST));
    }
    if (!runs.length) console.log('no run records in runs/ (the first with/without run waits for connector parity)');
  }
}
