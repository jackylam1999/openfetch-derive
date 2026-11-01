// Proves rhino3dm can write Picture objects by reusing a template's attributes.
const fs = require('fs'), path = require('path');
const rhino3dm = require('rhino3dm');
const HERE = __dirname;
const SRC = 'G:\\My Drive\\OpenFetch (Claude)\\research\\rhino-picture\\picture-r7.3dm';
const MARKER = Buffer.from('F70F463F8992C04FBF667D7B7DC658BF', 'hex');

function markerOffsets(buf) {
  const out = [];
  let i = buf.indexOf(MARKER);
  while (i >= 0) { out.push(i); i = buf.indexOf(MARKER, i + 1); }
  return out;
}

function write(doc, version, file) {
  const o = new (doc.__rhino.File3dmWriteOptions)();
  o.version = version;
  o.saveUserData = true;
  const bytes = Buffer.from(doc.toByteArrayOptions(o));
  fs.writeFileSync(path.join(HERE, file), bytes);
  console.log(file, bytes.length, 'bytes, marker offsets', markerOffsets(bytes), 'header', bytes.subarray(24, 32).toString('ascii').trim());
  return bytes;
}

(async () => {
  const rhino = await rhino3dm();
  console.log('PlaneSurface ctor keys:', Object.getOwnPropertyNames(rhino.PlaneSurface || {}).join(','));
  console.log('Transform statics:', Object.getOwnPropertyNames(rhino.Transform).filter(k => /scale|transl/i.test(k)).join(','));
  console.log('NurbsSurface statics:', Object.getOwnPropertyNames(rhino.NurbsSurface).join(','));

  const src = rhino.File3dm.fromByteArray(new Uint8Array(fs.readFileSync(SRC)));
  console.log('source objects', src.objects().count, 'materials', src.materials().count, 'embedded', src.embeddedFiles().count);
  const so = src.objects().get(0);
  const geom = so.geometry(), attrs = so.attributes();
  console.log('geometry', geom.constructor.name, 'faces', geom.faces().count, 'surface', geom.surfaces().get(0).constructor.name);
  console.log('attrs id', attrs.id, 'materialIndex', attrs.materialIndex, 'source', attrs.materialSource);

  // Step 1: minimal template
  const tpl = new rhino.File3dm();
  tpl.__rhino = rhino;
  const m0 = new rhino.Material();
  m0.name = 'picture';
  console.log('setBitmapTextureFilename', m0.setBitmapTextureFilename('aerial_photo.jpg'));
  tpl.materials().add(m0);
  attrs.materialIndex = 0;
  attrs.materialSource = rhino.ObjectMaterialSource.MaterialFromObject;
  tpl.objects().add(geom, attrs);
  write(tpl, 7, 'template-min.3dm');

  // Read the template back, as the web app will
  const t = rhino.File3dm.fromByteArray(new Uint8Array(fs.readFileSync(path.join(HERE, 'template-min.3dm'))));
  console.log('template reread: objects', t.objects().count, 'materials', t.materials().count, 'embedded', t.embeddedFiles().count);
  console.log('template texture', t.materials().get(0).getBitmapTexture().fileName);

  // Step 2: two pictures from the template, 400 x 400 m at MGA-like coordinates
  const out = new rhino.File3dm();
  out.__rhino = rhino;
  const tObj = t.objects().get(0);
  const SIZE = 400, X0 = 320000, Y0 = 5812000;
  for (let c = 1; c <= 2; c++) {
    const jpg = `aerial_photo_r1c${c}.jpg`;
    const data = new Uint8Array(fs.readFileSync(path.join(HERE, 'jpgs', jpg)));
    const ef = rhino.EmbeddedFile.fromByteArray(data);
    ef.fileName = jpg;
    console.log(jpg, 'embedded length', ef.length, 'fileName', ef.fileName);
    out.embeddedFiles().add(ef);

    const mat = new rhino.Material();
    mat.name = `aerial_r1c${c}`;
    mat.setBitmapTextureFilename(jpg);
    const before = out.materials().count;
    out.materials().add(mat);

    const g = tObj.geometry().duplicate();
    const k = SIZE / 100;
    const x = new rhino.Transform(1);
    x.m00 = k; x.m11 = k; x.m03 = X0 + (c - 1) * SIZE; x.m13 = Y0;
    g.transform(x);
    const a = tObj.attributes();
    a.name = `aerial r1c${c}`;
    a.materialIndex = before;
    a.materialSource = rhino.ObjectMaterialSource.MaterialFromObject;
    const id = out.objects().add(g, a);
    const bb = g.getBoundingBox();
    console.log('added', id, 'bbox', bb.min, bb.max);
  }
  console.log('embedded files in table', out.embeddedFiles().count);
  write(out, 7, 'test-out.3dm');
  const r = rhino.File3dm.fromByteArray(new Uint8Array(fs.readFileSync(path.join(HERE, 'test-out.3dm'))));
  console.log('test-out reread: objects', r.objects().count, 'materials', r.materials().count, 'embedded', r.embeddedFiles().count);
  for (let i = 0; i < r.objects().count; i++) { const o = r.objects().get(i), a = o.attributes(), b = o.geometry().getBoundingBox(); console.log(' object', i, a.id, a.name, 'mat', a.materialIndex, b.min, b.max); }
  const probe = t.objects().get(0).geometry().duplicate();
  const px = new rhino.Transform(1); px.m00 = 4; px.m11 = 3; probe.transform(px);
  const pb = probe.getBoundingBox(); console.log('non-uniform probe bbox', pb.min, pb.max);
  for (let i = 0; i < r.embeddedFiles().count; i++) { const e = r.embeddedFiles().get(i); console.log(' embedded', i, e.fileName, e.length); }
})().catch(e => { console.error('FAILED', e); process.exit(1); });
