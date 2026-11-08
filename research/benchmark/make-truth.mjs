// Suburb benchmark: draft one truth sheet per site straight from the official servers (never through OpenFetch's app or connector,
// so the benchmark cannot grade OpenFetch against itself). A thread checks each sheet by eye and sets checked.by / checked.on.
// Usage: node research/benchmark/make-truth.mjs [site-id ...]   (no ids = all sites in sites.json)
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const VICMAP = 'https://services-ap1.arcgis.com/P744lA0wf4LlBZ84/ArcGIS/rest/services';
const SIX = 'https://portal.spatial.nsw.gov.au/server/rest/services';
const EPI = 'https://mapprod3.environment.nsw.gov.au/arcgis/rest/services/Planning/EPI_Primary_Planning_Layers/MapServer';
const MIRROR = 'https://openfetch-data.pages.dev';
const DATASETS = path.join(HERE, '..', '..', 'data', 'datasets');

const sites = JSON.parse(fs.readFileSync(path.join(HERE, 'sites.json'), 'utf8'));
const want = process.argv.slice(2);

async function get(url, tries = 3){
  for (let i = 0; ; i++){
    try {
      const r = await fetch(url, {signal: AbortSignal.timeout(45000)});
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const j = await r.json();
      if (j.error) throw new Error(JSON.stringify(j.error).slice(0, 200));
      return j;
    } catch (e){ if (i + 1 >= tries) throw new Error(url.split('?')[0] + ': ' + e.message); await new Promise(r => setTimeout(r, 2000 * (i + 1))); }
  }
}
const qs = o => Object.entries(o).map(([k, v]) => k + '=' + encodeURIComponent(typeof v === 'object' ? JSON.stringify(v) : v)).join('&');
const query = (layer, o) => get(layer + '/query?' + qs({f: 'json', outFields: '*', ...o}));
const atPoint = (lon, lat) => ({geometry: lon + ',' + lat, geometryType: 'esriGeometryPoint', inSR: 4326, spatialRel: 'esriSpatialRelIntersects'});
const atXY = (x, y, sr) => ({geometry: x + ',' + y, geometryType: 'esriGeometryPoint', inSR: sr, spatialRel: 'esriSpatialRelIntersects'});

function ringArea(r){ let a = 0; for (let i = 0, j = r.length - 1; i < r.length; j = i++) a += (r[j][0] + r[i][0]) * (r[j][1] - r[i][1]); return a / 2; }
function centroid(r){
  let a = 0, cx = 0, cy = 0;
  for (let i = 0, j = r.length - 1; i < r.length; j = i++){ const f = r[j][0] * r[i][1] - r[i][0] * r[j][1]; a += f; cx += (r[j][0] + r[i][0]) * f; cy += (r[j][1] + r[i][1]) * f; }
  return [cx / (3 * a), cy / (3 * a)];
}
function inside(p, r){ let c = false; for (let i = 0, j = r.length - 1; i < r.length; j = i++){ const [xi, yi] = r[i], [xj, yj] = r[j]; if ((yi > p[1]) !== (yj > p[1]) && p[0] < (xj - xi) * (p[1] - yi) / (yj - yi) + xi) c = !c; } return c; }
// four corners of the lot: the points furthest out along the two diagonals of the grid (NE, SE, SW, NW), rounded to the cm
function corners(ring){
  const pick = f => ring.reduce((b, p) => f(p) > f(b) ? p : b, ring[0]);
  return {NE: pick(p => p[0] + p[1]), SE: pick(p => p[0] - p[1]), SW: pick(p => -p[0] - p[1]), NW: pick(p => -p[0] + p[1])};
}
const r2 = n => Math.round(n * 100) / 100;
const xy = p => [r2(p[0]), r2(p[1])];
const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);

// Transverse Mercator (Krüger series, GRS80), zone from the site; used only for the hosted roofprint copy, whose cells are lon/lat
function toMGA(lon, lat, zone){
  const a = 6378137, f = 1 / 298.257222101, k0 = 0.9996, n = f / (2 - f), A = a / (1 + n) * (1 + n * n / 4 + n ** 4 / 64);
  const al = [n / 2 - 2 * n * n / 3 + 5 * n ** 3 / 16, 13 * n * n / 48 - 3 * n ** 3 / 5, 61 * n ** 3 / 240];
  const e = Math.sqrt(f * (2 - f)), phi = lat * Math.PI / 180, lam = (lon - (zone * 6 - 183)) * Math.PI / 180;
  const t = Math.sinh(Math.atanh(Math.sin(phi)) - e * Math.atanh(e * Math.sin(phi)));
  const xi = Math.atan2(t, Math.cos(lam)), eta = Math.atanh(Math.sin(lam) / Math.sqrt(1 + t * t));
  let x = eta, y = xi;
  for (let j = 1; j <= 3; j++){ x += al[j - 1] * Math.cos(2 * j * xi) * Math.sinh(2 * j * eta); y += al[j - 1] * Math.sin(2 * j * xi) * Math.cosh(2 * j * eta); }
  return [500000 + k0 * A * x, 10000000 + k0 * A * y];
}

// official kerb lines: a registry dataset of thing "kerbs", kind official, drawn in the app, titled as kerbs (not road pavement), from
// this council: file name starting "<council>." or ending "-<council>.json" (data.gov.au copies)
function officialKerbSources(region, council){
  const dir = path.join(DATASETS, region), slug = council.toLowerCase().replace(/\s+/g, '-'), out = [];
  for (const f of fs.readdirSync(dir)){
    if (!(f.startsWith(slug + '.') || f.endsWith('-' + slug + '.json'))) continue;
    const d = JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8'));
    if (d.thing === 'kerbs' && d.kind === 'official' && d.status === 'drawn' && /kerb/i.test(d.title || '') && !/\.openfetch\./.test(d.id)) out.push(d.id);
  }
  return out;
}

async function geelongRoofprints(site, lotRing, lotC, zone, radius){
  const idx = await get(MIRROR + '/geelong-roofprints/index.json');
  const Q = idx.q, CELL = idx.cell, cells = new Set(idx.cells), seen = [];
  const cx = Math.floor(site.lon / CELL), cy = Math.floor(site.lat / CELL);
  for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++){
    const c = (cx + dx) + '_' + (cy + dy); if (!cells.has(c)) continue;
    const body = await get(MIRROR + '/geelong-roofprints/c/' + c + '.json');
    const ox = Math.round((cx + dx) * CELL * Q), oy = Math.round((cy + dy) * CELL * Q);
    for (const [props, parts] of body.f){
      const ring = []; let lx = ox, ly = oy; const g = parts[0];
      for (let i = 0; i < g.length; i += 2){ lx += g[i]; ly += g[i + 1]; ring.push(toMGA(lx / Q, ly / Q, zone)); }
      if (ring.length < 3 || props.height == null) continue;
      const c0 = centroid(ring);
      if (inside(lotC, ring) || inside(c0, lotRing)) continue;   // the site's own building is not a neighbour
      const d = dist(c0, lotC); if (d <= radius) seen.push({height_m: props.height, distance_m: Math.round(d), centre_mga: xy(c0)});
    }
  }
  seen.sort((a, b) => b.height_m - a.height_m);
  return seen[0] || null;
}

async function vic(site){
  const sr = 7855, zone = 55, notes = [];
  // the point is the address point of site.address (Vicmap Address, looked up once by hand: the address-name query is slow)
  const lot = (await query(VICMAP + '/Vicmap_Parcel/FeatureServer/0', {...atPoint(site.lon, site.lat), outSR: sr})).features[0];
  if (!lot) throw new Error('no Vicmap parcel at the site point');
  const A = lot.attributes, ring = lot.geometry.rings.reduce((b, r) => Math.abs(ringArea(r)) > Math.abs(ringArea(b)) ? r : b);
  const lotC = centroid(ring);
  const addr = (await query(VICMAP + '/Vicmap_Address/FeatureServer/0', {geometry: JSON.stringify({rings: lot.geometry.rings, spatialReference: {wkid: sr}}), geometryType: 'esriGeometryPolygon', inSR: sr, spatialRel: 'esriSpatialRelIntersects', returnGeometry: false, resultRecordCount: 50})).features.map(f => f.attributes);
  const zones = (await query(VICMAP + '/Vicmap_Planning/FeatureServer/3', {...atXY(lotC[0], lotC[1], sr), returnGeometry: false})).features.map(f => f.attributes.zone_code);
  const ovs = (await query(VICMAP + '/Vicmap_Planning/FeatureServer/2', {...atXY(lotC[0], lotC[1], sr), returnGeometry: false})).features.map(f => f.attributes.zone_code);
  const st = (await query(VICMAP + '/Vicmap_Transport/FeatureServer/2', {where: "feature_type_code='rail_station'", geometry: lotC.join(','), geometryType: 'esriGeometryPoint', inSR: sr, distance: 4000, units: 'esriSRUnit_Meter', outSR: sr})).features
    .map(f => ({name: f.attributes.name, distance_m: Math.round(dist([f.geometry.x, f.geometry.y], lotC))})).sort((a, b) => a.distance_m - b.distance_m);
  let tallest = {value_m: null, status: 'no official building height published here', source: null};
  if (site.council === 'GREATER GEELONG'){
    const t = await geelongRoofprints(site, ring, lotC, zone, 100);
    if (t) tallest = {value_m: t.height_m, status: 'official', distance_m: t.distance_m, centre_mga: t.centre_mga, basis: 'roof height above ground',
      source: 'City of Greater Geelong roofprints (LiDAR + photogrammetry), CC BY 3.0 AU, via the OpenFetch hosted copy; GDA94 lon/lat projected to MGA 55 (about 1.5 m datum shift ignored for picking the neighbour)'};
  }
  const kerbs = officialKerbSources('vic', site.council_file || site.council);
  const ho = ovs.filter(c => /^HO\d/.test(c));
  return {
    lot: {id: A.parcel_spi || (A.parcel_lot_number + '\\' + A.parcel_plan_number), lot: A.parcel_lot_number, plan: A.parcel_plan_number, pfi: A.parcel_pfi,
      area_m2: Math.round(Math.abs(ringArea(ring))), area_basis: 'planar area of the Vicmap Parcel polygon in MGA 55 (GDA2020)',
      address: addr.map(a => a.ezi_address).filter(Boolean).sort().slice(0, 5),
      corners_mga: Object.fromEntries(Object.entries(corners(ring)).map(([k, p]) => [k, xy(p)])), centre_mga: xy(lotC), crs: 'EPSG:7855 GDA2020 MGA zone 55',
      source: 'Vicmap Property, Parcel Map Polygons (PARCEL_MP), DEECA, CC BY 4.0'},
    tallest_neighbour: {...tallest, radius_m: 100},
    zones: {codes: [...new Set(zones)].sort(), at: 'lot centre', source: 'Vicmap Planning, PLAN_ZONE, DTP, CC BY 4.0'},
    overlays: {codes: [...new Set(ovs)].sort(), at: 'lot centre', source: 'Vicmap Planning, PLAN_OVERLAY, DTP, CC BY 4.0'},
    heritage: {overlay: [...new Set(ho)].sort(), grading: null, grading_status: site.council === 'MELBOURNE' ? 'check the City of Melbourne heritage gradings by eye' : 'the council publishes no heritage gradings as open data',
      source: 'Vicmap Planning, PLAN_OVERLAY (HO codes)'},
    nearest_station: st[0] ? {...st[0], next: st[1] || null, source: 'Vicmap Transport, TR_RAIL_INFRASTRUCTURE rail_station, DTP, CC BY 4.0'} : null,
    official_kerb: {exists: kerbs.length > 0, datasets: kerbs, source: 'OpenFetch registry (data/datasets) of official council kerb datasets, checked by eye against the council portal'},
    notes
  };
}

async function nsw(site){
  const sr = 7856, notes = [];
  const lot = (await query(SIX + '/NSW_Land_Parcel_Property_Theme_multiCRS/FeatureServer/8', site.lotid ? {where: "lotidstring='" + site.lotid + "'", outSR: sr} : {...atPoint(site.lon, site.lat), outSR: sr})).features[0];
  if (!lot) throw new Error('no NSW Cadastre lot at the site point');
  const A = lot.attributes, ring = lot.geometry.rings.reduce((b, r) => Math.abs(ringArea(r)) > Math.abs(ringArea(b)) ? r : b);
  const lotC = centroid(ring);
  const pt = atXY(lotC[0], lotC[1], sr);
  const zones = (await query(EPI + '/2', {...pt, returnGeometry: false})).features.map(f => f.attributes);
  const her = (await query(EPI + '/0', {...pt, returnGeometry: false})).features.map(f => f.attributes);
  const hob = (await query(EPI + '/5', {...pt, returnGeometry: false})).features.map(f => f.attributes);
  const st = (await query(SIX + '/NSW_FOI_Transport_Facilities/MapServer/1', {where: "generalname LIKE '%RAILWAY STATION'", geometry: lotC.join(','), geometryType: 'esriGeometryPoint', inSR: sr, distance: 4000, units: 'esriSRUnit_Meter', outSR: sr})).features
    .map(f => ({name: f.attributes.generalname || f.attributes.GENERALNAME || f.attributes.name, distance_m: Math.round(dist([f.geometry.x, f.geometry.y], lotC))})).sort((a, b) => a.distance_m - b.distance_m);
  const kerbs = officialKerbSources('nsw', site.council_file || site.council);
  const pick = (o, re) => { const k = Object.keys(o).find(k => re.test(k)); return k ? o[k] : null; };
  return {
    lot: {id: pick(A, /^lotidstring$/i), lot: pick(A, /^lotnumber$/i), section: pick(A, /^sectionnumber$/i) || null, plan: pick(A, /^planlabel$/i),
      area_m2: Math.round(Math.abs(ringArea(ring))), area_basis: 'planar area of the NSW Cadastre lot polygon in MGA 56 (GDA2020)',
      stated_area_m2: pick(A, /^planlotarea$/i) || null,
      corners_mga: Object.fromEntries(Object.entries(corners(ring)).map(([k, p]) => [k, xy(p)])), centre_mga: xy(lotC), crs: 'EPSG:7856 GDA2020 MGA zone 56',
      source: 'NSW Cadastre (Lot), DCS Spatial Services, CC BY 4.0'},
    tallest_neighbour: {value_m: null, status: 'no official building height published here', source: null, radius_m: 100},
    zones: {codes: [...new Set(zones.map(z => pick(z, /^SYM_CODE$/i)))].sort(), epi: [...new Set(zones.map(z => pick(z, /^EPI_NAME$/i)))], at: 'lot centre', source: 'NSW Planning Portal, EPI Land Zoning, DPHI, CC BY 4.0'},
    overlays: {codes: hob.map(h => pick(h, /^MAX_B_H$/i) == null ? 'HOB ' + (pick(h, /^LAY_CLASS$/i) || 'none') : 'HOB ' + pick(h, /^MAX_B_H$/i) + ' ' + (pick(h, /^UNITS$/i) || '')).map(s => s.trim()), at: 'lot centre', source: 'NSW Planning Portal, EPI Height of Building, DPHI, CC BY 4.0'},
    heritage: {items: her.map(h => ({id: pick(h, /^H_ID$/i), name: pick(h, /^H_NAME$/i), significance: pick(h, /^SIG$/i)})), grading: her.length ? her.map(h => pick(h, /^SIG$/i)).join(', ') : 'not a listed item',
      source: 'NSW Planning Portal, EPI Heritage, DPHI, CC BY 4.0'},
    nearest_station: st[0] ? {...st[0], next: st[1] || null, source: 'NSW Features of Interest, Train Station, DCS Spatial Services, CC BY 4.0'} : null,
    official_kerb: {exists: kerbs.length > 0, datasets: kerbs, source: 'OpenFetch registry (data/datasets) of official council kerb datasets, checked by eye against the council portal'},
    notes
  };
}

fs.mkdirSync(path.join(HERE, 'sites'), {recursive: true});
for (const site of sites.sites){
  if (want.length && !want.includes(site.id)) continue;
  try {
    const t = site.region === 'vic' ? await vic(site) : await nsw(site);
    const file = path.join(HERE, 'sites', site.id + '.json');
    const old = fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, 'utf8')) : null;
    const sheet = {site: site.id, name: site.name, region: site.region, council: site.council, rank: site.rank, point: [site.lon, site.lat],
      made: new Date().toISOString().slice(0, 10), checked: old?.checked || {by: null, on: null, note: 'not yet checked by eye'}, ...t};
    fs.writeFileSync(file, JSON.stringify(sheet, null, 2) + '\n');
    console.log(site.id + ': ' + sheet.lot.id + ', ' + sheet.lot.area_m2 + ' m², zones ' + sheet.zones.codes.join('/') + ', overlays ' + sheet.overlays.codes.join('/') +
      ', station ' + (sheet.nearest_station ? sheet.nearest_station.name + ' ' + sheet.nearest_station.distance_m + ' m' : 'none') + ', kerb ' + sheet.official_kerb.exists + ', tallest ' + sheet.tallest_neighbour.value_m);
  } catch (e){ console.log(site.id + ': FAILED ' + e.message); process.exitCode = 1; }
}
