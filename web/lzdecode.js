/* WTFTD — decoder for the block-compressed streams of the game's model files: LZ77 with Huffman, tANS and run-length
   coding, the block format known as Leviathan (the only one the game's models use). Plain JavaScript port of lztans:

   MIT License

   Copyright (c) 2026 patodois

   Permission is hereby granted, free of charge, to any person obtaining a copy
   of this software and associated documentation files (the "Software"), to deal
   in the Software without restriction, including without limitation the rights
   to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
   copies of the Software, and to permit persons to whom the Software is
   furnished to do so, subject to the following conditions:

   The above copyright notice and this permission notice shall be included in all
   copies or substantial portions of the Software.

   THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
   IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
   FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
   AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
   LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
   OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
   SOFTWARE. */
'use strict';

const LZ_BLOCK = 262144, LZ_SUB = 131072, LZ_DEPTH = 24, HUFF_LEN = 11, HUFF_SIZE = 2048;
const lzBad = what => { throw new Error('lz: ' + what); };

// ------------------------------------------------------------------ bit readers: bytes past the region read as zero
class Mf {  // most significant bit first, forward
  constructor(d) { this.d = d; this.bit = 0; }
  peek(k) {
    if (!k) return 0;
    const d = this.d, i = this.bit >>> 3, s = this.bit & 7;
    const hi = (d[i] << 24 | d[i + 1] << 16 | d[i + 2] << 8 | d[i + 3]) >>> 0;
    const w = s ? (hi << s | d[i + 4] >>> (8 - s)) >>> 0 : hi;
    return k === 32 ? w : w >>> (32 - k);
  }
  consume(k) { this.bit += k; }
  read(k) { const v = this.peek(k); this.bit += k; return v; }
  zeros() { const w = this.peek(32); return w ? Math.clz32(w) : -1; }
  bytePos() { return Math.ceil(this.bit / 8); }
  overrun() { return this.bit > this.d.length * 8; }
}
class Mb extends Mf {  // most significant bit first, from the last byte backward
  peek(k) {
    if (!k) return 0;
    const d = this.d, i = d.length - 1 - (this.bit >>> 3), s = this.bit & 7;
    const hi = (d[i] << 24 | d[i - 1] << 16 | d[i - 2] << 8 | d[i - 3]) >>> 0;
    const w = s ? (hi << s | d[i - 4] >>> (8 - s)) >>> 0 : hi;
    return k === 32 ? w : w >>> (32 - k);
  }
}
// least significant bit first: at least 17 bits from bit position p, forward or from the last byte backward
const lfBits = (d, p) => { const i = p >>> 3; return (d[i] | d[i + 1] << 8 | d[i + 2] << 16) >>> (p & 7); };
const lbBits = (d, n, p) => { const i = n - 1 - (p >>> 3); return (d[i] | d[i - 1] << 8 | d[i - 2] << 16) >>> (p & 7); };

// ------------------------------------------------------------------ code tables
const zigzag = v => (v >>> 1) ^ -(v & 1);
function readUnary(r) {
  let total = 0;
  for (;;) {
    const z = r.zeros();
    if (z >= 0) {
      r.consume(z + 1);
      total += z;
      if (total >= 4096) lzBad('unary count too large');
      return total;
    }
    r.consume(32);
    total += 32;
    if (total >= 4096) lzBad('unary count too large');
  }
}
function readTruncated(r, x) {
  const y = 32 - Math.clz32(x - 1), u = (1 << y) - x, v = r.peek(y);
  if ((v >>> 1) >= u) { r.consume(y); return v - u; }
  r.consume(y - 1);
  return v >>> 1;
}
// the coded symbols in ascending order, ns of them
function readRanges(r, ns, extras) {
  const syms = [];
  let sym = 0, used = 0, j = 0;
  const x = extras.length;
  if (x % 2 === 1) {
    const v = extras[0];
    j = 1;
    if (v >= 8) lzBad('symbol range: initial gap');
    sym = r.read(v + 1) + (1 << (v + 1)) - 1;
  }
  for (let i = 0; i < x >> 1; i++) {
    const v1 = extras[j++];
    if (v1 >= 9) lzBad('symbol range: count');
    const count = r.read(v1) + (1 << v1);
    const v2 = extras[j++];
    if (v2 >= 8) lzBad('symbol range: gap');
    const gap = r.read(v2 + 1) + (1 << (v2 + 1)) - 1;
    if (sym + count > 256) lzBad('symbol range beyond 255');
    for (let s = sym; s < sym + count; s++) syms.push(s);
    used += count;
    sym += count + gap;
  }
  if (sym >= 256 || used >= ns || sym + (ns - used) > 256) lzBad('symbol range: inconsistent');
  for (let s = sym, end = sym + (ns - used); s < end; s++) syms.push(s);
  return syms;
}

function huffLz(r) { const z = r.zeros(); if (z < 0) lzBad('too many leading zero bits'); return z; }
function readGamma(r) {
  if (r.peek(8) === 0) lzBad('gamma code starts with eight zero bits');
  const z = huffLz(r);
  r.consume(z + 1);
  return (2 ** (z + 1)) + r.read(z + 1) - 1;
}
function huffNew(r, lists) {
  const k = r.read(2), ns = r.read(8) + 1;
  const xcount = ns === 256 ? 0 : readTruncated(r, 2 * Math.min(257 - ns, ns));
  const u = [];
  for (let i = 0; i < ns + xcount; i++) {
    const v = readUnary(r);
    if (v >= 256) lzBad('huffman: unary count');
    u.push(v);
  }
  const c = u.slice(0, ns), extras = u.slice(ns), lens = [];
  if (k > 0) for (let i = 0; i < ns; i++) c[i] = c[i] << k | r.read(k);
  let run = 30;
  for (const ci of c) {
    const d = zigzag(ci), len = d + (run >> 2) + 1;
    if (len < 1 || len > HUFF_LEN) lzBad('huffman: code length');
    lens.push(len);
    run += d;
  }
  const syms = readRanges(r, ns, extras);
  syms.forEach((s, i) => lists[lens[i]].push(s));
}
function huffSparse(r, lists) {
  const ns = r.read(8);
  if (ns < 2) lzBad('huffman: sparse description too short');
  const cb = r.read(3);
  if (cb > 4) lzBad('huffman: sparse length width');
  for (let i = 0; i < ns; i++) {
    const s = r.read(8), len = r.read(cb) + 1;
    if (len > HUFF_LEN) lzBad('huffman: sparse code length');
    lists[len].push(s);
  }
}
function huffDense(r, lists) {
  const k = r.read(2), zmax = 20 >> k;
  let skip = r.read(1) === 1, sym = 0, coded = 0, mean4 = 32;
  while (sym < 256) {
    if (skip) skip = false;
    else {
      sym += readGamma(r);
      if (sym >= 256) break;
    }
    const n = readGamma(r);
    if (sym + n > 256) lzBad('huffman: dense group beyond 255');
    coded += n;
    for (let i = 0; i < n; i++) {
      const z = huffLz(r);
      if (z > zmax) lzBad('huffman: dense code too long');
      r.consume(z + 1);
      const f = r.read(k), len = zigzag(z << k | f) + ((mean4 + 2) >> 2);
      if (len < 1 || len > HUFF_LEN) lzBad('huffman: dense code length');
      mean4 = len + ((3 * mean4 + 2) >> 2);
      lists[len].push(sym++);
    }
  }
  if (sym !== 256 || coded < 2) lzBad('huffman: dense description inconsistent');
}
function rev11(v) { let o = 0; for (let i = 0; i < HUFF_LEN; i++) { o = o << 1 | v & 1; v >>= 1; } return o; }
function huffTable(r) {
  const lists = Array.from({ length: HUFF_LEN + 1 }, () => []);
  if (r.read(1) === 1) {
    if (r.read(1) !== 0) lzBad('huffman: description selector');
    huffNew(r, lists);
  } else if (r.read(1) === 1) huffDense(r, lists);
  else huffSparse(r, lists);
  if (r.overrun()) lzBad('huffman: description runs past the array');
  const t = new Uint16Array(HUFF_SIZE);
  let slot = 0;
  for (let len = 1; len <= HUFF_LEN; len++) {
    const width = 1 << (HUFF_LEN - len);
    for (const s of lists[len]) {
      if (slot + width > HUFF_SIZE) lzBad('huffman: code space overfull');
      const entry = s | len << 8;
      for (let sl = slot; sl < slot + width; sl++) t[rev11(sl)] = entry;
      slot += width;
    }
  }
  if (slot !== HUFF_SIZE) lzBad('huffman: code space not full');
  return t;
}
// three bit streams, one symbol from each in turn: region starts with the length of the first one
function huffThree(region, out, start, end, t) {
  if (region.length < 2) lzBad('huffman: payload too short');
  const m = region[0] | region[1] << 8;
  if (2 + m > region.length) lzBad('huffman: stream length');
  const a = region.subarray(2, 2 + m), bc = region.subarray(2 + m), n = bc.length;
  let pa = 0, pb = 0, pc = 0, o = start;
  const whole = end - (end - start) % 3;
  for (; o < whole; o += 3) {
    let e = t[lfBits(a, pa) & 2047]; pa += e >>> 8; out[o] = e;
    e = t[lbBits(bc, n, pc) & 2047]; pc += e >>> 8; out[o + 1] = e;
    e = t[lfBits(bc, pb) & 2047]; pb += e >>> 8; out[o + 2] = e;
  }
  if (o < end) {
    const e = t[lfBits(a, pa) & 2047]; pa += e >>> 8; out[o] = e;
    if (o + 1 < end) { const f = t[lbBits(bc, n, pc) & 2047]; pc += f >>> 8; out[o + 1] = f; }
  }
  if (Math.ceil(pa / 8) !== m || Math.ceil(pb / 8) + Math.ceil(pc / 8) !== n) lzBad('huffman: bit streams not exactly consumed');
}
function huffDecode(body, outLen, six) {
  const r = new Mf(body), t = huffTable(r);
  const rest = body.subarray(Math.min(r.bytePos(), body.length)), out = new Uint8Array(outLen);
  if (!six) { huffThree(rest, out, 0, outLen, t); return out; }
  if (rest.length < 3) lzBad('huffman: payload too short');
  const m = rest[0] | rest[1] << 8 | rest[2] << 16;
  if (m > rest.length - 3) lzBad('huffman: six-stream split');
  const half = Math.ceil(outLen / 2);
  huffThree(rest.subarray(3, 3 + m), out, 0, half, t);
  huffThree(rest.subarray(3 + m), out, half, outLen, t);
  return out;
}

function rleDecode(body, outLen, depth) {
  if (!body.length) lzBad('rle: empty body');
  const out = new Uint8Array(outLen);
  if (body.length === 1) return out.fill(body[0]);
  let w = body.subarray(1);
  if (body[0] !== 0) {
    const [arr, n] = lzArray(body, outLen, depth + 1);
    w = new Uint8Array(arr.length + body.length - n);
    w.set(arr);
    w.set(body.subarray(n), arr.length);
  }
  let lit = 0, end = w.length, fill = 0, o = 0;
  while (lit < end) {
    const cmd = w[end - 1];
    let copy, run;
    if (cmd === 0 || cmd > 0x2F) {
      end -= 1;
      copy = ~cmd & 15;
      run = cmd >> 4;
    } else if (cmd === 1) {
      end -= 1;
      if (lit >= end) lzBad('rle: missing literal for run byte');
      fill = w[lit++];
      continue;
    } else {
      if (end - lit < 2) lzBad('rle: truncated command');
      const v = cmd << 8 | w[end - 2];
      end -= 2;
      if (cmd >= 0x10) { copy = (v - 4096) & 63; run = (v - 4096) >> 6; }
      else if (cmd >= 9) { copy = 0; run = (v - 0x8FF) * 128; }
      else { copy = (v - 511) * 64; run = 0; }
    }
    if (copy > end - lit) lzBad('rle: literal count beyond the data');
    if (copy + run > outLen - o) lzBad('rle: output overrun');
    out.set(w.subarray(lit, lit + copy), o);
    lit += copy;
    o += copy;
    out.fill(fill, o, o + run);
    o += run;
  }
  if (o !== outLen) lzBad('rle: output size mismatch');
  return out;
}

function tansWeights(r) {
  if (r.read(1) !== 0) lzBad('tans: reserved bit set');
  const tb = r.read(2) + 8, size = 1 << tb, golomb = r.read(1) === 1, out = [];
  if (golomb) {
    const q = r.read(3), ns = r.read(8) + 1;
    if (ns < 2) lzBad('tans: fewer than two symbols');
    const xcount = ns === 256 ? 0 : readTruncated(r, 2 * Math.min(257 - ns, ns));
    const u = [];
    for (let i = 0; i < ns + xcount; i++) u.push(readUnary(r));
    const codes = u.slice(0, ns), syms = readRanges(r, ns, u.slice(ns));
    let mean = 6, total = 0;
    syms.forEach((s, i) => {
      const wBits = codes[i] + q;
      if (wBits > 15) lzBad('tans: weight width');
      let v = r.read(wBits) + (1 << wBits) - (1 << q);
      const a4 = mean >> 2;
      let limit = 2 * a4;
      if (v <= limit) v = a4 + zigzag(v);
      if (limit > v) limit = v;
      const w = v + 1;
      if (w < 1) lzBad('tans: weight below one');
      mean += limit - a4;
      total += w;
      if (total > size) lzBad('tans: weights exceed table size');
      out.push([s, w]);
    });
    if (total !== size) lzBad('tans: weights do not fill the table');
  } else {
    const count = r.read(3) + 1, bps = 32 - Math.clz32(tb), mdb = r.read(bps);
    if (mdb < 1 || mdb > tb) lzBad('tans: sparse weight width');
    const seen = new Set();
    let weight = 0, total = 0;
    for (let i = 0; i < count; i++) {
      const s = r.read(8);
      if (seen.has(s)) lzBad('tans: repeated symbol');
      seen.add(s);
      weight += r.read(mdb);
      if (weight === 0) lzBad('tans: zero weight');
      total += weight;
      if (total >= size) lzBad('tans: weights exceed table size');
      out.push([s, weight]);
    }
    const s = r.read(8);
    if (seen.has(s)) lzBad('tans: repeated symbol');
    const last = size - total;
    if (last < weight || last <= 1) lzBad('tans: last weight');
    out.push([s, last]);
    out.sort((a, b) => a[0] - b[0]);
  }
  if (r.overrun()) lzBad('tans: table runs past the array');
  return [tb, out];
}
function tansTable(tb, weights) {
  const size = 1 << tb, mask = size - 1;
  const singles = weights.filter(e => e[1] === 1).map(e => e[0]), states = size - singles.length;
  const symbol = new Uint8Array(size), nbits = new Uint8Array(size), base = new Uint16Array(size);
  singles.forEach((s, i) => { symbol[states + i] = s; nbits[states + i] = tb; });
  const a = Math.floor(states / 4), rem = states % 4, cursor = [0, 0, 0, 0], ends = [0, 0, 0, 0];
  let acc = 0;
  for (let j = 0; j < 4; j++) {
    cursor[j] = acc;
    acc += a + (j < rem ? 1 : 0);
    ends[j] = acc;
  }
  let p = 0;
  for (const [sym, w] of weights) {
    if (w <= 1) continue;
    let k = 0;
    for (let j = 0; j < 4; j++) {
      const off = (j + 4 - (p % 4)) % 4, cj = w > off ? Math.ceil((w - off) / 4) : 0;
      for (let c = 0; c < cj; c++) {
        if (cursor[j] >= ends[j]) lzBad('tans: region overflow');
        const wv = w + k, nb = tb - (31 - Math.clz32(wv)), at = cursor[j]++;
        symbol[at] = sym;
        nbits[at] = nb;
        base[at] = (wv << nb) & mask;
        k++;
      }
    }
    p += w;
  }
  return { symbol, nbits, base };
}
function tansDecode(body, outLen) {
  if (outLen < 5 || body.length < 8) lzBad('tans: array too small');
  const r = new Mf(body), [tb, weights] = tansWeights(r), { symbol, nbits, base } = tansTable(tb, weights);
  const start = r.bytePos();
  if (start >= body.length) lzBad('tans: no payload');
  const payload = body.subarray(start), n = payload.length, tmask = (1 << tb) - 1;
  let pf = 0, pb = 0;
  const st = [0, 0, 0, 0, 0];
  st[0] = lfBits(payload, pf) & tmask; pf += tb;
  st[1] = lbBits(payload, n, pb) & tmask; pb += tb;
  st[2] = lfBits(payload, pf) & tmask; pf += tb;
  st[3] = lbBits(payload, n, pb) & tmask; pb += tb;
  st[4] = lfBits(payload, pf) & tmask; pf += tb;
  const out = new Uint8Array(outLen), main = outLen - 5;
  for (let i = 0; i < main; i++) {
    const j = i % 5, s = st[j], nb = nbits[s];
    out[i] = symbol[s];
    if ((i - j) % 10 === 0) {  // the groups of five alternate between the two streams
      st[j] = base[s] + (lfBits(payload, pf) & ((1 << nb) - 1));
      pf += nb;
    } else {
      st[j] = base[s] + (lbBits(payload, n, pb) & ((1 << nb) - 1));
      pb += nb;
    }
  }
  st.forEach((s, k) => {
    if (s > 255) lzBad('tans: final state is not a byte');
    out[main + k] = s;
  });
  if (start + Math.ceil(pf / 8) !== body.length - Math.ceil(pb / 8)) lzBad('tans: bit streams not exactly consumed');
  return out;
}

// ------------------------------------------------------------------ byte arrays
// one array from the start of src: [bytes, input bytes used]
function lzArray(src, limit, depth) {
  if (depth > LZ_DEPTH) lzBad('arrays nested too deeply');
  if (!src.length) lzBad('truncated');
  const h0 = src[0], ty = (h0 >> 4) & 7;
  if (ty === 0) {
    let size, off;
    if (h0 >= 0x80) {
      if (src.length < 2) lzBad('truncated');
      size = (h0 << 8 | src[1]) & 0x0FFF;
      off = 2;
    } else {
      if (src.length < 3) lzBad('truncated');
      const v = h0 << 16 | src[1] << 8 | src[2];
      if (v >> 18) lzBad('stored array: size');
      size = v;
      off = 3;
    }
    if (size > limit) lzBad('array larger than its limit');
    if (off + size > src.length) lzBad('truncated');
    return [src.subarray(off, off + size), off + size];
  }
  if (ty > 5) lzBad('invalid array type');
  let bodyLen, outLen, hdr;
  if (h0 >= 0x80) {
    if (src.length < 3) lzBad('truncated');
    const b = h0 << 16 | src[1] << 8 | src[2];
    bodyLen = b & 0x3FF;
    outLen = bodyLen + ((b >> 10) & 0x3FF) + 1;
    hdr = 3;
  } else {
    if (src.length < 5) lzBad('truncated');
    const c = (src[1] << 24 | src[2] << 16 | src[3] << 8 | src[4]) >>> 0;
    bodyLen = c & 0x3FFFF;
    outLen = ((h0 & 0x0F) * 16384 + Math.floor(c / 262144)) + 1;
    if (bodyLen >= outLen) lzBad('array: source size not below decoded size');
    hdr = 5;
  }
  if (outLen > limit) lzBad('array larger than its limit');
  if (hdr + bodyLen > src.length) lzBad('truncated');
  const body = src.subarray(hdr, hdr + bodyLen);
  const data = ty === 1 ? tansDecode(body, outLen) : ty === 2 ? huffDecode(body, outLen, false)
    : ty === 3 ? rleDecode(body, outLen, depth) : ty === 4 ? huffDecode(body, outLen, true) : lzConcat(body, outLen, depth);
  return [data, hdr + bodyLen];
}
function lzConcat(body, outLen, depth) {
  if (!body.length) lzBad('truncated');
  const b = body[0], n = b & 0x7F;
  if (n < 2 || body.length < 6) lzBad('concatenated array: too small');
  if (b & 0x80) {
    const [outs, used] = lzSliced(body, 1, outLen, depth);
    if (outs[0].length !== outLen || used !== body.length) lzBad('sliced container: size mismatch');
    return outs[0];
  }
  const out = new Uint8Array(outLen);
  let pos = 1, o = 0;
  for (let i = 0; i < n; i++) {
    const [a, used] = lzArray(body.subarray(pos), outLen - o, depth + 1);
    out.set(a, o);
    o += a.length;
    pos += used;
  }
  if (o !== outLen || pos !== body.length) lzBad('concatenated array: size mismatch');
  return out;
}
// the multi-array container of type-5 arrays and of literals and commands: [arrays, input bytes used]
function lzSliced(src, nOut, limit, depth) {
  if (src.length < 4) lzBad('truncated');
  const b = src[0];
  if (!(b & 0x80)) lzBad('sliced container: count byte');
  const nIn = b & 0x3F;
  let pos = 1;
  if (nIn === 0) {
    const outs = [];
    let left = limit;
    for (let i = 0; i < nOut; i++) {
      const [a, n] = lzArray(src.subarray(pos), left, depth + 1);
      left -= a.length;
      pos += n;
      outs.push(a);
    }
    return [outs, pos];
  }
  const sources = [];
  let total = 0;
  for (let i = 0; i < nIn; i++) {
    const [a, n] = lzArray(src.subarray(pos), limit - total, depth + 1);
    total += a.length;
    pos += n;
    sources.push(a);
  }
  if (src.length < pos + 2) lzBad('truncated');
  const q = src[pos] | src[pos + 1] << 8;
  pos += 2;
  const vb = q & 0x3FFF, combined = !!(q & 0x8000);
  let index, exps, nExp;
  if (combined) {
    const [a, n] = lzArray(src.subarray(pos), total, depth + 1);
    pos += n;
    index = a.map(t => t & 15);
    exps = a.map(t => t >> 4);
    nExp = index.length;
  } else {
    const [a, n] = lzArray(src.subarray(pos), total, depth + 1);
    pos += n;
    if (a.length < nOut) lzBad('sliced container: fewer intervals than arrays');
    nExp = a.length - nOut;
    const [e, n2] = lzArray(src.subarray(pos), nExp, depth + 1);
    pos += n2;
    if (e.length !== nExp) lzBad('sliced container: exponent count');
    if (e.some(x => x > 16)) lzBad('sliced container: exponent above 16');
    index = a;
    exps = e;
  }
  if (index.length > total) lzBad('sliced container: too many intervals');
  if (vb > src.length - pos) lzBad('truncated');
  const streams = src.subarray(pos, pos + vb);
  pos += vb;
  if (index[index.length - 1] !== 0) lzBad('sliced container: last index is not zero');
  const fwd = new Mf(streams), bwd = new Mb(streams), lens = new Array(nExp);
  for (let i = 0; i < nExp; i++) {
    const e = exps[i];
    lens[i] = (2 ** e) + (i % 2 === 0 ? fwd.read(e) : bwd.read(e));
  }
  if (fwd.overrun() || bwd.overrun()) lzBad('sliced container: length streams overrun');
  const cursors = new Array(nIn).fill(0), outs = [];
  let ci = 0, cl = 0;
  for (let i = 0; i < nOut; i++) {
    const parts = [];
    let size = 0;
    for (;;) {
      if (ci >= index.length) lzBad('sliced container: index list ended');
      const s = index[ci++];
      if (s === 0) break;
      if (s > nIn) lzBad('sliced container: source index out of range');
      if (cl >= lens.length) lzBad('sliced container: length list ended');
      const len = lens[cl++], c = cursors[s - 1], from = sources[s - 1];
      if (len > from.length - c) lzBad('sliced container: interval beyond its source');
      parts.push(from.subarray(c, c + len));
      size += len;
      cursors[s - 1] = c + len;
    }
    if (combined) cl++;
    const o = new Uint8Array(size);
    let at = 0;
    for (const p of parts) { o.set(p, at); at += p.length; }
    outs.push(o);
  }
  if (ci !== index.length || cl !== nExp) lzBad('sliced container: unused intervals');
  if (cursors.some((c, i) => c !== sources[i].length)) lzBad('sliced container: source not fully used');
  return [outs, pos];
}

// ------------------------------------------------------------------ one LZ sub-chunk
// offsets and lengths, from the two bit streams after the last array of the sub-chunk
function lzSide(src, oc, ox, scale, lc) {
  if (!src.length) lzBad('truncated');
  const fwd = new Mf(src), bwd = new Mb(src);
  const z = bwd.zeros();
  if (z < 0 || z > 10) lzBad('long-length count');
  bwd.consume(z);
  const nLong = bwd.read(z + 1) - 1;
  if (nLong > 512) lzBad('too many long lengths');
  const offsets = new Array(oc.length);
  for (let i = 0; i < oc.length; i++) {
    const c = oc[i], r = i % 2 === 0 ? fwd : bwd;
    let dist;
    if (scale === 0) {
      if (c < 0xF0) {
        const n = (c >> 4) + 4, m = (2 ** n) + r.read(n);
        dist = m * 16 + (c & 15) - 248;
      } else {
        const n = c - 0xF0 + 4, m = (2 ** n) + r.read(n), low = r.read(12);
        dist = 8322816 + m * 4096 + low;
      }
    } else {
      const nb = c >> 3;
      if (nb > 26) lzBad('scaled offset: too many bits');
      const od = (8 + (c & 7)) * (2 ** nb) + r.read(nb) - 8;
      if (scale === 1) dist = od;
      else {
        if (!ox || i >= ox.length) lzBad('offset extras');
        dist = od * scale + ox[i];
      }
      if (dist === 0) lzBad('scaled offset: zero distance');
    }
    offsets[i] = dist;
  }
  const longs = new Array(nLong);
  for (let i = 0; i < nLong; i++) {
    const r = i % 2 === 0 ? fwd : bwd, y = r.zeros();
    if (y < 0 || y > 12) lzBad('long length code');
    r.consume(y);
    longs[i] = r.read(y + 7) - 64;
  }
  if (fwd.overrun() || bwd.overrun() || fwd.bytePos() + bwd.bytePos() !== src.length) lzBad('offset/length streams not exactly consumed');
  const lens = new Array(lc.length);
  let li = 0;
  for (let i = 0; i < lc.length; i++) {
    const b = lc[i];
    if (b === 255) {
      if (li >= longs.length) lzBad('long lengths exhausted');
      lens[i] = longs[li++] + 255 + 3;
    } else lens[i] = b + 3;
  }
  if (li !== longs.length) lzBad('unused long lengths');
  return { offsets, lens };
}

function lzCopy(out, p, dist, len, base, limit) {
  if (p < base || dist === 0 || dist > p - base) lzBad('match reaches before the window');
  if (len > limit - p) lzBad('match runs past the end of its sub-chunk');
  if (dist < 8 && len > dist) lzBad('overlapping match with distance below 8');
  if (dist >= len && len > 32) out.copyWithin(p, p - dist, p - dist + len);
  else for (let i = 0; i < len; i++) out[p + i] = out[p + i - dist];
}

// literals: modes 0 delta, 1 raw, 2 delta with a first array, 3 and 5 delta over 4 and 16 arrays, 4 by previous byte
function lzLiterals(mode, arrays, out, start, base, end) {
  const cur = new Array(arrays.length).fill(0);
  const take = i => {
    if (cur[i] >= arrays[i].length) lzBad('literal array exhausted');
    return arrays[i][cur[i]++];
  };
  const reach = (p, dist) => { if (dist === 0 || p < base || dist > p - base) lzBad('delta literal reaches before the window'); };
  return {
    run(p, n, dist) {
      if (n === 0) return;
      if ((mode === 2 || mode === 3 || mode === 5) && dist < 8 && n > dist) lzBad('delta literal run longer than a short distance');
      if (n > end - p) lzBad('literal run past the sub-chunk');
      if (mode === 1) {
        if (n > arrays[0].length - cur[0]) lzBad('literal run beyond its array');
        out.set(arrays[0].subarray(cur[0], cur[0] + n), p);
        cur[0] += n;
      } else if (mode === 0 || mode === 2) {
        let q = p;
        if (mode === 2) {
          reach(p, dist);
          out[q] = take(1) + out[q - dist];
          q++;
        }
        const left = p + n - q;
        if (!left) return;
        if (left > arrays[0].length - cur[0]) lzBad('literal run beyond its array');
        if (dist < 8 && left > dist) lzBad('delta literal run longer than a short distance');
        reach(q, dist);
        const a = arrays[0];
        for (let i = 0, c = cur[0]; i < left; i++) out[q + i] = a[c + i] + out[q + i - dist];
        cur[0] += left;
      } else if (mode === 3 || mode === 5) {
        reach(p, dist);
        const m = mode === 3 ? 4 : 16;
        for (let q = p; q < p + n; q++) out[q] = take((q - start) % m) + out[q - dist];
      } else {
        if (p === 0) lzBad('no previous byte');
        for (let q = p; q < p + n; q++) out[q] = take(out[q - 1] >> 4);
      }
    },
    allUsed: () => arrays.every((a, i) => a.length === cur[i]),
  };
}

function lzSubChunk(body, mode, out, base, start, end) {
  if (mode > 5) lzBad('invalid mode');
  const subLen = end - start;
  let pos = 0;
  if (start === base) {  // the window starts with eight raw bytes
    if (subLen < 8) lzBad('sub-chunk too short for its eight raw bytes');
    if (body.length < 8) lzBad('truncated');
    out.set(body.subarray(0, 8), start);
    pos = 8;
  }
  let p = start + pos;
  if (pos >= body.length) lzBad('truncated');
  const x = body[pos];
  let scale = 0;
  if (x & 0x80) { pos++; scale = x - 127; }
  const third = Math.floor(subLen / 3);
  let [oc, n] = lzArray(body.subarray(pos), third, 0);
  pos += n;
  let ox = null;
  if (scale >= 2) {
    [ox, n] = lzArray(body.subarray(pos), third, 0);
    pos += n;
    if (ox.length !== oc.length) lzBad('offset extras length');
  }
  let lc;
  [lc, n] = lzArray(body.subarray(pos), Math.floor(subLen / 5), 0);
  pos += n;

  let arrays;
  if (mode < 2) {
    const [a, used] = lzArray(body.subarray(pos), subLen, 0);
    pos += used;
    arrays = [a];
  } else {
    const [v, used] = lzSliced(body.subarray(pos), mode === 2 ? 2 : mode === 3 ? 4 : 16, subLen, 0);
    pos += used;
    arrays = v;
  }
  const lits = lzLiterals(mode, arrays, out, start, base, end);

  if (pos >= body.length) lzBad('truncated');
  const first = body[pos];
  let lanes;
  if (!(first & 0x80)) {
    const [a, used] = lzArray(body.subarray(pos), subLen, 0);
    pos += used;
    lanes = [a];
  } else {
    if (first !== 0x83) lzBad('bad command lane marker');
    pos++;
    const [v, used] = lzSliced(body.subarray(pos), 8, subLen, 0);
    pos += used;
    lanes = v;
  }
  const { offsets, lens } = lzSide(body.subarray(pos), oc, ox, scale, lc);

  let total = 0;
  for (const l of lanes) total += l.length;
  const eight = lanes.length === 8, laneCur = [0, 0, 0, 0, 0, 0, 0, 0];
  const recent = [8, 8, 8, 8, 8, 8, 8];
  let lo = 8, offCur = 0, front = 0, back = lens.length;
  for (let k = 0; k < total; k++) {
    let cmd;
    if (eight) {
      const lane = (p - start) & 7;
      if (laneCur[lane] >= lanes[lane].length) lzBad('command lane exhausted');
      cmd = lanes[lane][laneCur[lane]++];
    } else cmd = lanes[0][k];
    const oidx = cmd >> 5, litc = (cmd >> 3) & 3, mlc = cmd & 7;
    let litN = litc;
    if (litc === 3) {
      if (front >= back) lzBad('lengths exhausted');
      litN = lens[front++];
    }
    lits.run(p, litN, lo);
    p += litN;
    let dist;
    if (oidx === 7) {
      if (offCur >= offsets.length) lzBad('offsets exhausted');
      dist = offsets[offCur++];
      recent.pop();
      recent.unshift(dist);
    } else {
      dist = recent[oidx];
      recent.copyWithin(1, 0, oidx);
      recent[0] = dist;
    }
    lo = dist;
    let mlen = mlc + 2;
    if (mlc === 7) {
      if (front >= back) lzBad('lengths exhausted');
      mlen = lens[--back] + 6;
    }
    lzCopy(out, p, dist, mlen, base, end);
    p += mlen;
  }
  lits.run(p, end - p, lo);
  if (!lits.allUsed()) lzBad('unused literals');
  if (offCur !== offsets.length) lzBad('unused offsets');
  if (front !== back) lzBad('unused lengths');
}

function lzPayload(payload, out, blockStart, left, base) {
  let q = 0, d = 0;
  while (d < left) {
    const subLen = Math.min(left - d, LZ_SUB);
    if (payload.length - q < 4) lzBad('truncated');
    const h = payload[q] << 16 | payload[q + 1] << 8 | payload[q + 2], start = blockStart + d;
    if (!(h & 0x800000)) {
      const [arr, used] = lzArray(payload.subarray(q), subLen, 0);
      if (arr.length !== subLen) lzBad('entropy sub-chunk has the wrong size');
      out.set(arr, start);
      q += used;
    } else {
      const mode = (h >> 19) & 15, n = h & 0x7FFFF;
      if (q + 3 + n > payload.length) lzBad('truncated');
      const body = payload.subarray(q + 3, q + 3 + n);
      if (n < subLen) lzSubChunk(body, mode, out, base, start, start + subLen);
      else if (n === subLen && mode === 0) out.set(body, start);
      else lzBad('bad sub-chunk header');
      q += 3 + n;
    }
    d += subLen;
  }
  if (q !== payload.length) lzBad('quantum payload not exactly consumed');
}

// the whole stream: rawSize bytes out
function lzDecode(src, rawSize) {
  const out = new Uint8Array(rawSize);
  let ip = 0, produced = 0, base = 0;
  while (produced < rawSize) {
    const left = Math.min(rawSize - produced, LZ_BLOCK);
    if (ip + 2 > src.length) lzBad('truncated');
    const b0 = src[ip], b1 = src[ip + 1];
    ip += 2;
    if ((b0 & 0x0F) !== 0x0C || (b0 & 0x30) !== 0) lzBad('bad block header');
    if (b1 & 0x80) lzBad('checksummed blocks are not supported');
    if ((b1 & 0x7F) !== 0x0C) lzBad('only the block format of the game\'s models is supported');
    if (b0 & 0x80) base = produced;
    if (b0 & 0x40) {
      if (ip + left > src.length) lzBad('truncated');
      out.set(src.subarray(ip, ip + left), produced);
      ip += left;
      produced += left;
      continue;
    }
    if (ip + 3 > src.length) lzBad('truncated');
    const v = src[ip] << 16 | src[ip + 1] << 8 | src[ip + 2], size = v & 0x3FFFF;
    ip += 3;
    if (size !== 0x3FFFF) {
      if (ip + size + 1 > src.length) lzBad('truncated');
      lzPayload(src.subarray(ip, ip + size + 1), out, produced, left, base);
      ip += size + 1;
    } else if (v >> 18 === 1) {
      if (ip >= src.length) lzBad('truncated');
      out.fill(src[ip++], produced, produced + left);
    } else lzBad('bad quantum header');
    produced += left;
  }
  return out;
}

if (typeof module !== 'undefined') module.exports = { lzDecode };
