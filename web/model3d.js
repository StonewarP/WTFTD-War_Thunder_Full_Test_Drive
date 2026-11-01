/* WTFTD — 3D viewer: a vehicle's or a weapon's model, read from the player's own game files and shown in WebGL. The layout
   of the files follows the public Dagor Engine sources. Nothing is stored and nothing can be exported. */
'use strict';

const MD_FLOAT2 = 1, MD_FLOAT3 = 2, MD_FLOAT4 = 3, MD_E3D = 4, MD_SHORT2 = 6, MD_SHORT4N = 10;  // vertex channel types
const MD_POSITION = 0, MD_NORMAL = 1, MD_TEXCOORD = 3;  // and uses
const MD_SKIN_CURRENT = 0x40000000;

class MdReader {
  constructor(bytes, pos = 0) {
    this.b = bytes;
    this.v = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    this.p = pos;
  }
  u16() { const x = this.v.getUint16(this.p, true); this.p += 2; return x; }
  u32() { const x = this.v.getUint32(this.p, true); this.p += 4; return x; }
  f32() { const x = this.v.getFloat32(this.p, true); this.p += 4; return x; }
  wide() { const x = this.u32(); this.p += 4; return x; }  // 64-bit offsets and sizes: all of them fit in 32
  skip(n) { this.p += n; }
  take(n) {
    if (this.p + n > this.b.length) throw new Error('model: cut short');
    const s = this.b.subarray(this.p, this.p + n);
    this.p += n;
    return s;
  }
  cstr(at) {
    const end = this.b.indexOf(0, at);
    return new TextDecoder().decode(this.b.subarray(at, end));
  }
}

// a packed block: its length word, then the unpacked size and the stream
function mdUnpack(r) {
  const block = r.take(r.u32() & 0x3FFFFFFF);
  return lzDecode(block.subarray(4), new MdReader(block).u32());
}

// the index format of meshoptimizer's meshopt_encodeIndexSequence
function mdIndices(data, count, wide) {
  if ((data[0] & 0xF0) !== 0xD0) throw new Error('model: index header');
  const out = new Uint32Array(count), base = [0, 0];
  let at = 1;
  for (let i = 0; i < count; i++) {
    let value = 0;
    for (let group = 0; group < 5; group++) {
      const byte = data[at++];
      value |= (byte & 0x7F) << (7 * group);
      if (byte < 0x80) break;
    }
    const which = value & 1, zig = value >>> 1, index = (base[which] + ((zig >>> 1) ^ -(zig & 1))) >>> 0;
    base[which] = index;
    out[i] = wide ? index : index & 0xFFFF;
  }
  return out;
}

const mdChannelBytes = ty => ([MD_E3D, 5, 6, 9, 15].includes(ty) ? 4 : [1, 7, MD_SHORT4N, 16].includes(ty) ? 8 : ty === MD_FLOAT3 ? 12 : 16);

function mdBuffers(data, payloadAt) {
  const h = new MdReader(data, 16), tableAt = h.u32(), count = h.u32(), payload = new MdReader(data, payloadAt), out = [];
  for (let i = 0; i < count; i++) {
    const e = new MdReader(data, tableAt + i * 32);
    const vertices = e.u32(), w1 = e.u32(), w2 = e.u32(), flags = e.u32(), declAt = e.u32(), declN = e.u32();
    const stride = w1 & 0xFF, wide = !!(flags & 0x40) || (vertices > 65536 && !(flags & 0x20)), packed = !!(flags & 0x200);
    const idxBytes = w2 & 0x0FFFFFFF, stored = packed ? (w1 >>> 8) | ((w2 >>> 28) * 16777216) : idxBytes;
    const buf = { stride, vertices, pos: -1, posTy: 0, nor: -1, uv: [] }, d = new MdReader(data, declAt);
    for (let k = 0, offset = 0; k < declN; k++) {
      const ty = d.u32() >>> 16, usage = d.u32(), index = d.u16();
      d.skip(2);
      if (usage === MD_POSITION) { buf.pos = offset; buf.posTy = ty; }
      if (usage === MD_NORMAL) buf.nor = offset;
      if (usage === MD_TEXCOORD && index < 2) buf.uv[index] = { offset, ty };
      offset += mdChannelBytes(ty);
    }
    buf.data = payload.take(vertices * stride);
    buf.view = new DataView(buf.data.buffer, buf.data.byteOffset, buf.data.byteLength);
    const raw = payload.take(stored), n = idxBytes / (wide ? 4 : 2);
    if (packed) buf.indices = mdIndices(raw, n, wide);
    else {
      const v = new DataView(raw.buffer, raw.byteOffset, raw.byteLength);
      buf.indices = Uint32Array.from({ length: n }, (_, k) => (wide ? v.getUint32(k * 4, true) : v.getUint16(k * 2, true)));
    }
    out.push(buf);
  }
  return out;
}

function mdVertexData(r, word) {
  if ((word & 0xE0000000) >>> 0 === 0xC0000000) return mdBuffers(mdUnpack(r), word & 0x3FFFFFFF);
  if ((word & 0xC0000000) !== 0) throw new Error('model: old packing');
  const header = r.take(word), h = new MdReader(header, 16), at = h.u32(), count = h.u32();
  let payload = 0;
  for (let i = 0; i < count; i++) {
    const e = new MdReader(header, at + i * 32), vertices = e.u32(), w1 = e.u32(), w2 = e.u32(), flags = e.u32();
    payload += vertices * (w1 & 0xFF) + (flags & 0x200 ? (w1 >>> 8) | ((w2 >>> 28) * 16777216) : w2 & 0x0FFFFFFF);
  }
  const all = new Uint8Array(word + payload);
  all.set(header);
  all.set(r.take(payload), word);
  return mdBuffers(all, word);
}

// the draw calls of a mesh: a table, and a second one for its see-through parts unless bit 31 of the word at +0x20 says none
function mdMesh(dump, at) {
  const r = new MdReader(dump, at), mainAt = r.u32(), mainN = r.u32();
  r.skip(8);
  const secondAt = r.u32(), secondN = r.u32();
  r.skip(8);
  const tables = r.u32() & 0x80000000 ? [[mainAt, mainN]] : [[mainAt, mainN], [secondAt, secondN]], elems = [];
  for (const [tableAt, n] of tables) {
    for (let i = 0; i < n; i++) {
      const e = new MdReader(dump, tableAt + i * 48);
      e.skip(8);
      const material = e.wide(), vdata = e.wide();
      e.skip(12);
      elems.push({ material, vdata, first: e.u32(), triangles: e.u32(), base: e.u32() });
    }
  }
  return elems;
}

function mdNodeNames(r) {
  const dump = r.take(r.u32()), m = new MdReader(dump), namesAt = m.u32(), count = m.u32();
  m.skip(8);
  const idsAt = m.u32(), names = [];
  for (let i = 0; i < count; i++) {
    names[new MdReader(dump, idsAt + i * 2).u16()] = m.cstr(new MdReader(dump, namesAt + i * 8).wide());
  }
  return names;
}

async function mdInflate(bytes) {
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('deflate'));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

// the skinned parts (tracks, cables) of the most detailed level, in model space
async function mdSkins(r, counts) {
  const section = r.p, variants = r.u32(), total = r.u32();
  if (variants !== 1) throw new Error('model: skin variants');
  r.skip(8);
  r.skip(12);
  const buffers = mdVertexData(r, r.u32());
  const z = new MdReader(await mdInflate(r.take(section + 8 + total - r.p))), parts = [];
  counts.forEach((count, l) => {
    const nodes = Array.from({ length: count }, () => z.u32()), sizes = Array.from({ length: count }, () => z.wide());
    nodes.forEach((_, i) => {
      const dump = z.take(sizes[i] & ~MD_SKIN_CURRENT);
      if (l === 0) parts.push({ skinned: true, elems: mdMesh(dump, 0x38), buffers });
    });
  });
  return parts;
}

async function mdModel(bytes) {
  const r = new MdReader(bytes), dumpSize = r.u32(), textures = r.u32();
  r.skip(8);
  const word = r.u32();
  if (textures !== 0xFFFFFFFF) r.take(r.u32());  // a few small models carry their texture names here
  const buffers = mdVertexData(r, word), dump = r.take(dumpSize), d = new MdReader(dump);
  const vec3 = at => { const c = new MdReader(dump, at); return [c.f32(), c.f32(), c.f32()]; };
  const offset = vec3(0x28), scale = vec3(0x38), names = mdNodeNames(r);
  const tableAt = d.u32(), lods = d.u32(), parts = [], skinCounts = [];
  for (let l = 0; l < lods; l++) {
    const scene = r.take(new MdReader(dump, tableAt + l * 16).wide()), s = new MdReader(scene), rigidsAt = s.u32(), rigids = s.u32();
    s.skip(12);
    skinCounts.push(s.u32());
    for (let i = 0; i < rigids; i++) {
      const e = new MdReader(scene, rigidsAt + i * 32), size = e.wide();
      e.skip(16);
      const node = names[e.u32()], mesh = r.take(size);
      if (l === 0) parts.push({ node, elems: mdMesh(mesh, 0), buffers });
    }
  }
  if (skinCounts.some(n => n > 0)) parts.push(...await mdSkins(r, skinCounts));
  return { parts, offset, scale };
}

// node name -> matrix in model space (column-major)
function mdTree(bytes) {
  const nodes = new Map();
  if (!bytes.length) return nodes;
  const r = new MdReader(bytes), size = r.u32() & 0xFFFFF, word = r.u32(), count = word & 0x7FFFFFFF;
  const dump = word & 0x80000000 ? mdUnpack(r) : bytes.subarray(8, 8 + size);
  for (let i = 0; i < count; i++) {
    const n = new MdReader(dump, i * 160 + 64), wtm = Float32Array.from({ length: 16 }, () => n.f32());
    n.skip(24);
    const name = n.cstr(n.wide());
    if (!nodes.has(name)) nodes.set(name, wtm);
  }
  return nodes;
}

// one texture coordinate of a vertex into out[at], out[at + 1]; stored in units of 1/4096 or as floats
function mdUv(vd, set, src, out, at) {
  const c = vd.uv[set];
  if (!c) return;
  const o = src * vd.stride + c.offset, v = vd.view;
  if (c.ty === MD_SHORT2) { out[at] = v.getInt16(o, true) / 4096; out[at + 1] = v.getInt16(o + 2, true) / 4096; }
  else if (c.ty === MD_FLOAT2) { out[at] = v.getFloat32(o, true); out[at + 1] = v.getFloat32(o + 4, true); }
}

// one mesh out of all the parts of a model, in model space, with the game's mirrored z turned round; its triangles are
// grouped by material, what shows through last
function mdAssemble({ parts, offset, scale }, tree, mats) {
  const groups = new Map(), keyOf = (p, e) => (p.skinned ? 'S' : 'R') + e.material + (p.label ? '|' + p.label : '');
  for (const p of parts) {
    for (const e of p.elems) {
      const key = keyOf(p, e);
      if (!groups.has(key)) groups.set(key, { material: (mats[key[0]] || [])[e.material] || {}, part: p.label, count: 0 });
      groups.get(key).count += e.triangles * 3;
    }
  }
  const order = [...groups.values()].sort((a, b) => (/glass/.test(a.material.cls) ? 1 : 0) - (/glass/.test(b.material.cls) ? 1 : 0));
  let total = 0;
  for (const g of order) { g.first = g.at = total; total += g.count; }
  const indices = new Uint32Array(total), marks = new Map();
  let pos = new Float32Array(3 << 16), nor = new Float32Array(3 << 16), uv = new Float32Array(4 << 16), count = 0, stamp = 0;
  const min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
  for (const part of parts) {
    const m = part.node && tree.get(part.node);
    stamp++;
    for (const e of part.elems) {
      const vd = part.buffers[e.vdata], group = groups.get(keyOf(part, e));
      if (!vd || vd.pos < 0) continue;
      if (!marks.has(vd)) marks.set(vd, { seen: new Uint32Array(vd.vertices), to: new Uint32Array(vd.vertices) });
      const { seen, to } = marks.get(vd), v = vd.view, packed = vd.posTy === MD_SHORT4N;
      for (let i = e.first, end = e.first + e.triangles * 3; i < end; i++) {
        const src = vd.indices[i] + e.base;
        if (seen[src] !== stamp) {
          seen[src] = stamp;
          to[src] = count;
          if ((count + 1) * 3 > pos.length) {
            const a = new Float32Array(pos.length * 2), b = new Float32Array(pos.length * 2), c = new Float32Array(uv.length * 2);
            a.set(pos); b.set(nor); c.set(uv);
            pos = a; nor = b; uv = c;
          }
          mdUv(vd, 0, src, uv, count * 4);
          mdUv(vd, 1, src, uv, count * 4 + 2);
          const o = src * vd.stride + vd.pos;
          let x, y, z;
          if (packed) {
            x = v.getInt16(o, true) / 32767 * scale[0] + offset[0];
            y = v.getInt16(o + 2, true) / 32767 * scale[1] + offset[1];
            z = v.getInt16(o + 4, true) / 32767 * scale[2] + offset[2];
          } else { x = v.getFloat32(o, true); y = v.getFloat32(o + 4, true); z = v.getFloat32(o + 8, true); }
          let nx = 0, ny = 1, nz = 0;
          if (vd.nor >= 0) {  // stored blue, green, red
            const q = src * vd.stride + vd.nor;
            nx = vd.data[q + 2] / 127.5 - 1; ny = vd.data[q + 1] / 127.5 - 1; nz = vd.data[q] / 127.5 - 1;
          }
          if (m) {
            [x, y, z] = [m[0] * x + m[4] * y + m[8] * z + m[12], m[1] * x + m[5] * y + m[9] * z + m[13], m[2] * x + m[6] * y + m[10] * z + m[14]];
            [nx, ny, nz] = [m[0] * nx + m[4] * ny + m[8] * nz, m[1] * nx + m[5] * ny + m[9] * nz, m[2] * nx + m[6] * ny + m[10] * nz];
          }
          const c = count * 3;
          pos[c] = x; pos[c + 1] = y; pos[c + 2] = -z;
          nor[c] = nx; nor[c + 1] = ny; nor[c + 2] = -nz;
          min[0] = Math.min(min[0], x); min[1] = Math.min(min[1], y); min[2] = Math.min(min[2], -z);
          max[0] = Math.max(max[0], x); max[1] = Math.max(max[1], y); max[2] = Math.max(max[2], -z);
          count++;
        }
        indices[group.at++] = to[src];
      }
    }
  }
  return { pos: pos.subarray(0, count * 3), nor: nor.subarray(0, count * 3), uv: uv.subarray(0, count * 4), indices, groups: order, vertices: count, triangles: total / 3, min, max };
}

// what the game's own materials say is not a solid: gun flashes and engine flames, blurred propellers, invisible and
// x-ray shapes, sight glass, decals (which only mean something with their textures)
const MD_NOT_SOLID = /^(aces_weapon_fire|propeller_|dynamic_null|hatching|water_cut|collimator|glass_crack|tracer_head)|decal/;
// on a vehicle, parts the game shows only at times: the drag chute, the stores of every loadout on their pylons, broken
// parts, and the stages of a propeller at speed (prop01 is the propeller at rest, prop02 and prop03 its blurred hubs)
const MD_HIDDEN = /jet_flame|chute|pylon|_pod|damocles|ecm_|_dmg$|prop_side|^prop0[2-9]_/;

// a weapon's part, from its skeleton node: stab_01 and stab_02 are one kind of part, the root or the node named as the model
// its body, and matra_530_cap a cap
function mdLabel(node, name) {
  const n = (node || '').toLowerCase().replace(/[_\d]+$/, '');
  if (!n || n === '@root' || n === name.toLowerCase().replace(/[_\d]+$/, '')) return 'body';
  return /(engine|booster|cap|stab|fin|wing)$/.exec(n)?.[1] || n;
}

// what the server sends: the sizes of the model, its skeleton and its materials, then their bytes. name: a weapon's, whose
// parts can then be left out one by one
async function mdParse(bytes, vehicle, name) {
  const h = new MdReader(bytes), modelSize = h.u32(), treeSize = h.u32(), matSize = h.u32();
  const model = await mdModel(bytes.subarray(12, 12 + modelSize)), treeAt = 12 + modelSize;
  const mats = JSON.parse(new TextDecoder().decode(bytes.subarray(treeAt + treeSize, treeAt + treeSize + matSize)));
  if (vehicle) model.parts = model.parts.filter(p => !MD_HIDDEN.test(p.node || ''));
  for (const p of model.parts) {
    const list = mats[p.skinned ? 'S' : 'R'] || [];
    if (name) p.label = mdLabel(p.node, name);
    p.elems = p.elems.filter(e => !MD_NOT_SOLID.test(list[e.material]?.cls || ''));
  }
  return mdAssemble(model, mdTree(bytes.subarray(treeAt, treeAt + treeSize)), mats);
}

// ------------------------------------------------------------------ the view
const MD = { gl: null, prog: null, blit: null, fbo: null, vao: null, buffers: [], textures: [], raf: 0, token: 0, mesh: null, yaw: 0, pitch: 0, dist: 1, spin: true, last: 0, hiddenParts: new Set() };

const MD_VS = `#version 300 es
in vec3 aPos; in vec3 aNor; in vec4 aUv; uniform mat4 uVp; out vec3 vPos; out vec3 vNor; out vec4 vUv;
void main() { vPos = aPos; vNor = aNor; vUv = aUv; gl_Position = uVp * vec4(aPos, 1.0); }`;
// the game's shaders aren't public: painted areas (the alpha of the colour map) take the camouflage on the second set of
// texture coordinates, modulated by the detail of the colour map; occlusion, on the first set, darkens it; the packed normal map holds the
// normal in alpha and green, smoothness in red, metalness in blue
const MD_FS = `#version 300 es
precision highp float;
in vec3 vPos; in vec3 vNor; in vec4 vUv;
uniform vec3 uEye; uniform sampler2D uColor, uCamo, uNormal, uAo, uMask; uniform ivec4 uHas; uniform int uSplit; uniform float uCut, uAlpha;
out vec4 color;
void main() {
  vec3 n = normalize(vNor), v = normalize(uEye - vPos), l1 = normalize(vec3(0.5, 0.8, 0.35)), l2 = normalize(vec3(-0.6, 0.3, -0.5));
  if (dot(n, v) < 0.0) n = -n;
  vec2 uv = vUv.xy;
  vec4 base = uHas.x == 1 ? texture(uColor, uv) : vec4(0.62, 0.66, 0.70, 1.0);
  if ((uSplit == 1 ? texture(uMask, uv).r : base.a) < uCut) discard;  // tree branches keep their transparency in a texture of its own
  vec3 albedo = base.rgb;
  if (uHas.x == 1 && uHas.y == 1) {
    float mean = max(dot(textureLod(uColor, vec2(0.5), 20.0).rgb, vec3(1.0 / 3.0)), 0.04);
    albedo = mix(base.rgb, min(texture(uCamo, vUv.zw).rgb * dot(base.rgb, vec3(1.0 / 3.0)) / mean, vec3(1.0)), base.a);
  }
  if (uHas.w == 1) albedo *= texture(uAo, uv).r;
  float smooth_ = 0.35, metal = 0.0;
  if (uHas.z == 1) {
    vec4 p = texture(uNormal, uv);
    vec3 dp1 = dFdx(vPos), dp2 = dFdy(vPos), side1 = cross(dp2, n), side2 = cross(n, dp1);
    vec2 du = dFdx(uv), dv = dFdy(uv);
    vec3 t = side1 * du.x + side2 * dv.x, b = side1 * du.y + side2 * dv.y;
    float len = max(max(dot(t, t), dot(b, b)), 1e-12);
    vec2 xy = vec2(p.a, p.g) * 2.0 - 1.0;
    n = normalize(mat3(t * inversesqrt(len), b * inversesqrt(len), n) * vec3(xy, sqrt(max(1.0 - dot(xy, xy), 0.0))));
    smooth_ = p.r; metal = p.b;
  }
  float d = max(dot(n, l1), 0.0) * 0.72 + max(dot(n, l2), 0.0) * 0.22;
  float s = pow(max(dot(n, normalize(l1 + v)), 0.0), mix(8.0, 96.0, smooth_)) * mix(0.08, 0.55, max(smooth_ * 0.6, metal));
  color = vec4(albedo * (0.3 + 0.24 * (0.5 + 0.5 * n.y) + d) + s, uAlpha);
}`;
const MD_BLIT_VS = `#version 300 es
out vec2 vUv;
void main() { vUv = vec2(gl_VertexID & 2, (gl_VertexID << 1) & 2); gl_Position = vec4(vUv * 2.0 - 1.0, 0.0, 1.0); }`;
const MD_BLIT_FS = `#version 300 es
precision highp float;
in vec2 vUv; uniform sampler2D uTex; out vec4 color;
void main() { color = texture(uTex, vUv); }`;

function mdProgram(gl, vs, fs) {
  const stage = (type, src) => {
    const s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    return s;
  };
  const p = gl.createProgram();
  gl.attachShader(p, stage(gl.VERTEX_SHADER, vs));
  gl.attachShader(p, stage(gl.FRAGMENT_SHADER, fs));
  ['aPos', 'aNor', 'aUv'].forEach((name, i) => gl.bindAttribLocation(p, i, name));
  gl.linkProgram(p);
  return p;
}

// the game's block formats, which the graphics card reads as they are
function mdFormat(gl, fourcc) {
  const s3tc = gl.getExtension('WEBGL_compressed_texture_s3tc'), rgtc = gl.getExtension('EXT_texture_compression_rgtc');
  const bptc = gl.getExtension('EXT_texture_compression_bptc');
  return { 'DXT1': s3tc?.COMPRESSED_RGBA_S3TC_DXT1_EXT, 'DXT3': s3tc?.COMPRESSED_RGBA_S3TC_DXT3_EXT, 'DXT5': s3tc?.COMPRESSED_RGBA_S3TC_DXT5_EXT,
    'ATI1': rgtc?.COMPRESSED_RED_RGTC1_EXT, 'ATI2': rgtc?.COMPRESSED_RED_GREEN_RGTC2_EXT, 'BC7 ': bptc?.COMPRESSED_RGBA_BPTC_UNORM_EXT }[fourcc];
}

// a texture of the player's game on the graphics card. Often only the top level is stored, and block formats can't build
// their own smaller levels: the card copies it to a plain texture, which can
// the top level of a stored texture (a header of 32 bytes, then its data), unpacked
function mdTop(bytes) {
  const h = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const flags = h.getUint32(8, true), w = h.getUint16(12, true), ht = h.getUint16(14, true), levels = bytes[16], shift = bytes[23] & 15, bits = h.getUint16(20, true);
  const mem = h.getUint32(24, true), packed = h.getUint32(28, true);
  if (!w || flags & (0x800 | 0x1000 | 0x20000 | 0x200000)) return null;  // cubes, volumes, differences to a base, arrays
  const data = flags >>> 29 === 3 ? lzDecode(bytes.subarray(32, 32 + packed), mem) : bytes.subarray(32);
  const size = l => { const a = Math.max(w >> l, 1), b = Math.max(ht >> l, 1); return shift ? Math.ceil(a / 4) * Math.ceil(b / 4) * 2 ** shift : a * b * bits / 8; };
  const own = flags & 0x6000 ? 1 : Math.max(levels, 1);
  let start = 0;
  if (flags & 0x40000) for (let l = 1; l < own; l++) start += size(l);  // smallest level first
  if (start + size(0) > data.length) return null;
  return { fourcc: String.fromCharCode(...bytes.subarray(4, 8)), d3d: h.getUint32(4, true), w, h: ht, top: data.subarray(start, start + size(0)) };
}

async function mdTexture(ctx, name, { low = false, max = 4096 } = {}) {
  const res = await fetch(`/api/model-texture${low ? '-low' : ''}/${encodeURIComponent(name)}`);
  if (!res.ok) return null;
  const surface = mdTop(new Uint8Array(await res.arrayBuffer())), gl = ctx.gl, format = surface && mdFormat(gl, surface.fourcc);
  if (!format) return null;
  const { w, h: ht, top } = surface, src = gl.createTexture(), out = gl.createTexture();
  gl.activeTexture(gl.TEXTURE0);
  gl.bindTexture(gl.TEXTURE_2D, src);
  gl.compressedTexImage2D(gl.TEXTURE_2D, 0, format, w, ht, 0, top);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAX_LEVEL, 0);
  const shrink = Math.min(1, max / Math.max(w, ht)), ow = Math.max(1, Math.round(w * shrink)), oh = Math.max(1, Math.round(ht * shrink));
  if (shrink < 1) gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.bindTexture(gl.TEXTURE_2D, out);
  gl.texStorage2D(gl.TEXTURE_2D, Math.floor(Math.log2(Math.max(ow, oh))) + 1, gl.RGBA8, ow, oh);
  ctx.blit ||= mdProgram(gl, MD_BLIT_VS, MD_BLIT_FS);
  ctx.fbo ||= gl.createFramebuffer();
  gl.bindFramebuffer(gl.FRAMEBUFFER, ctx.fbo);
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, out, 0);
  gl.viewport(0, 0, ow, oh);
  gl.disable(gl.DEPTH_TEST);
  gl.disable(gl.BLEND);
  gl.bindTexture(gl.TEXTURE_2D, src);
  gl.useProgram(ctx.blit);
  gl.bindVertexArray(null);
  gl.drawArrays(gl.TRIANGLES, 0, 3);
  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  gl.deleteTexture(src);
  gl.bindTexture(gl.TEXTURE_2D, out);
  gl.generateMipmap(gl.TEXTURE_2D);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  const aniso = gl.getExtension('EXT_texture_filter_anisotropic');
  if (aniso) gl.texParameterf(gl.TEXTURE_2D, aniso.TEXTURE_MAX_ANISOTROPY_EXT, 8);
  ctx.textures.push(out);
  return out;
}

// what each material takes from its texture slots, in the place of the viewer's plain grey
function mdSlots(m) {
  const named = (t, test) => (t && test(t) ? t : null);
  return { color: m.t0 || null, camo: /masked/.test(m.cls) ? named(m.t1, t => t.includes('camo')) : null,
    normal: named(m.t2, t => t.endsWith('_n')), ao: named(m.t3, t => t.endsWith('_ao')) };
}

// the model shows at once, and each texture joins it when it arrives
async function mdLoadTextures(mesh, token) {
  const jobs = new Map();
  for (const g of mesh.groups) {
    g.tex = {};
    for (const [slot, name] of Object.entries(mdSlots(g.material))) {
      if (!name) continue;
      if (!jobs.has(name)) jobs.set(name, []);
      jobs.get(name).push([g, slot]);
    }
  }
  const queue = [...jobs], total = queue.length;
  let done = 0;
  const info = () => { $('#mdInfo').textContent = t('model.stats', { n: I18N.num(mesh.triangles) }) + (done < total ? ' · ' + t('model.textures', { n: done, total }) : ''); };
  info();
  const worker = async () => {
    while (queue.length && token === MD.token) {
      const [name, users] = queue.shift();
      try {
        const tex = await mdTexture(MD, name);
        if (tex && token === MD.token) for (const [g, slot] of users) g.tex[slot] = tex;
      } catch (e) { console.warn(name, e); }
      done++;
      if (token === MD.token) info();
    }
  };
  await Promise.all([worker(), worker(), worker(), worker()]);
}

function mdClear() {
  cancelAnimationFrame(MD.raf);
  MD.raf = 0;
  MD.mesh = null;
  const gl = MD.gl;
  if (!gl) return;
  MD.buffers.forEach(b => gl.deleteBuffer(b));
  MD.buffers = [];
  MD.textures.forEach(x => gl.deleteTexture(x));
  MD.textures = [];
  gl.deleteVertexArray(MD.vao);
  gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
}

function mdShow(mesh) {
  const cv = $('#mdCanvas'), gl = MD.gl ||= cv.getContext('webgl2', { antialias: true, alpha: true });
  if (!gl) throw new Error('no WebGL2');
  MD.prog ||= mdProgram(gl, MD_VS, MD_FS);
  MD.vao = gl.createVertexArray();
  gl.bindVertexArray(MD.vao);
  const buffer = (target, data, attr, size) => {
    const b = gl.createBuffer();
    gl.bindBuffer(target, b);
    gl.bufferData(target, data, gl.STATIC_DRAW);
    if (attr >= 0) {
      gl.enableVertexAttribArray(attr);
      gl.vertexAttribPointer(attr, size, gl.FLOAT, false, 0, 0);
    }
    MD.buffers.push(b);
  };
  buffer(gl.ARRAY_BUFFER, mesh.pos, 0, 3);
  buffer(gl.ARRAY_BUFFER, mesh.nor, 1, 3);
  buffer(gl.ARRAY_BUFFER, mesh.uv, 2, 4);
  buffer(gl.ELEMENT_ARRAY_BUFFER, mesh.indices, -1);
  const size = [0, 1, 2].map(i => mesh.max[i] - mesh.min[i]);
  mesh.center = [0, 1, 2].map(i => (mesh.max[i] + mesh.min[i]) / 2);
  mesh.radius = Math.hypot(...size) / 2 || 1;
  Object.assign(MD, { mesh, yaw: 0.7, pitch: 0.3, dist: mesh.radius * 2.2, spin: true, last: performance.now() });
  MD.raf = requestAnimationFrame(mdFrame);
}

function mdMatrix(mesh, aspect) {
  const c = mesh.center, cp = Math.cos(MD.pitch), eye = [c[0] + MD.dist * cp * Math.sin(MD.yaw), c[1] + MD.dist * Math.sin(MD.pitch), c[2] + MD.dist * cp * Math.cos(MD.yaw)];
  const norm = a => { const l = Math.hypot(...a); return a.map(x => x / l); };
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const z = norm(eye.map((x, i) => x - c[i])), x = norm(cross([0, 1, 0], z)), y = cross(z, x);
  const f = 1 / Math.tan(0.35), near = mesh.radius * 0.02, far = mesh.radius * 30, nf = near - far;
  const p = [f / aspect, f, (far + near) / nf, 2 * far * near / nf];
  return { eye, vp: new Float32Array([
    p[0] * x[0], p[1] * y[0], p[2] * z[0], -z[0],
    p[0] * x[1], p[1] * y[1], p[2] * z[1], -z[1],
    p[0] * x[2], p[1] * y[2], p[2] * z[2], -z[2],
    -p[0] * dot(x, eye), -p[1] * dot(y, eye), -p[2] * dot(z, eye) + p[3], dot(z, eye)]) };
}

function mdFrame(now) {
  const { gl, mesh } = MD;
  if (!mesh || !$('#dlgModel').open) return;
  MD.raf = requestAnimationFrame(mdFrame);
  if (MD.spin) MD.yaw += (now - MD.last) * 0.00025;
  MD.last = now;
  const cv = gl.canvas, dpr = window.devicePixelRatio || 1, w = Math.round(cv.clientWidth * dpr), h = Math.round(cv.clientHeight * dpr);
  if (cv.width !== w || cv.height !== h) { cv.width = w; cv.height = h; }
  gl.viewport(0, 0, w, h);
  gl.enable(gl.DEPTH_TEST);
  gl.clearColor(0, 0, 0, 0);
  gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
  gl.useProgram(MD.prog);
  const at = name => gl.getUniformLocation(MD.prog, name);
  const { eye, vp } = mdMatrix(mesh, w / (h || 1));
  gl.uniformMatrix4fv(at('uVp'), false, vp);
  gl.uniform3fv(at('uEye'), eye);
  ['uColor', 'uCamo', 'uNormal', 'uAo'].forEach((name, i) => gl.uniform1i(at(name), i));
  gl.bindVertexArray(MD.vao);
  for (const g of mesh.groups) {
    if (MD.hiddenParts.has(g.part)) continue;
    const tex = g.tex || {}, m = g.material, glass = /glass/.test(m.cls);
    ['color', 'camo', 'normal', 'ao'].forEach((slot, i) => {
      gl.activeTexture(gl.TEXTURE0 + i);
      gl.bindTexture(gl.TEXTURE_2D, tex[slot] || null);
    });
    gl.uniform4i(at('uHas'), tex.color ? 1 : 0, tex.camo ? 1 : 0, tex.normal ? 1 : 0, tex.ao ? 1 : 0);
    gl.uniform1f(at('uCut'), tex.color && (m.atest || /atest/.test(m.cls)) ? (m.atest ?? 128) / 255 : 0);
    gl.uniform1f(at('uAlpha'), glass ? 0.35 : 1);
    if (glass) { gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA); gl.depthMask(false); }
    else { gl.disable(gl.BLEND); gl.depthMask(true); }
    gl.drawElements(gl.TRIANGLES, g.count, gl.UNSIGNED_INT, g.first * 4);
  }
  gl.depthMask(true);
}

// a weapon's positions, when the game has a model for each, and its parts, each of which can be left out
async function mdControls(id, title, mesh, view) {
  const names = await api('model-variants/' + encodeURIComponent(id)).catch(() => []);
  const parts = [...new Set(mesh.groups.map(g => g.part))].filter(Boolean);
  const position = n => t(n.endsWith('_deployed') ? 'model.deployed' : n.endsWith('_container') ? 'model.container' : 'model.stowed');
  const part = p => I18N.tOr('model.part.' + p, p.replace(/_/g, ' '));
  const bar = $('#mdBar');
  bar.innerHTML = `${names.length > 1 ? `<div class="md-group"><span>${esc(t('model.position'))}</span><div class="seg">${names.map(n => `<button class="${n === id.toLowerCase() ? 'active' : ''}" data-mdname="${esc(n)}">${esc(position(n))}</button>`).join('')}</div></div>` : ''}
    ${parts.length > 1 ? `<div class="md-group"><span>${esc(t('model.parts'))}</span>${parts.map(p => `<button class="btn btn-ghost btn-sm${MD.hiddenParts.has(p) ? '' : ' active'}" data-mdpart="${esc(p)}">${esc(part(p))}</button>`).join('')}</div>` : ''}`;
  bar.classList.toggle('hidden', !bar.textContent.trim());
  bar.onclick = ev => {
    const b = ev.target.closest('button');
    if (b?.dataset.mdname) openModel('name', b.dataset.mdname, title, { yaw: MD.yaw, pitch: MD.pitch, spin: MD.spin });
    if (b?.dataset.mdpart) {
      const p = b.dataset.mdpart;
      if (!MD.hiddenParts.delete(p)) MD.hiddenParts.add(p);
      b.classList.toggle('active', !MD.hiddenParts.has(p));
    }
  };
  if (view) Object.assign(MD, view);
}

async function openModel(kind, id, title, view) {
  const token = ++MD.token;
  mdClear();
  if (!view) { MD.hiddenParts.clear(); $('#mdBar').classList.add('hidden'); }
  $('#mdTitle').textContent = title;
  $('#mdInfo').textContent = t('model.loading');
  $('#dlgModel').showModal();
  try {
    const res = await fetch(`/api/model/${kind}/${encodeURIComponent(id)}`);
    if (!res.ok) throw new Error('no model');
    const bytes = new Uint8Array(await res.arrayBuffer());
    await new Promise(requestAnimationFrame);  // the message shows before the page gets busy
    const mesh = await mdParse(bytes, kind === 'vehicle', kind === 'name' ? id : null);
    if (token !== MD.token) return;
    if (!mesh.triangles) throw new Error('an empty model');
    mdShow(mesh);
    if (kind === 'name') mdControls(id, title, mesh, view);
    await mdLoadTextures(mesh, token);
  } catch (e) {
    console.warn(e);
    if (token === MD.token) $('#mdInfo').textContent = t('model.none');
  }
}

if (typeof document !== 'undefined') {
  const cv = $('#mdCanvas');
  let drag = null;
  cv.addEventListener('pointerdown', ev => { cv.setPointerCapture(ev.pointerId); drag = [ev.clientX, ev.clientY]; MD.spin = false; });
  cv.addEventListener('pointermove', ev => {
    if (!drag) return;
    MD.yaw -= (ev.clientX - drag[0]) * 0.008;
    MD.pitch = Math.max(-1.5, Math.min(1.5, MD.pitch + (ev.clientY - drag[1]) * 0.008));
    drag = [ev.clientX, ev.clientY];
  });
  cv.addEventListener('pointerup', () => { drag = null; });
  cv.addEventListener('wheel', ev => {
    ev.preventDefault();
    if (MD.mesh) MD.dist = Math.max(MD.mesh.radius * 0.5, Math.min(MD.mesh.radius * 8, MD.dist * (ev.deltaY > 0 ? 1.12 : 1 / 1.12)));
  }, { passive: false });
  $('#dlgModel').addEventListener('close', () => { MD.token++; mdClear(); });
}
if (typeof module !== 'undefined') module.exports = { mdParse };
