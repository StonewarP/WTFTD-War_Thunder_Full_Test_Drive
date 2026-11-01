/* WTFTD — the scenario editor's map in 3D: the level's relief and its placed objects, read from the player's own game files,
   and the units as their real models. The editor's own markers are drawn on top: edToScreen and edToWorld go through this
   camera, so selecting, placing, moving and routes work as on the flat map. Nothing is stored. */
'use strict';

const M3 = { on: false, gl: null, blit: null, fbo: null, textures: [], yaw: 0.5, pitch: 0.7, fov: 0.7, raf: 0, token: 0, orbit: null,
  ground: null, outer: null, land: null, groundProg: null, objProg: null, leafProg: null, objects: [], leaves: [], units: new Map(), maps: [], baked: false, vp: null, eye: null, cam: null };
const M3_NOT_OBJECT = /baked_impostor|facing_leaves/;  // billboards only the game's shaders can draw, and leaves (m3Leaves)
const M3_LEAF_TRIANGLES = [2500000, 8000000];  // what leaves may cost, one kind of tree and the whole level: past that, not every tree gets them
const M3_OBJECT_TEX = 512, M3_LOD_TRIANGLES = 400000;  // the size of an object's textures, and what one kind of object may cost
const M3_IDENTITY = new Float32Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]);
const M3_PITCH = [1.54, 0.08];  // the camera, from just above the flat map to just above the ground

const M3_GROUND_VS = `#version 300 es
in vec3 aPos; in vec3 aNor; uniform mat4 uVp; out vec3 vPos; out vec3 vNor;
void main() { vPos = aPos; vNor = aNor; gl_Position = uVp * vec4(aPos, 1.0); }`;
const M3_GROUND_FS = `#version 300 es
precision highp float;
in vec3 vPos; in vec3 vNor; uniform sampler2D uMap0, uMap1; uniform vec4 uRect0, uRect1, uFlat, uClip; uniform ivec2 uHas; uniform vec2 uUp; out vec4 color;
vec2 at(vec4 r, float up) {
  vec2 p = (vPos.xz - r.xy) / (r.zw - r.xy);
  return vec2(p.x, up > 0.5 ? 1.0 - p.y : p.y);
}
void main() {
  if (uFlat.a > 0.0) { color = uFlat; return; }
  if (uClip.z > uClip.x && vPos.x > uClip.x && vPos.x < uClip.z && vPos.z > uClip.y && vPos.z < uClip.w) discard;  // the finer ground is there
  vec3 base = vec3(0.42, 0.45, 0.34);
  vec2 a = at(uRect0, uUp.x), b = at(uRect1, uUp.y);
  if (uHas.x == 1 && all(greaterThanEqual(a, vec2(0.0))) && all(lessThanEqual(a, vec2(1.0)))) { vec4 c = texture(uMap0, a); base = mix(base, c.rgb / max(c.a, 0.01), step(0.01, c.a)); }
  if (uHas.y == 1 && all(greaterThanEqual(b, vec2(0.0))) && all(lessThanEqual(b, vec2(1.0)))) { vec4 c = texture(uMap1, b); base = mix(base, c.rgb / max(c.a, 0.01), step(0.01, c.a)); }
  float d = max(dot(normalize(vNor), normalize(vec3(0.5, 0.8, 0.35))), 0.0);
  color = vec4(base * (0.5 + 0.6 * d), 1.0);
}`;
// objects and units: an instance's matrix comes in three rows, constant for a unit
const M3_OBJ_VS = `#version 300 es
in vec3 aPos; in vec3 aNor; in vec4 aUv; in vec4 iRow0, iRow1, iRow2; uniform mat4 uVp, uParent; out vec3 vPos; out vec3 vNor; out vec4 vUv;
void main() {
  vec4 p = vec4(aPos, 1.0);
  vPos = (uParent * vec4(dot(iRow0, p), dot(iRow1, p), dot(iRow2, p), 1.0)).xyz;
  vNor = mat3(uParent) * vec3(dot(iRow0.xyz, aNor), dot(iRow1.xyz, aNor), dot(iRow2.xyz, aNor));
  vUv = aUv;
  gl_Position = uVp * vec4(vPos, 1.0);
}`;

// leaves: cards around a centre, their corners given in the camera's frame, so that they always face it (the game's own way)
const M3_LEAF_VS = `#version 300 es
layout(location = 0) in vec4 aCentre; layout(location = 1) in vec4 aNor; layout(location = 2) in vec2 aUv; layout(location = 6) in vec4 aCorner;
layout(location = 3) in vec4 iRow0; layout(location = 4) in vec4 iRow1; layout(location = 5) in vec4 iRow2;
uniform mat4 uVp; uniform vec3 uRight, uUp, uToward; out vec3 vPos; out vec3 vNor; out vec4 vUv;
void main() {
  vec4 p = vec4(aCentre.xyz, 1.0);
  vec3 c = vec3(dot(iRow0, p), dot(iRow1, p), dot(iRow2, p));
  vPos = c + (aCorner.x * uRight + aCorner.y * uUp + aCorner.z * uToward) * length(iRow1.xyz);
  vec3 n = aNor.bgr * 2.0 - 1.0;
  vNor = vec3(dot(iRow0.xyz, n), dot(iRow1.xyz, n), dot(iRow2.xyz, n));
  vUv = vec4(aUv / 4096.0, 0.0, 0.0);
  gl_Position = uVp * vec4(vPos, 1.0);
}`;
// the zones: seen through, stronger at their foot
const M3_ZONE_VS = `#version 300 es
in vec3 aPos; uniform mat4 uVp, uTm; out float vUp;
void main() { vUp = aPos.y * 0.5 + 0.5; gl_Position = uVp * uTm * vec4(aPos, 1.0); }`;
const M3_ZONE_FS = `#version 300 es
precision highp float;
in float vUp; uniform vec4 uTint; uniform float uFade; out vec4 color;
void main() { color = vec4(uTint.rgb, uTint.a * mix(1.0, uFade, vUp)); }`;
// the real ground: for one cell of the level's grid, its land classes' colour maps blended by the cell's weights, as a picture
const M3_BAKE_VS = `#version 300 es
uniform vec4 uCell, uRect; out vec2 vCell; out vec2 vWorld;
void main() {
  vCell = vec2(gl_VertexID & 1, (gl_VertexID >> 1) & 1);
  vWorld = mix(uCell.xy, uCell.zw, vCell);
  gl_Position = vec4((vWorld - uRect.xy) / (uRect.zw - uRect.xy) * 2.0 - 1.0, 0.0, 1.0);
}`;
const M3_BAKE_FS = `#version 300 es
precision highp float;
in vec2 vCell; in vec2 vWorld;
uniform sampler2D uW0, uW1, uC0, uC1, uC2, uC3, uC4, uC5, uC6;
uniform vec4 uTile[7], uPage0, uPage1; uniform int uCount, uPacked; uniform ivec4 uHasW;
out vec4 color;
#define ADD(i, t) if (w[i] > 0.0 && uTile[i].x > 0.0) { \
  vec3 c = texture(t, vec2((vWorld.x - uTile[i].z) / uTile[i].x, -(vWorld.y - uTile[i].w) / uTile[i].y)).rgb; \
  acc += w[i] * pow(c, vec3(2.2)); total += w[i]; }
void main() {
  float w[7];
  for (int i = 0; i < 7; i++) w[i] = 0.0;
  int n = min(uCount, 7);
  if (n <= 1) w[0] = 1.0;
  else if (uPacked == 1) {  // pages of an atlas: the last class gets what the others leave
    vec3 a = texture(uW0, uPage0.xy + vCell * uPage0.zw).rgb;
    w[0] = a.r; w[1] = a.g; w[2] = a.b;
    if (n > 4) { vec3 b = texture(uW1, uPage1.xy + vCell * uPage1.zw).rgb; w[3] = b.r; w[4] = b.g; w[5] = b.b; }
    float sum = 0.0;
    for (int i = n - 1; i < 7; i++) w[i] = 0.0;
    for (int i = 0; i < n - 1; i++) sum += w[i];
    w[n - 1] = clamp(1.0 - sum, 0.0, 1.0);
  } else {  // two textures for a cell: the even class just below the count gets what the others leave
    vec4 a = uHasW.x == 1 ? texture(uW0, vCell) : vec4(0.0);
    vec4 b = uHasW.y == 1 ? texture(uW1, vCell) : vec4(0.0);
    if (uHasW.z == 1) a = a.gbar;  // stored as ARGB
    if (uHasW.w == 1) b = b.gbar;
    w[0] = a.r; w[1] = a.g; w[2] = a.b; w[3] = a.a; w[4] = b.r; w[5] = b.g;
    for (int i = n; i < 7; i++) w[i] = 0.0;
    int left = (n - 1) & ~1;
    float sum = 0.0;
    w[left] = 0.0;
    for (int i = 0; i < n; i++) sum += w[i];
    w[left] = clamp(1.0 - sum, 0.0, 1.0);
  }
  vec3 acc = vec3(0.0);
  float total = 0.0;
  ADD(0, uC0) ADD(1, uC1) ADD(2, uC2) ADD(3, uC3) ADD(4, uC4) ADD(5, uC5) ADD(6, uC6)
  color = total > 0.0 ? vec4(pow(acc / total, vec3(1.0 / 2.2)), 1.0) : vec4(0.0);
}`;

function m3Program(gl, vs, fs) {
  const p = gl.createProgram();
  for (const [type, src] of [[gl.VERTEX_SHADER, vs], [gl.FRAGMENT_SHADER, fs]]) {
    const s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    gl.attachShader(p, s);
  }
  ['aPos', 'aNor', 'aUv', 'iRow0', 'iRow1', 'iRow2'].forEach((name, i) => gl.bindAttribLocation(p, i, name));
  gl.linkProgram(p);
  return p;
}

// ------------------------------------------------------------------ camera
function m3Camera() {
  const c = ED.canvas, s = Math.tan(M3.fov / 2), dist = c.height / 2 / s / ED.view.scale;
  const t = [ED.view.cx, edGround(ED.view.cx, ED.view.cz) ?? 0, -ED.view.cz], cp = Math.cos(M3.pitch);
  const eye = [t[0] + dist * cp * Math.sin(M3.yaw), t[1] + dist * Math.sin(M3.pitch), t[2] + dist * cp * Math.cos(M3.yaw)];
  const norm = a => { const l = Math.hypot(...a); return a.map(x => x / l); };
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const z = norm(eye.map((v, i) => v - t[i])), x = norm(cross([0, 1, 0], z)), y = cross(z, x);
  const aspect = c.width / c.height, f = 1 / s, near = Math.max(dist / 60, 0.5), far = Math.max(dist * 40, 200000), nf = near - far;
  const a = (far + near) / nf, b = 2 * far * near / nf, px = f / aspect;
  // the game's z runs the other way: the third column turns it round
  M3.vp = new Float32Array([
    px * x[0], f * y[0], a * z[0], -z[0],
    px * x[1], f * y[1], a * z[1], -z[1],
    -px * x[2], -f * y[2], -a * z[2], z[2],
    -px * dot(x, eye), -f * dot(y, eye), -a * dot(z, eye) + b, dot(z, eye)]);
  M3.eye = [eye[0], eye[1], -eye[2]];
  M3.cam = { eye, x, y, z, s, aspect };
}

// where a point of the world falls on the editor's canvas
function m3ToScreen(x, z, y) {
  const v = M3.vp, h = y ?? edGround(x, z) ?? 0, c = ED.canvas;
  const cw = v[3] * x + v[7] * h + v[11] * z + v[15];
  if (cw <= 0.01) return [-1e6, -1e6];
  return [(v[0] * x + v[4] * h + v[8] * z + v[12]) / cw * c.width / 2 + c.width / 2, c.height / 2 - (v[1] * x + v[5] * h + v[9] * z + v[13]) / cw * c.height / 2];
}

function m3Ray(sx, sy) {
  const { x, y, z, s, aspect } = M3.cam, c = ED.canvas;
  const nx = (sx / c.width * 2 - 1) * s * aspect, ny = (1 - sy / c.height * 2) * s;
  return [0, 1, 2].map(i => x[i] * nx + y[i] * ny - z[i]);
}

// where the ray through a point of the canvas meets a height: what a unit in the air is turned towards
function m3AtHeight(sx, sy, h) {
  const { eye } = M3.cam, d = m3Ray(sx, sy), t = (h - eye[1]) / d[1];
  return t > 0 ? [eye[0] + d[0] * t, -(eye[2] + d[2] * t)] : null;
}

// the ground under a point of the canvas: along the ray, then finer around where it goes below
function m3ToWorld(sx, sy) {
  const { eye } = M3.cam, d = m3Ray(sx, sy);
  const under = t => { const p = eye[1] + d[1] * t; return p <= (edGround(eye[0] + d[0] * t, -(eye[2] + d[2] * t)) ?? 0); };
  let hit = null, step = Math.hypot(...eye.map((v, i) => v - [ED.view.cx, 0, -ED.view.cz][i])) / 24, t = 0;
  for (let i = 0; i < 80 && hit == null; i++) {
    if (under(t + step)) hit = t; else { t += step; step *= 1.08; }
  }
  if (hit == null) return [ED.view.cx, ED.view.cz];
  let a = hit, b = hit + step;
  for (let i = 0; i < 14; i++) { const m = (a + b) / 2; if (under(m)) b = m; else a = m; }
  return [eye[0] + d[0] * a, -(eye[2] + d[2] * a)];
}

// left drag on the map: the ground follows the pointer, whichever way the camera looks
function m3Pan(drag, sx, sy) {
  const k = 1 / ED.view.scale, dx = (sx - drag.sx) * k, dy = (sy - drag.sy) * k / Math.max(Math.sin(M3.pitch), 0.35);
  const c = Math.cos(M3.yaw), s = Math.sin(M3.yaw);
  ED.view.cx = drag.cx - dx * c - dy * s;
  ED.view.cz = drag.cz - dx * s + dy * c;
}

// ------------------------------------------------------------------ the ground
function m3GroundMesh(T, old) {
  const gl = M3.gl;
  if (old) { gl.deleteVertexArray(old.vao); old.buffers.forEach(b => gl.deleteBuffer(b)); }
  const v = gl.createVertexArray(), buffers = [];
  gl.bindVertexArray(v);
  const put = (target, data, attr) => {
    const b = gl.createBuffer();
    gl.bindBuffer(target, b);
    gl.bufferData(target, data, gl.STATIC_DRAW);
    if (attr >= 0) { gl.enableVertexAttribArray(attr); gl.vertexAttribPointer(attr, 3, gl.FLOAT, false, 0, 0); }
    buffers.push(b);
  };
  let w = 2, h = 2, pos, nor, count;
  if (T) {
    const step = Math.max(1, Math.ceil(Math.max(T.w, T.h) / 1024)), height = (i, j) => T.hmin + T.grid[j * T.w + i] * T.hscale / 65535;
    w = Math.floor((T.w - 1) / step) + 1; h = Math.floor((T.h - 1) / step) + 1;
    pos = new Float32Array(w * h * 3); nor = new Float32Array(w * h * 3);
    for (let j = 0, o = 0; j < h; j++) {
      for (let i = 0; i < w; i++, o += 3) {
        const a = i * step, b = j * step, l = Math.max(a - step, 0), r = Math.min(a + step, T.w - 1), d = Math.max(b - step, 0), u = Math.min(b + step, T.h - 1);
        pos[o] = T.ofs[0] + a * T.cell; pos[o + 1] = height(a, b); pos[o + 2] = T.ofs[1] + b * T.cell;
        const nx = (height(l, b) - height(r, b)) / ((r - l) * T.cell), nz = (height(a, d) - height(a, u)) / ((u - d) * T.cell), n = 1 / Math.hypot(nx, 1, nz);
        nor[o] = nx * n; nor[o + 1] = n; nor[o + 2] = nz * n;
      }
    }
  } else {  // no relief in this level's file: its map, flat
    const all = ED.layers.length ? ED.layers : [{ min: [-8192, -8192], max: [8192, 8192] }], lo = all[0].min, hi = all[0].max;
    pos = new Float32Array([lo[0], 0, lo[1], hi[0], 0, lo[1], lo[0], 0, hi[1], hi[0], 0, hi[1]]);
    nor = new Float32Array([0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0]);
  }
  const idx = new Uint32Array((w - 1) * (h - 1) * 6);
  count = 0;
  for (let j = 0; j < h - 1; j++) {
    for (let i = 0; i < w - 1; i++) {
      const a = j * w + i, b = a + 1, c = a + w, d = c + 1;
      idx[count++] = a; idx[count++] = c; idx[count++] = b; idx[count++] = b; idx[count++] = c; idx[count++] = d;
    }
  }
  put(gl.ARRAY_BUFFER, pos, 0);
  put(gl.ARRAY_BUFFER, nor, 1);
  put(gl.ELEMENT_ARRAY_BUFFER, idx, -1);
  return { vao: v, buffers, count, terrain: T };
}

function m3MapTextures() {
  const gl = M3.gl;
  for (const l of M3.baked ? [] : ED.layers) {
    if (!l.img || M3.maps.some(m => m.layer === l)) continue;
    const tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, l.img);
    gl.generateMipmap(gl.TEXTURE_2D);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    M3.maps.push({ layer: l, tex });
  }
}

// ------------------------------------------------------------------ the level's real ground
// a weight texture of the level on the graphics card; argb: 4-bit channels stored as ARGB, which the shader turns round
function m3WeightTexture(ddsx) {
  const s = mdTop(ddsx), gl = M3.gl;
  if (!s) return null;
  const tex = gl.createTexture(), format = mdFormat(gl, s.fourcc);
  gl.bindTexture(gl.TEXTURE_2D, tex);
  if (format) gl.compressedTexImage2D(gl.TEXTURE_2D, 0, format, s.w, s.h, 0, s.top);
  else if (s.d3d === 26) gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA4, s.w, s.h, 0, gl.RGBA, gl.UNSIGNED_SHORT_4_4_4_4, new Uint16Array(s.top.slice().buffer));
  else { gl.deleteTexture(tex); return null; }
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAX_LEVEL, 0);
  return { tex, argb: !format, w: s.w, h: s.h };
}

// the cells of the level's grid: which land classes each one blends, and with what weights
function m3Cells(lmap, info) {
  const { w, h, tex, elem, at } = info.weights, n = w * h, r = new MdReader(lmap, at), cells = [];
  if (tex === 0) {
    r.skip(n * 4 + 7 + 8);
    const perRow = r.u32();
    r.skip(4);
    const records = Array.from({ length: n * 3 }, () => r.u32()), atlas = m3WeightTexture(r.take(r.u32()));
    if (!atlas) return null;
    const page = atlas.w / perRow, border = (page - elem) / 2, uv = p => [((p % perRow) * page + border) / atlas.w, (Math.floor(p / perRow) * page + border) / atlas.h, elem / atlas.w, elem / atlas.h];
    for (let i = 0; i < n; i++) {
      const a = records[i * 3], count = ((a >>> 28) & 7) + 1;
      const ids = [...new Uint8Array(new Uint32Array([records[i * 3 + 1], records[i * 3 + 2]]).buffer)].slice(0, Math.min(count, 7));
      cells.push({ ids, packed: true, w0: atlas, w1: atlas, page0: uv(a & 0x3FFF), page1: uv((a >>> 14) & 0x3FFF) });
    }
    return cells;
  }
  return Array.from({ length: n }, () => {
    const c = new MdReader(lmap, 36 + r.u32()), ids = [...lmap.subarray(c.p, c.p + 7)].filter(x => x !== 0xFF);
    c.skip(7);
    const len = c.u32(), second = c.u32(), body = c.take(len), a = body.subarray(0, second || len), b = second ? body.subarray(second) : body.subarray(0, 0);
    return { ids, packed: false, a, b };
  });
}

// the ground of a rectangle of the world as a picture
function m3Bake(info, cells, maps, rect, size, cellM) {
  const gl = M3.gl, p = M3.bakeProg ||= m3Program(gl, M3_BAKE_VS, M3_BAKE_FS), at = name => gl.getUniformLocation(p, name);
  const out = gl.createTexture();
  gl.activeTexture(gl.TEXTURE0);
  gl.bindTexture(gl.TEXTURE_2D, out);
  gl.texStorage2D(gl.TEXTURE_2D, Math.floor(Math.log2(size)) + 1, gl.RGBA8, size, size);
  M3.bakeFbo ||= gl.createFramebuffer();
  gl.bindFramebuffer(gl.FRAMEBUFFER, M3.bakeFbo);
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, out, 0);
  gl.viewport(0, 0, size, size);
  gl.disable(gl.DEPTH_TEST);
  gl.disable(gl.BLEND);
  gl.useProgram(p);
  gl.bindVertexArray(null);
  gl.uniform4f(at('uRect'), rect[0], rect[1], rect[2], rect[3]);
  gl.uniform1i(at('uW0'), 0);
  gl.uniform1i(at('uW1'), 1);
  for (let i = 0; i < 7; i++) gl.uniform1i(at(`uC${i}`), 2 + i);
  const ox = info.origin[0] * info.land, oz = info.origin[1] * info.land, { w, h } = info.weights;
  for (let j = 0; j < h; j++) {
    for (let i = 0; i < w; i++) {
      const x0 = ox + i * cellM, z0 = oz + j * cellM, c = cells[j * w + i];
      if (!c || x0 + cellM <= rect[0] || x0 >= rect[2] || z0 + cellM <= rect[1] || z0 >= rect[3]) continue;
      if (!c.packed && c.w0 === undefined) { c.w0 = c.a.length > 32 ? m3WeightTexture(c.a) : null; c.w1 = c.b.length > 32 ? m3WeightTexture(c.b) : null; }
      gl.uniform4f(at('uCell'), x0, z0, x0 + cellM, z0 + cellM);
      gl.uniform1i(at('uCount'), c.ids.length);
      gl.uniform1i(at('uPacked'), c.packed ? 1 : 0);
      gl.uniform4i(at('uHasW'), c.w0 ? 1 : 0, c.w1 ? 1 : 0, c.w0?.argb ? 1 : 0, c.w1?.argb ? 1 : 0);
      if (c.packed) { gl.uniform4fv(at('uPage0'), c.page0); gl.uniform4fv(at('uPage1'), c.page1); }
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, c.w0?.tex || null);
      gl.activeTexture(gl.TEXTURE1);
      gl.bindTexture(gl.TEXTURE_2D, c.w1?.tex || null);
      const tiles = new Float32Array(28);
      for (let k = 0; k < 7; k++) {
        const m = maps[c.ids[k]], l = info.classes[c.ids[k]];
        gl.activeTexture(gl.TEXTURE2 + k);
        gl.bindTexture(gl.TEXTURE_2D, m || null);
        if (m && k < c.ids.length) tiles.set([l.size[0], l.size[1], ox + l.offset[0], oz + l.offset[1]], k * 4);
      }
      gl.uniform4fv(at('uTile'), tiles);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    }
  }
  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  gl.activeTexture(gl.TEXTURE0);
  gl.bindTexture(gl.TEXTURE_2D, out);
  gl.generateMipmap(gl.TEXTURE_2D);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  return out;
}

async function m3LoadGround(level, info, token) {
  const res = await fetch(`/api/level-land/${encodeURIComponent(level)}`);
  if (!res.ok || !info.classes?.length) return;
  const lmap = new Uint8Array(await res.arrayBuffer()), gl = M3.gl, cells = m3Cells(lmap, info);
  if (!cells) return;
  M3.blit ||= mdProgram(gl, MD_BLIT_VS, MD_BLIT_FS);
  M3.fbo ||= gl.createFramebuffer();
  const scratch = { gl, blit: M3.blit, fbo: M3.fbo, textures: [] };
  const maps = await Promise.all(info.classes.map(c => (c.texture ? mdTexture(scratch, c.texture, { max: 2048 }).catch(() => null) : null)));
  if (token !== M3.token) return;
  const cellM = info.land * info.cells[0] / info.weights.w, x0 = info.origin[0] * info.land, z0 = info.origin[1] * info.land;
  const whole = [x0, z0, x0 + info.cells[0] * info.land, z0 + info.cells[1] * info.land], layer = (rect, tex) => ({ layer: { min: rect.slice(0, 2), max: rect.slice(2), zUp: false }, tex });
  const baked = [layer(whole, m3Bake(info, cells, maps, whole, 4096, cellM))];
  const T = ED.terrain;
  if (T && !T.coarse) {
    const fine = [T.ofs[0], T.ofs[1], T.ofs[0] + T.w * T.cell, T.ofs[1] + T.h * T.cell];
    baked.push(layer(fine, m3Bake(info, cells, maps, fine, 4096, cellM)));
  }
  for (const c of cells) for (const t of [c.w0, c.w1]) if (t && !c.packed) gl.deleteTexture(t.tex);
  scratch.textures.forEach(x => gl.deleteTexture(x));
  M3.maps.forEach(m => gl.deleteTexture(m.tex));
  Object.assign(M3, { maps: baked, baked: true });
  m3Redraw();
}

// ------------------------------------------------------------------ the relief of the whole level
// the ground as triangles: two ways the game stores them
function m3LtDump(raw) {
  const r = new MdReader(raw);
  r.skip(10);
  const cx = r.u32(), cy = r.u32();
  r.skip(40);
  const n = r.u32(), cells = [];
  if (n !== cx * cy) throw new Error('land: cells');
  for (let i = 0; i < n; i++) {
    const c = new MdReader(raw, r.p);
    const ofs = [c.f32(), c.f32(), c.f32(), c.f32()], scale = [c.f32(), c.f32(), c.f32(), c.f32()];
    c.skip(16);
    cells.push({ ofs, scale, f0: c.u32(), v0: c.u32() });
    r.skip(64);
  }
  for (let i = 0; i < 2; i++) r.skip(r.u32() * 4);
  const faceN = r.u32(), faces = r.take(faceN * 2), vertN = r.u32(), verts = r.take(vertN * 8);
  const fv = new DataView(faces.buffer, faces.byteOffset, faces.byteLength), vv = new DataView(verts.buffer, verts.byteOffset, verts.byteLength);
  const pos = new Float32Array(vertN * 3), idx = new Uint32Array(faceN);
  let p = 0, q = 0;
  cells.forEach((c, i) => {
    const f1 = cells[i + 1]?.f0 ?? faceN, v1 = cells[i + 1]?.v0 ?? vertN, nv = v1 - c.v0;
    if (!nv || f1 - c.f0 < 3) return;
    const base = p / 3;
    for (let v = c.v0; v < v1; v++) for (let k = 0; k < 3; k++) pos[p++] = vv.getUint16((v * 4 + k) * 2, true) * c.scale[k] + c.ofs[k];
    for (let f = c.f0; f < f1; f++) idx[q++] = base + fv.getUint16(f * 2, true);
  });
  return { pos: pos.subarray(0, p), idx: idx.subarray(0, q) };
}

function m3Lts4(raw) {
  const r = new MdReader(raw);
  r.skip(8);
  const cx = r.u32(), cy = r.u32();
  r.skip(40);
  const chunks = [];
  let verts = 0, tris = 0;
  for (let ci = 0; ci < cx * cy; ci++) {
    if (!r.u32()) continue;
    const scale = [r.f32(), r.f32(), r.f32(), r.f32()], ofs = [r.f32(), r.f32(), r.f32(), r.f32()];
    r.skip(4);
    const version = r.u16();
    r.skip(2);
    const treeBytes = r.u32(), count = r.u32();
    r.skip(24);
    const edges = version >= 2 && r.u32() & 1, at = r.p;
    r.skip(count * 8);
    const list = [];
    let done = 0, leaves = 0;
    const sx = v => (v << 19) >> 19;
    while (done < treeBytes) {
      const cc = r.b[r.p++];
      if (cc !== 0 && cc < 0xFD) { done += 16; continue; }
      const w0 = r.u32(), w1 = r.u32();
      let w2 = cc === 0xFD ? 1 << 29 : 0, w3 = 0;
      if (cc === 0 || cc === 0xFF) { w2 = r.u32(); w3 = r.u32(); }
      done += 28;
      leaves++;
      if (cc === 0xFF) continue;
      const apex = w1 & 0xFFFFFF, o1 = sx(w0), o2 = sx(w0 >>> 13), o3 = sx(((w0 >>> 26) & 31) | (w1 >>> 24) << 5), b1 = sx(w2 >>> 16), b2 = sx(w3), b3 = sx(w3 >>> 13);
      const quad = (a, p1, p2, p3, flip) => {
        list.push(a, a + p1, a + p2);
        if (p3 !== p2) { if (flip) list.push(a + p2, a + p1, a + p3); else list.push(a + p1, a + p2, a + p3); }
      };
      quad(apex, o1, o2, o3, !!(w2 & (1 << 29)));
      if (b1 !== b2) quad(apex + (w2 & 0xFFFF), b1, b2, b3, !!(w2 & (1 << 30)));
    }
    if (edges) r.skip(leaves * 2);
    chunks.push({ at, count, scale, ofs, list });
    verts += count;
    tris += list.length;
  }
  const pos = new Float32Array(verts * 3), idx = new Uint32Array(tris);
  let p = 0, q = 0;
  for (const c of chunks) {
    const base = p / 3, v = new DataView(raw.buffer, raw.byteOffset + c.at, c.count * 8);
    for (let i = 0; i < c.count; i++) {
      const lo = v.getUint32(i * 8, true), hi = v.getUint32(i * 8 + 4, true);
      const qv = [lo & 0x1FFFFF, ((lo >>> 21) | (hi << 11)) & 0x1FFFFF, (hi >>> 10) & 0x1FFFFF];
      for (let k = 0; k < 3; k++) pos[p++] = (qv[k] / 32 - c.ofs[k]) / c.scale[k];
    }
    for (const i of c.list) idx[q++] = base + i;
  }
  return { pos: pos.subarray(0, p), idx: idx.subarray(0, q) };
}

// the triangles as a grid of heights, like the editor's own relief. They leave a hole where the level's heightmap (under) takes
// over: its heights run through it, or the ground would drop away along its edge and leave a gap
function m3Grid({ pos, idx }, info, under) {
  const x0 = info.origin[0] * info.land, z0 = info.origin[1] * info.land, sx = info.cells[0] * info.land, sz = info.cells[1] * info.land;
  const cell = Math.max(info.grid, Math.max(sx, sz) / 2048), w = Math.ceil(sx / cell) + 1, h = Math.ceil(sz / cell) + 1, heights = new Float32Array(w * h).fill(NaN);
  for (let t = 0; t + 2 < idx.length; t += 3) {
    const a = idx[t] * 3, b = idx[t + 1] * 3, c = idx[t + 2] * 3;
    const ax = (pos[a] - x0) / cell, az = (pos[a + 2] - z0) / cell, bx = (pos[b] - x0) / cell, bz = (pos[b + 2] - z0) / cell, cx = (pos[c] - x0) / cell, cz = (pos[c + 2] - z0) / cell;
    const area = (bx - ax) * (cz - az) - (cx - ax) * (bz - az);
    if (!area) continue;
    const i0 = Math.max(0, Math.ceil(Math.min(ax, bx, cx))), i1 = Math.min(w - 1, Math.floor(Math.max(ax, bx, cx)));
    const j0 = Math.max(0, Math.ceil(Math.min(az, bz, cz))), j1 = Math.min(h - 1, Math.floor(Math.max(az, bz, cz)));
    for (let j = j0; j <= j1; j++) {
      for (let i = i0; i <= i1; i++) {
        const u = ((bx - i) * (cz - j) - (cx - i) * (bz - j)) / area, v = ((cx - i) * (az - j) - (ax - i) * (cz - j)) / area, s = 1 - u - v;
        if (u < -1e-4 || v < -1e-4 || s < -1e-4) continue;
        const y = u * pos[a + 1] + v * pos[b + 1] + s * pos[c + 1], at = j * w + i;
        if (!(heights[at] >= y)) heights[at] = y;
      }
    }
  }
  if (heights.reduce((n, v) => n + !Number.isNaN(v), 0) < w * h / 100) return null;  // the level's relief is all in its heightmap
  let hmin = Infinity, hmax = -Infinity;
  for (let j = 0, at = 0; j < h; j++) {
    for (let i = 0; i < w; i++, at++) {
      if (under && Number.isNaN(heights[at])) {
        const a = Math.round((x0 + i * cell - under.ofs[0]) / under.cell), b = Math.round((z0 + j * cell - under.ofs[1]) / under.cell);
        heights[at] = under.hmin + under.grid[Math.max(0, Math.min(under.h - 1, b)) * under.w + Math.max(0, Math.min(under.w - 1, a))] * under.hscale / 65535;
      }
      if (heights[at] < hmin) hmin = heights[at];
      if (heights[at] > hmax) hmax = heights[at];
    }
  }
  const scale = Math.max(hmax - hmin, 1), grid = new Uint16Array(w * h);
  for (let i = 0; i < grid.length; i++) grid[i] = Number.isNaN(heights[i]) ? 0 : (heights[i] - hmin) / scale * 65535;
  return { ofs: [x0, z0], cell, w, h, hmin, hscale: scale, grid, coarse: true };
}

async function m3LoadLand(level, info, token) {
  const res = await fetch(`/api/level-tracer/${encodeURIComponent(level)}`);
  if (!res.ok) return;
  const bytes = new Uint8Array(await res.arrayBuffer()), size = new MdReader(bytes).u32();
  const raw = size ? lzDecode(bytes.subarray(4), size) : bytes.subarray(4);
  const mesh = String.fromCharCode(...raw.subarray(0, 4)) === 'LTS4' ? m3Lts4(raw) : m3LtDump(raw), T = m3Grid(mesh, info, ED.terrain);
  if (!T || token !== M3.token) return;
  M3.land = T;
  if (!ED.terrain) ED.terrain = T;  // no finer relief in this level: heights in the editor come from this one
  edDraw();
}

// ------------------------------------------------------------------ the level's placed objects
function m3Pointer(r) { const v = r.v.getInt32(r.p, true); r.p += 8; return v >= 0 ? v : null; }

// a layer's table of objects: its cells, and in each one how many objects of each kind
function m3Layer(dump) {
  const at = p => new MdReader(dump, p), r = at(8), cellsAt = r.u32(), cellCount = r.u32();
  r.skip(8);
  const cellsW = r.v.getInt32(r.p, true); r.p += 8;
  const cellSize = r.v.getInt16(r.p, true); r.p += 2;
  const flags = dump[r.p], dwords = dump[r.p + 1], world = at(64), grid = at(112).f32(), table = at(128), poolAt = table.u32(), poolN = table.u32();
  const world0 = [world.f32(), world.f32()], pools = [];
  for (let i = 0; i < poolN; i++) {
    const p = at(poolAt + i * 32 + 8), name = m3Pointer(p);
    p.skip(8);
    const bits = p.u32(), palette = p.v.getInt32(p.p, true);
    pools.push({ name: name == null ? '' : p.cstr(name), posOnly: !!(bits & 1), rotated: !!(bits & 2), noSeeds: !!(bits & 4), palette });
  }
  const cells = [], size = flags & 1 ? 8 : 4;
  for (let i = 0; i < cellCount; i++) {
    const c = at(cellsAt + i * 552 + 24), min = c.v.getInt16(c.p, true), delta = c.v.getInt16(c.p + 2, true), ofs = c.v.getInt32(c.p + 4, true);
    if (ofs < 0) continue;
    c.p += 8;
    const ptr = Array.from({ length: 65 }, () => m3Pointer(c)), counts = [];
    for (let s = 0; s < 64; s++) {
      if (ptr[s] == null || ptr[s + 1] == null) continue;
      for (let p = ptr[s]; p + size <= ptr[s + 1]; p += size) {
        const q = at(p);
        if (size === 8) counts.push([q.u32(), q.u32()]);
        else { const v = q.u32(); counts.push([(v & 0x3FF) | (v >>> 30) << 10, (v >>> 10) & 0xFFFFF]); }
      }
    }
    cells.push({ i, min, delta, ofs, counts });
  }
  return { cellsW, cellSize, grid, world0, dwords, pools, cells };
}

// every object of a layer, added to byName: {name: [rows of its matrices]}; cell is what the server unpacked for it
function m3Instances(layer, byName, unpacked) {
  const side = layer.cellSize * layer.grid, u = new MdReader(unpacked);
  for (const cell of layer.cells) {
    const size = u.u32(), d = new MdReader(u.take(size)), cx = cell.i % layer.cellsW, cz = Math.floor(cell.i / layer.cellsW);
    const add = [layer.world0[0] + cx * side, cell.min, layer.world0[1] + cz * side], mul = [side / 32767, (cell.delta || 8192) / 32767, side / 32767];
    if (!size) continue;
    for (const [poolId, count] of cell.counts) {
      const pool = layer.pools[poolId], out = byName.get(pool.name) || byName.set(pool.name, []).get(pool.name);
      const seeds = pool.noSeeds ? 0 : 4 * layer.dwords, n = pool.posOnly ? 4 : 12;
      for (let k = 0; k < count; k++) {
        const q = [];
        for (let i = 0; i < n; i++) { q.push(d.v.getInt16(d.p, true)); d.p += 2; }
        d.p += seeds;
        if (pool.posOnly) {
          let s = q[3] / 256, sin = 0, cos = 1;
          if (pool.rotated) {
            const v = q[3] & 0xFFFF, id = v & 7, a = 2 * Math.PI * id / Math.max(Math.min(pool.palette, 8), 1);
            s = (v & ~7) / 256; sin = Math.sin(a); cos = Math.cos(a);
          }
          out.push(s * cos, 0, -s * sin, q[0] * mul[0] + add[0], 0, s, 0, q[1] * mul[1] + add[1], s * sin, 0, s * cos, q[2] * mul[2] + add[2]);
        } else {
          out.push(q[0] / 256, q[1] / 256, q[2] / 256, q[3] * mul[0] + add[0], q[4] / 256, q[5] / 256, q[6] / 256, q[7] * mul[1] + add[1],
            q[8] / 256, q[9] / 256, q[10] / 256, q[11] * mul[2] + add[2]);
        }
      }
    }
  }
}

// a placed object's model: its vertex buffers and levels of detail, positions being fractions of its box
function m3RiModel(bytes) {
  const r = new MdReader(bytes), word = r.u32(), dumpSize = word & 0xFFFFFF, impostor = !!((word >>> 24) & 1), textures = r.u32();
  r.skip(8);
  const hdr = r.u32();
  if (textures !== 0xFFFFFFFF) r.take(r.u32());
  const buffers = mdVertexData(r, hdr), d = new MdReader(r.take(dumpSize)), lodAt = d.u32(), lodN = d.u32();
  d.skip(8);
  const lo = [d.f32(), d.f32(), d.f32()], hi = [d.f32(), d.f32(), d.f32()], lods = [];
  for (let l = 0; l < lodN; l++) {
    const size = r.u32(), voxel = r.u32();
    lods.push(mdMesh(r.take(size), 0));
    if (voxel) r.take(r.u32());
  }
  return { buffers, lods: impostor ? lods.slice(0, -1) : lods, offset: [0, 1, 2].map(i => (hi[i] + lo[i]) / 2), scale: [0, 1, 2].map(i => (hi[i] - lo[i]) / 2) };
}

// a mesh on the graphics card, in the game's own axes
function m3Upload(mesh, rows) {
  const gl = M3.gl, vao = gl.createVertexArray(), buffers = [];
  for (let i = 2; i < mesh.pos.length; i += 3) { mesh.pos[i] = -mesh.pos[i]; mesh.nor[i] = -mesh.nor[i]; }
  gl.bindVertexArray(vao);
  const put = (target, data, attr, size) => {
    const b = gl.createBuffer();
    gl.bindBuffer(target, b);
    gl.bufferData(target, data, gl.STATIC_DRAW);
    if (attr >= 0) { gl.enableVertexAttribArray(attr); gl.vertexAttribPointer(attr, size, gl.FLOAT, false, 0, 0); }
    buffers.push(b);
  };
  put(gl.ARRAY_BUFFER, mesh.pos, 0, 3);
  put(gl.ARRAY_BUFFER, mesh.nor, 1, 3);
  put(gl.ARRAY_BUFFER, mesh.uv, 2, 4);
  put(gl.ELEMENT_ARRAY_BUFFER, mesh.indices, -1);
  if (rows) {
    put(gl.ARRAY_BUFFER, rows, -1);
    for (let i = 0; i < 3; i++) {
      gl.enableVertexAttribArray(3 + i);
      gl.vertexAttribPointer(3 + i, 4, gl.FLOAT, false, 48, i * 16);
      gl.vertexAttribDivisor(3 + i, 1);
    }
  }
  return { vao, buffers, groups: mesh.groups, count: rows ? rows.length / 12 : 1 };
}

// a tree's leaves: the lightest level of detail that has them, as many trees as the budget allows
async function m3Leaves(model, list, rows, token) {
  const isLeaf = e => /facing_leaves/.test(list[e.material]?.cls || ''), elems = model.lods.map(l => l.filter(isLeaf)).filter(l => l.length).pop();
  const left = Math.min(M3_LEAF_TRIANGLES[0], M3_LEAF_TRIANGLES[1] - M3.leaves.reduce((s, o) => s + o.triangles, 0));
  if (!elems || left <= 0 || token !== M3.token) return;
  const gl = M3.gl, vd = model.buffers[elems[0].vdata];
  if (!vd || vd.stride !== 24) return;
  const mine = elems.filter(e => e.vdata === elems[0].vdata), total = mine.reduce((s, e) => s + e.triangles * 3, 0), idx = new Uint32Array(total), groups = [];
  let at = 0;
  for (const material of new Set(mine.map(e => e.material))) {
    const first = at;
    for (const e of mine.filter(x => x.material === material)) for (let i = e.first; i < e.first + e.triangles * 3; i++) idx[at++] = vd.indices[i] + e.base;
    groups.push({ material: list[material] || {}, first, count: at - first });
  }
  const n = rows.length / 12, every = Math.max(1, Math.ceil(n * total / 3 / left)), kept = new Float32Array(Math.ceil(n / every) * 12);
  for (let i = 0, o = 0; i < n; i += every, o += 12) kept.set(rows.slice(i * 12, i * 12 + 12), o);
  const vao = gl.createVertexArray(), buffers = [gl.createBuffer(), gl.createBuffer(), gl.createBuffer()];
  gl.bindVertexArray(vao);
  gl.bindBuffer(gl.ARRAY_BUFFER, buffers[0]);
  gl.bufferData(gl.ARRAY_BUFFER, vd.data, gl.STATIC_DRAW);
  gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 4, gl.HALF_FLOAT, false, 24, 0);
  gl.enableVertexAttribArray(2); gl.vertexAttribPointer(2, 2, gl.SHORT, false, 24, 8);
  gl.enableVertexAttribArray(6); gl.vertexAttribPointer(6, 4, gl.HALF_FLOAT, false, 24, 12);
  gl.enableVertexAttribArray(1); gl.vertexAttribPointer(1, 4, gl.UNSIGNED_BYTE, true, 24, 20);
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, buffers[1]);
  gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, idx, gl.STATIC_DRAW);
  gl.bindBuffer(gl.ARRAY_BUFFER, buffers[2]);
  gl.bufferData(gl.ARRAY_BUFFER, kept, gl.STATIC_DRAW);
  for (let i = 0; i < 3; i++) {
    gl.enableVertexAttribArray(3 + i);
    gl.vertexAttribPointer(3 + i, 4, gl.FLOAT, false, 48, i * 16);
    gl.vertexAttribDivisor(3 + i, 1);
  }
  gl.bindVertexArray(null);
  const leaf = { vao, buffers, groups, count: Math.ceil(n / every), triangles: Math.ceil(n / every) * total / 3 };
  M3.leaves.push(leaf);
  for (const g of groups) {
    g.tex = {};
    if (g.material.t0) g.tex.color = await m3Texture(g.material.t0);
    if (token !== M3.token) return;
  }
  m3Redraw();
}

// an asset: the game's objects that make it up, each in its place in the group (shown as they arrive), drawn where the asset stands
function m3Asset(cls) {
  const parts = [], token = M3.token, kinds = new Map();
  api('asset/' + encodeURIComponent(cls)).then(nodes => {
    for (const [name, row] of nodes) { if (!kinds.has(name)) kinds.set(name, []); kinds.get(name).push(...row); }
    for (const [name, rows] of kinds) m3Object(name, rows, token, parts).catch(e => console.warn(e));
  }).catch(e => console.warn(e));
  return { parts };
}

async function m3Object(name, rows, token, into = M3.objects) {
  const res = await fetch(`/api/model/ri/${encodeURIComponent(name)}`);
  if (!res.ok) return;
  const bytes = new Uint8Array(await res.arrayBuffer()), h = new MdReader(bytes), modelSize = h.u32(), treeSize = h.u32(), matSize = h.u32();
  const model = m3RiModel(bytes.subarray(12, 12 + modelSize));
  const mats = JSON.parse(new TextDecoder().decode(bytes.subarray(12 + modelSize + treeSize, 12 + modelSize + treeSize + matSize)));
  const list = mats.R || [], n = rows.length / 12, solid = e => !M3_NOT_OBJECT.test(list[e.material]?.cls || '') && !MD_NOT_SOLID.test(list[e.material]?.cls || '');
  const lods = model.lods.map(elems => elems.filter(solid)), cost = l => l.reduce((s, e) => s + e.triangles, 0) * n;
  const elems = lods.find(l => cost(l) && cost(l) <= M3_LOD_TRIANGLES) || lods.filter(l => l.length).pop();
  if (!elems || token !== M3.token) return;
  const object = m3Upload(mdAssemble({ parts: [{ elems, buffers: model.buffers }], offset: model.offset, scale: model.scale }, new Map(), { R: list }), new Float32Array(rows));
  into.push(object);
  m3Redraw();
  if (into === M3.objects) await m3Leaves(model, list, rows, token);  // shortcut: an asset's trees stay without their leaf cards, m3Frame draws those for the level only
  for (const g of object.groups) {
    const { t0, t1, cls } = g.material, mask = /tree/.test(cls) && /_a$/i.test(t1 || '') ? await m3Texture(t1) : null;
    g.tex = { mask, color: t0 ? await m3Texture(t0) : null };
    if (token !== M3.token) return;
  }
  m3Redraw();
}

function m3Texture(name) {
  M3.byName ||= new Map();
  if (!M3.byName.has(name)) M3.byName.set(name, mdTexture(M3, name, { low: true, max: M3_OBJECT_TEX }).catch(() => null));
  return M3.byName.get(name);
}

async function m3LoadObjects(level, token) {
  const status = text => { $('#m3Status').textContent = text; $('#m3Status').classList.toggle('hidden', !text); };
  status(t('editor.map3dLoading'));
  const res = await fetch(`/api/level-objects/${encodeURIComponent(level)}`);
  if (!res.ok) { status(''); return; }
  const raw = new Uint8Array(await res.arrayBuffer()), r = new MdReader(raw), byName = new Map();
  while (raw.length - r.p > 160) {
    const head = r.u32(), block = r.take(head & 0x3FFFFFFF), plain = lzDecode(block.subarray(4), new MdReader(block).u32());
    const d = new MdReader(plain), dump = d.take(d.u32()), layer = m3Layer(dump), word = r.u32(), start = r.p;
    r.take(word & 0x3FFFFFFF);
    const cells = await fetch('/api/level-cells', { method: 'POST', body: JSON.stringify({ level, start, cells: layer.cells.map(c => c.ofs) }) });
    if (!cells.ok) { status(''); return; }
    m3Instances(layer, byName, new Uint8Array(await cells.arrayBuffer()));
    if (token !== M3.token) return;
  }
  const queue = [...byName].filter(([name]) => name).sort((a, b) => a[1].length - b[1].length), total = queue.length;
  let done = 0;
  const worker = async () => {
    while (queue.length && token === M3.token) {
      const [name, rows] = queue.shift();
      try { await m3Object(name, rows, token); } catch (e) { console.warn(name, e); }
      done++;
      if (token === M3.token) status(done < total ? t('editor.map3dObjects', { n: done, total }) : '');
    }
  };
  await Promise.all([worker(), worker(), worker(), worker()]);
}

// ------------------------------------------------------------------ the units, as their real models
async function m3Unit(cls) {
  const mesh = await (async () => {
    const res = await fetch(`/api/model/vehicle/${encodeURIComponent(cls)}`);
    return res.ok ? mdParse(new Uint8Array(await res.arrayBuffer()), true) : null;
  })();
  if (!mesh?.triangles) return null;
  const object = m3Upload(mesh, null);
  m3Redraw();
  for (const g of object.groups) {
    g.tex = {};
    for (const [slot, name] of Object.entries(mdSlots(g.material))) {
      if (name) g.tex[slot] = await mdTexture(M3, name, { max: 1024 }).catch(() => null);
    }
  }
  m3Redraw();
  return object;
}

// ------------------------------------------------------------------ drawing
function m3Draw(gl, prog, object, instances) {
  const at = name => gl.getUniformLocation(prog, name);
  gl.bindVertexArray(object.vao);
  for (const g of object.groups) {
    const tex = g.tex || {}, m = g.material;
    if (m.atest && !tex.color) continue;  // a card without its texture is a plain rectangle
    ['color', 'camo', 'normal', 'ao', 'mask'].forEach((slot, i) => {
      gl.activeTexture(gl.TEXTURE0 + i);
      gl.bindTexture(gl.TEXTURE_2D, tex[slot] || null);
    });
    gl.uniform4i(at('uHas'), tex.color ? 1 : 0, tex.camo ? 1 : 0, tex.normal ? 1 : 0, tex.ao ? 1 : 0);
    gl.uniform1i(at('uSplit'), tex.mask ? 1 : 0);
    gl.uniform1f(at('uCut'), tex.color && (m.atest || /atest/.test(m.cls)) ? (m.atest ?? 127) / 255 : 0);
    gl.uniform1f(at('uAlpha'), 1);
    gl.drawElementsInstanced(gl.TRIANGLES, g.count, gl.UNSIGNED_INT, g.first * 4, instances);
  }
}

function m3Frame() {
  M3.raf = 0;
  if (!M3.on || !ED.canvas) return;
  const gl = M3.gl, cv = gl.canvas;
  if (cv.width !== ED.canvas.width || cv.height !== ED.canvas.height) { cv.width = ED.canvas.width; cv.height = ED.canvas.height; }
  if (!M3.ground || M3.ground.terrain !== ED.terrain) M3.ground = m3GroundMesh(ED.terrain, M3.ground);
  const land = M3.land && M3.land !== ED.terrain ? M3.land : null;
  if (land && M3.outer?.terrain !== land) M3.outer = m3GroundMesh(land, M3.outer);
  m3MapTextures();
  m3Camera();
  gl.viewport(0, 0, cv.width, cv.height);
  gl.enable(gl.DEPTH_TEST);
  gl.clearColor(0, 0, 0, 0);
  gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);

  gl.useProgram(M3.groundProg);
  gl.uniformMatrix4fv(gl.getUniformLocation(M3.groundProg, 'uVp'), false, M3.vp);
  const maps = M3.maps.slice(-2), has = [0, 0], up = [0, 0];
  maps.forEach((m, i) => {
    gl.activeTexture(gl.TEXTURE0 + i);
    gl.bindTexture(gl.TEXTURE_2D, m.tex);
    gl.uniform1i(gl.getUniformLocation(M3.groundProg, `uMap${i}`), i);
    gl.uniform4f(gl.getUniformLocation(M3.groundProg, `uRect${i}`), m.layer.min[0], m.layer.min[1], m.layer.max[0], m.layer.max[1]);
    has[i] = 1;
    up[i] = m.layer.zUp ? 1 : 0;
  });
  gl.uniform2i(gl.getUniformLocation(M3.groundProg, 'uHas'), has[0], has[1]);
  gl.uniform2f(gl.getUniformLocation(M3.groundProg, 'uUp'), up[0], up[1]);
  gl.uniform4f(gl.getUniformLocation(M3.groundProg, 'uFlat'), 0, 0, 0, 0);
  gl.uniform4f(gl.getUniformLocation(M3.groundProg, 'uClip'), 0, 0, 0, 0);
  gl.bindVertexArray(M3.ground.vao);
  gl.drawElements(gl.TRIANGLES, M3.ground.count, gl.UNSIGNED_INT, 0);
  if (land && ED.terrain) {  // around the battle area: the whole level, coarser, a little under its edge so that no gap shows
    const T = ED.terrain, inset = land.cell * 2;
    gl.uniform4f(gl.getUniformLocation(M3.groundProg, 'uClip'), T.ofs[0] + inset, T.ofs[1] + inset, T.ofs[0] + T.w * T.cell - inset, T.ofs[1] + T.h * T.cell - inset);
    gl.bindVertexArray(M3.outer.vao);
    gl.drawElements(gl.TRIANGLES, M3.outer.count, gl.UNSIGNED_INT, 0);
  }

  const p = M3.objProg, at = name => gl.getUniformLocation(p, name);
  gl.useProgram(p);
  gl.uniformMatrix4fv(at('uVp'), false, M3.vp);
  gl.uniformMatrix4fv(at('uParent'), false, M3_IDENTITY);
  gl.uniform3fv(at('uEye'), M3.eye);
  ['uColor', 'uCamo', 'uNormal', 'uAo', 'uMask'].forEach((name, i) => gl.uniform1i(at(name), i));
  for (const o of M3.objects) m3Draw(gl, p, o, o.count);
  if (M3.leaves.length) {
    const q = M3.leafProg ||= m3Program(gl, M3_LEAF_VS, MD_FS), um = name => gl.getUniformLocation(q, name), { x, y, z } = M3.cam;
    gl.useProgram(q);
    gl.uniformMatrix4fv(um('uVp'), false, M3.vp);
    gl.uniform3fv(um('uEye'), M3.eye);
    gl.uniform3f(um('uRight'), x[0], x[1], -x[2]);
    gl.uniform3f(um('uUp'), y[0], y[1], -y[2]);
    gl.uniform3f(um('uToward'), z[0], z[1], -z[2]);
    ['uColor', 'uCamo', 'uNormal', 'uAo', 'uMask'].forEach((name, i) => gl.uniform1i(um(name), i));
    for (const o of M3.leaves) {
      gl.bindVertexArray(o.vao);
      for (const g of o.groups) {
        const tex = g.tex?.color;
        if (!tex) continue;
        gl.activeTexture(gl.TEXTURE0);
        gl.bindTexture(gl.TEXTURE_2D, tex);
        gl.uniform4i(um('uHas'), 1, 0, 0, 0);
        gl.uniform1f(um('uCut'), 127 / 255);
        gl.uniform1f(um('uAlpha'), 1);
        gl.drawElementsInstanced(gl.TRIANGLES, g.count, gl.UNSIGNED_INT, g.first * 4, o.count);
      }
    }
    gl.useProgram(p);
  }

  for (const u of edAllPoints().map(edUnitState)) {
    if (u.removed || u.player || !(u.edit || u.added) || !u.cls) continue;
    const a = (u.yaw || 0) * Math.PI / 180, c = Math.cos(a), s = Math.sin(a), y = u.y ?? edGround(u.x, u.z) ?? 0;
    if (u.block === 'objectGroups') {
      const key = 'asset:' + u.cls;
      if (!M3.units.has(key)) M3.units.set(key, m3Asset(u.cls));
      gl.uniformMatrix4fv(at('uParent'), false, new Float32Array([c, 0, s, 0, 0, 1, 0, 0, -s, 0, c, 0, u.x, y, u.z, 1]));
      for (const o of M3.units.get(key).parts) m3Draw(gl, p, o, o.count);
      gl.uniformMatrix4fv(at('uParent'), false, M3_IDENTITY);
      continue;
    }
    const entry = M3.units.get(u.cls);
    if (entry === undefined) { M3.units.set(u.cls, null); m3Unit(u.cls).then(o => { M3.units.set(u.cls, o); m3Redraw(); }).catch(() => {}); continue; }
    if (!entry) continue;
    gl.vertexAttrib4f(3, c, 0, -s, u.x);
    gl.vertexAttrib4f(4, 0, 1, 0, y);
    gl.vertexAttrib4f(5, s, 0, c, u.z);
    m3Draw(gl, p, entry, 1);
  }
  if (M3.water != null) m3Water(gl);
  m3Zones(gl);
  gl.bindVertexArray(null);
}

// the level's water: a plane at its height, over its ground
function m3Water(gl) {
  const T = M3.land || ED.terrain, y = M3.water;
  if (!T) return;
  const x0 = T.ofs[0], z0 = T.ofs[1], x1 = x0 + T.w * T.cell, z1 = z0 + T.h * T.cell;
  M3.waterVao ||= gl.createVertexArray();
  gl.bindVertexArray(M3.waterVao);
  M3.waterBuf ||= gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, M3.waterBuf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([x0, y, z0, x1, y, z0, x0, y, z1, x1, y, z1]), gl.DYNAMIC_DRAW);
  gl.enableVertexAttribArray(0);
  gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);
  gl.useProgram(M3.groundProg);
  gl.uniformMatrix4fv(gl.getUniformLocation(M3.groundProg, 'uVp'), false, M3.vp);
  gl.uniform4f(gl.getUniformLocation(M3.groundProg, 'uFlat'), 0.17, 0.27, 0.33, 0.78);
  gl.enable(gl.BLEND);
  gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
  gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  gl.disable(gl.BLEND);
}

// a zone's shape, of unit size, as a surface of revolution (a box has four sides): profile is [radius, height, drawn as a ring]
function m3Lathe(profile, sides, turn, pos, indices) {
  const base = pos.length / 3, at = (j, i) => base + j * sides + i % sides, faces = [], edges = [];
  for (const [r, y] of profile) for (let i = 0; i < sides; i++) { const a = turn + i / sides * Math.PI * 2; pos.push(r * Math.cos(a), y, r * Math.sin(a)); }
  profile.forEach(([r, , ring], j) => {
    for (let i = 0; i < sides; i++) {
      if (ring) edges.push(at(j, i), at(j, i + 1));
      if (j + 1 === profile.length) continue;
      faces.push(at(j, i), at(j, i + 1), at(j + 1, i), at(j, i + 1), at(j + 1, i + 1), at(j + 1, i));
      if (i % (sides / 4) === 0 && r && profile[j + 1][0]) edges.push(at(j, i), at(j + 1, i));
    }
  });
  const first = indices.length;
  indices.push(...faces, ...edges);
  return { first, faces: faces.length, edges: edges.length };
}

function m3ZoneShapes(gl) {
  const pos = [], indices = [], arc = Array.from({ length: 17 }, (_, k) => [Math.sin(k / 16 * Math.PI), Math.cos(k / 16 * Math.PI), k === 8]);
  M3.zoneShapes = {
    box: m3Lathe([[0, 1], [Math.SQRT2, 1, true], [Math.SQRT2, -1, true]], 4, Math.PI / 4, pos, indices),
    cylinder: m3Lathe([[0, 1], [1, 1, true], [1, -1, true]], 48, 0, pos, indices),
    sphere: m3Lathe(arc, 48, 0, pos, indices),
  };
  M3.zoneVao = gl.createVertexArray();
  gl.bindVertexArray(M3.zoneVao);
  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(pos), gl.STATIC_DRAW);
  gl.enableVertexAttribArray(0);
  gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, gl.createBuffer());
  gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, new Uint16Array(indices), gl.STATIC_DRAW);
}

// the zones the map outlines, as volumes: over what is already drawn, hiding nothing behind them
function m3Zones(gl) {
  const items = edZoneItems(window.devicePixelRatio || 1).filter(i => i.outline);
  if (!items.length) return;
  const p = M3.zoneProg ||= m3Program(gl, M3_ZONE_VS, M3_ZONE_FS), at = name => gl.getUniformLocation(p, name);
  if (!M3.zoneVao) m3ZoneShapes(gl);
  gl.useProgram(p);
  gl.uniformMatrix4fv(at('uVp'), false, M3.vp);
  gl.bindVertexArray(M3.zoneVao);
  gl.enable(gl.BLEND);
  gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
  gl.depthMask(false);
  for (const { z0, z, info, sel } of items) {
    const box = /box/i.test(z.type), sphere = /sphere/i.test(z.type), shape = M3.zoneShapes[box ? 'box' : sphere ? 'sphere' : 'cylinder'];
    const a = z.yaw * Math.PI / 180, c = Math.cos(a), s = Math.sin(a), wide = box ? z.sx / 2 : z.sx, deep = box ? z.sz / 2 : z.sx, high = sphere ? z.sx : z.sy / 2;
    const color = sel ? ED_COLORS.player : edZoneColor(z0, info), [r, g, b] = color[0] === '#' ? [1, 3, 5].map(i => parseInt(color.slice(i, i + 2), 16) / 255) : [1, 1, 1];
    gl.uniformMatrix4fv(at('uTm'), false, new Float32Array([c * wide, 0, s * wide, 0, 0, high, 0, 0, -s * deep, 0, c * deep, 0, z.x, z.y, z.z, 1]));
    gl.uniform4f(at('uTint'), r, g, b, sel ? 0.3 : info.role ? 0.2 : 0.1);
    gl.uniform1f(at('uFade'), 0.15);
    gl.drawElements(gl.TRIANGLES, shape.faces, gl.UNSIGNED_SHORT, shape.first * 2);
    gl.uniform4f(at('uTint'), r, g, b, z0.used || sel ? 0.9 : 0.5);
    gl.uniform1f(at('uFade'), 1);
    gl.drawElements(gl.LINES, shape.edges, gl.UNSIGNED_SHORT, (shape.first + shape.faces) * 2);
  }
  gl.depthMask(true);
  gl.disable(gl.BLEND);
}

function m3Redraw() {
  if (M3.on && !M3.raf) M3.raf = requestAnimationFrame(m3Frame);
}

function m3Clear() {
  const gl = M3.gl;
  if (!gl) return;
  for (const o of [...M3.objects, ...M3.leaves, ...[...M3.units.values()].filter(Boolean).flatMap(u => u.parts || [u])]) { gl.deleteVertexArray(o.vao); o.buffers.forEach(b => gl.deleteBuffer(b)); }
  M3.textures.forEach(x => gl.deleteTexture(x));
  M3.maps.forEach(m => gl.deleteTexture(m.tex));
  Object.assign(M3, { objects: [], leaves: [], units: new Map(), textures: [], maps: [], byName: new Map(), level: null, baked: false, land: null });
}

// the editor's 2D / 3D slider: the flat map at 0; from there the view tilts down from straight above, north up as on the map
function m3Toggle() {
  const cv = $('#m3Canvas');
  M3.on = !M3.on;
  cv.classList.toggle('hidden', !M3.on);
  if (!M3.on) $('#ed3d').checked = false;
  if (M3.on) {
    M3.gl ||= cv.getContext('webgl2', { antialias: true, alpha: true });
    if (!M3.gl) { M3.on = false; cv.classList.add('hidden'); $('#ed3d').checked = false; return; }
    M3.yaw = 0;
    M3.pitch = 0.7;
    M3.groundProg ||= m3Program(M3.gl, M3_GROUND_VS, M3_GROUND_FS);
    M3.objProg ||= m3Program(M3.gl, M3_OBJ_VS, MD_FS);
    cv.width = ED.canvas.width; cv.height = ED.canvas.height;
    m3Camera();
    if (M3.level !== ED.data.level) {
      m3Clear();
      M3.level = ED.data.level;
      M3.water = null;
      api('level-info/' + encodeURIComponent(M3.level)).then(i => { M3.water = i.water; m3Redraw(); }).catch(() => {});
      const token = ++M3.token, level = M3.level;
      api('level-ground/' + encodeURIComponent(level)).then(async info => {
        if (!info.classes) return;
        await m3LoadLand(level, info, token);
        await m3LoadGround(level, info, token);
      }).catch(e => console.warn(e));
      m3LoadObjects(M3.level, token).catch(e => { console.warn(e); $('#m3Status').classList.add('hidden'); });
    }
  } else $('#m3Status').classList.add('hidden');
}
