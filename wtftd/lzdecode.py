"""WTFTD - decoder for the block-compressed streams of the game's files (map textures, heightmaps): LZ77 with Huffman,
tANS and run-length coding, the block format known as Leviathan. Python port of web/lzdecode.js, itself a plain
JavaScript port of lztans, so no Oodle runtime is needed:

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
   SOFTWARE.
"""
from __future__ import annotations

LZ_BLOCK, LZ_SUB, LZ_DEPTH, HUFF_LEN, HUFF_SIZE = 262144, 131072, 24, 11, 2048
PAD = bytes(8)
REV11 = [int(f"{i:011b}"[::-1], 2) for i in range(HUFF_SIZE)]


class LzError(ValueError):
    pass


def bad(what: str):
    raise LzError("lz: " + what)


# ------------------------------------------------------------------ bit readers: bytes past the region read as zero
class Mf:
    """Most significant bit first, forward."""
    __slots__ = ("d", "n", "bit")

    def __init__(self, d):
        self.n, self.d, self.bit = len(d), bytes(d) + PAD, 0

    def peek(self, k: int) -> int:
        i = self.bit >> 3
        if not k or i >= self.n:
            return 0
        return ((int.from_bytes(self.d[i:i + 5], "big") << (self.bit & 7) >> 8) & 0xFFFFFFFF) >> (32 - k)

    def consume(self, k: int):
        self.bit += k

    def read(self, k: int) -> int:
        v = self.peek(k)
        self.bit += k
        return v

    def zeros(self) -> int:
        w = self.peek(32)
        return 32 - w.bit_length() if w else -1

    def byte_pos(self) -> int:
        return (self.bit + 7) >> 3

    def overrun(self) -> bool:
        return self.bit > self.n * 8


def Mb(d) -> Mf:
    """Most significant bit first, from the last byte backward: the forward reader of the reversed bytes."""
    return Mf(bytes(d)[::-1])


# least significant bit first, forward: the backward streams are read as reversed copies (lbBits of the JS)
def lf(d: bytes, p: int) -> int:
    i = p >> 3
    return (d[i] | d[i + 1] << 8 | d[i + 2] << 16) >> (p & 7)


# ------------------------------------------------------------------ code tables
def zigzag(v: int) -> int:
    return (v >> 1) ^ -(v & 1)


def read_unary(r: Mf) -> int:
    total = 0
    while True:
        z = r.zeros()
        if z >= 0:
            r.consume(z + 1)
            total += z
            if total >= 4096:
                bad("unary count too large")
            return total
        r.consume(32)
        total += 32
        if total >= 4096:
            bad("unary count too large")


def read_truncated(r: Mf, x: int) -> int:
    y = (x - 1).bit_length()
    u, v = (1 << y) - x, r.peek(y)
    if (v >> 1) >= u:
        r.consume(y)
        return v - u
    r.consume(y - 1)
    return v >> 1


def read_ranges(r: Mf, ns: int, extras: list) -> list:
    """The coded symbols in ascending order, ns of them."""
    syms, sym, used, j, x = [], 0, 0, 0, len(extras)
    if x % 2 == 1:
        v, j = extras[0], 1
        if v >= 8:
            bad("symbol range: initial gap")
        sym = r.read(v + 1) + (1 << (v + 1)) - 1
    for _ in range(x >> 1):
        v1 = extras[j]
        j += 1
        if v1 >= 9:
            bad("symbol range: count")
        count = r.read(v1) + (1 << v1)
        v2 = extras[j]
        j += 1
        if v2 >= 8:
            bad("symbol range: gap")
        gap = r.read(v2 + 1) + (1 << (v2 + 1)) - 1
        if sym + count > 256:
            bad("symbol range beyond 255")
        syms.extend(range(sym, sym + count))
        used += count
        sym += count + gap
    if sym >= 256 or used >= ns or sym + (ns - used) > 256:
        bad("symbol range: inconsistent")
    syms.extend(range(sym, sym + (ns - used)))
    return syms


def huff_lz(r: Mf) -> int:
    z = r.zeros()
    if z < 0:
        bad("too many leading zero bits")
    return z


def read_gamma(r: Mf) -> int:
    if r.peek(8) == 0:
        bad("gamma code starts with eight zero bits")
    z = huff_lz(r)
    r.consume(z + 1)
    return (1 << (z + 1)) + r.read(z + 1) - 1


def huff_new(r: Mf, lists: list):
    k, ns = r.read(2), r.read(8) + 1
    xcount = 0 if ns == 256 else read_truncated(r, 2 * min(257 - ns, ns))
    u = []
    for _ in range(ns + xcount):
        v = read_unary(r)
        if v >= 256:
            bad("huffman: unary count")
        u.append(v)
    c, extras, lens = u[:ns], u[ns:], []
    if k > 0:
        c = [ci << k | r.read(k) for ci in c]
    run = 30
    for ci in c:
        d = zigzag(ci)
        n = d + (run >> 2) + 1
        if n < 1 or n > HUFF_LEN:
            bad("huffman: code length")
        lens.append(n)
        run += d
    for i, s in enumerate(read_ranges(r, ns, extras)):
        lists[lens[i]].append(s)


def huff_sparse(r: Mf, lists: list):
    ns = r.read(8)
    if ns < 2:
        bad("huffman: sparse description too short")
    cb = r.read(3)
    if cb > 4:
        bad("huffman: sparse length width")
    for _ in range(ns):
        s, n = r.read(8), r.read(cb) + 1
        if n > HUFF_LEN:
            bad("huffman: sparse code length")
        lists[n].append(s)


def huff_dense(r: Mf, lists: list):
    k = r.read(2)
    zmax, skip, sym, coded, mean4 = 20 >> k, r.read(1) == 1, 0, 0, 32
    while sym < 256:
        if skip:
            skip = False
        else:
            sym += read_gamma(r)
            if sym >= 256:
                break
        n = read_gamma(r)
        if sym + n > 256:
            bad("huffman: dense group beyond 255")
        coded += n
        for _ in range(n):
            z = huff_lz(r)
            if z > zmax:
                bad("huffman: dense code too long")
            r.consume(z + 1)
            f = r.read(k)
            ln = zigzag(z << k | f) + ((mean4 + 2) >> 2)
            if ln < 1 or ln > HUFF_LEN:
                bad("huffman: dense code length")
            mean4 = ln + ((3 * mean4 + 2) >> 2)
            lists[ln].append(sym)
            sym += 1
    if sym != 256 or coded < 2:
        bad("huffman: dense description inconsistent")


def huff_table(r: Mf) -> tuple[list, list]:
    """-> (symbol, code length) by the next 11 bits, least significant first."""
    lists = [[] for _ in range(HUFF_LEN + 1)]
    if r.read(1) == 1:
        if r.read(1) != 0:
            bad("huffman: description selector")
        huff_new(r, lists)
    elif r.read(1) == 1:
        huff_dense(r, lists)
    else:
        huff_sparse(r, lists)
    if r.overrun():
        bad("huffman: description runs past the array")
    sym, ln = [0] * HUFF_SIZE, [0] * HUFF_SIZE
    slot = 0
    for n in range(1, HUFF_LEN + 1):
        width = 1 << (HUFF_LEN - n)
        for s in lists[n]:
            if slot + width > HUFF_SIZE:
                bad("huffman: code space overfull")
            for sl in range(slot, slot + width):
                sym[REV11[sl]], ln[REV11[sl]] = s, n
            slot += width
    if slot != HUFF_SIZE:
        bad("huffman: code space not full")
    return sym, ln


def huff_three(region, out: bytearray, start: int, end: int, sym: list, ln: list):
    """Three bit streams, one symbol from each in turn: region starts with the length of the first one."""
    if len(region) < 2:
        bad("huffman: payload too short")
    m = region[0] | region[1] << 8
    if 2 + m > len(region):
        bad("huffman: stream length")
    a, bc = bytes(region[2:2 + m]) + PAD, bytes(region[2 + m:])
    n = len(bc)
    b, c = bc + PAD, bc[::-1] + PAD
    pa = pb = pc = 0
    o, whole = start, end - (end - start) % 3
    while o < whole:
        i = pa >> 3
        x = (a[i] | a[i + 1] << 8 | a[i + 2] << 16) >> (pa & 7) & 2047
        out[o] = sym[x]
        pa += ln[x]
        i = pc >> 3
        x = (c[i] | c[i + 1] << 8 | c[i + 2] << 16) >> (pc & 7) & 2047
        out[o + 1] = sym[x]
        pc += ln[x]
        i = pb >> 3
        x = (b[i] | b[i + 1] << 8 | b[i + 2] << 16) >> (pb & 7) & 2047
        out[o + 2] = sym[x]
        pb += ln[x]
        o += 3
    if o < end:
        x = lf(a, pa) & 2047
        out[o] = sym[x]
        pa += ln[x]
        if o + 1 < end:
            x = lf(c, pc) & 2047
            out[o + 1] = sym[x]
            pc += ln[x]
    if (pa + 7) >> 3 != m or ((pb + 7) >> 3) + ((pc + 7) >> 3) != n:
        bad("huffman: bit streams not exactly consumed")


def huff_decode(body, out_len: int, six: bool) -> bytearray:
    r = Mf(body)
    sym, ln = huff_table(r)
    rest, out = body[min(r.byte_pos(), len(body)):], bytearray(out_len)
    if not six:
        huff_three(rest, out, 0, out_len, sym, ln)
        return out
    if len(rest) < 3:
        bad("huffman: payload too short")
    m = rest[0] | rest[1] << 8 | rest[2] << 16
    if m > len(rest) - 3:
        bad("huffman: six-stream split")
    half = (out_len + 1) // 2
    huff_three(rest[3:3 + m], out, 0, half, sym, ln)
    huff_three(rest[3 + m:], out, half, out_len, sym, ln)
    return out


def rle_decode(body, out_len: int, depth: int) -> bytearray:
    if not len(body):
        bad("rle: empty body")
    if len(body) == 1:
        return bytearray(bytes(body[0:1]) * out_len)
    w = bytes(body[1:])
    if body[0] != 0:
        arr, n = lz_array(body, out_len, depth + 1)
        w = bytes(arr) + bytes(body[n:])
    out = bytearray(out_len)
    lit, end, fill, o = 0, len(w), 0, 0
    while lit < end:
        cmd = w[end - 1]
        if cmd == 0 or cmd > 0x2F:
            end -= 1
            copy, run = ~cmd & 15, cmd >> 4
        elif cmd == 1:
            end -= 1
            if lit >= end:
                bad("rle: missing literal for run byte")
            fill = w[lit]
            lit += 1
            continue
        else:
            if end - lit < 2:
                bad("rle: truncated command")
            v = cmd << 8 | w[end - 2]
            end -= 2
            if cmd >= 0x10:
                copy, run = (v - 4096) & 63, (v - 4096) >> 6
            elif cmd >= 9:
                copy, run = 0, (v - 0x8FF) * 128
            else:
                copy, run = (v - 511) * 64, 0
        if copy > end - lit:
            bad("rle: literal count beyond the data")
        if copy + run > out_len - o:
            bad("rle: output overrun")
        out[o:o + copy] = w[lit:lit + copy]
        lit += copy
        o += copy
        out[o:o + run] = bytes((fill,)) * run
        o += run
    if o != out_len:
        bad("rle: output size mismatch")
    return out


def tans_weights(r: Mf) -> tuple[int, list]:
    if r.read(1) != 0:
        bad("tans: reserved bit set")
    tb = r.read(2) + 8
    size, golomb, out = 1 << tb, r.read(1) == 1, []
    if golomb:
        q, ns = r.read(3), r.read(8) + 1
        if ns < 2:
            bad("tans: fewer than two symbols")
        xcount = 0 if ns == 256 else read_truncated(r, 2 * min(257 - ns, ns))
        u = [read_unary(r) for _ in range(ns + xcount)]
        codes, syms = u[:ns], read_ranges(r, ns, u[ns:])
        mean, total = 6, 0
        for i, s in enumerate(syms):
            w_bits = codes[i] + q
            if w_bits > 15:
                bad("tans: weight width")
            v = r.read(w_bits) + (1 << w_bits) - (1 << q)
            a4 = mean >> 2
            limit = 2 * a4
            if v <= limit:
                v = a4 + zigzag(v)
            if limit > v:
                limit = v
            w = v + 1
            if w < 1:
                bad("tans: weight below one")
            mean += limit - a4
            total += w
            if total > size:
                bad("tans: weights exceed table size")
            out.append((s, w))
        if total != size:
            bad("tans: weights do not fill the table")
    else:
        count, bps = r.read(3) + 1, tb.bit_length()
        mdb = r.read(bps)
        if mdb < 1 or mdb > tb:
            bad("tans: sparse weight width")
        seen, weight, total = set(), 0, 0
        for _ in range(count):
            s = r.read(8)
            if s in seen:
                bad("tans: repeated symbol")
            seen.add(s)
            weight += r.read(mdb)
            if weight == 0:
                bad("tans: zero weight")
            total += weight
            if total >= size:
                bad("tans: weights exceed table size")
            out.append((s, weight))
        s = r.read(8)
        if s in seen:
            bad("tans: repeated symbol")
        last = size - total
        if last < weight or last <= 1:
            bad("tans: last weight")
        out.append((s, last))
        out.sort(key=lambda e: e[0])
    if r.overrun():
        bad("tans: table runs past the array")
    return tb, out


def tans_table(tb: int, weights: list) -> tuple[list, list, list]:
    size = 1 << tb
    mask = size - 1
    singles = [s for s, w in weights if w == 1]
    states = size - len(singles)
    symbol, nbits, base = [0] * size, [0] * size, [0] * size
    for i, s in enumerate(singles):
        symbol[states + i], nbits[states + i] = s, tb
    a, rem = states // 4, states % 4
    cursor, ends, acc = [0] * 4, [0] * 4, 0
    for j in range(4):
        cursor[j] = acc
        acc += a + (1 if j < rem else 0)
        ends[j] = acc
    p = 0
    for sym, w in weights:
        if w <= 1:
            continue
        k = 0
        for j in range(4):
            off = (j + 4 - (p % 4)) % 4
            for _ in range((w - off + 3) // 4 if w > off else 0):
                if cursor[j] >= ends[j]:
                    bad("tans: region overflow")
                wv = w + k
                nb = tb - (wv.bit_length() - 1)
                at = cursor[j]
                cursor[j] += 1
                symbol[at], nbits[at], base[at] = sym, nb, (wv << nb) & mask
                k += 1
        p += w
    return symbol, nbits, base


def tans_decode(body, out_len: int) -> bytearray:
    if out_len < 5 or len(body) < 8:
        bad("tans: array too small")
    r = Mf(body)
    tb, weights = tans_weights(r)
    symbol, nbits, base = tans_table(tb, weights)
    start = r.byte_pos()
    if start >= len(body):
        bad("tans: no payload")
    payload = bytes(body[start:])
    n, tmask = len(payload), (1 << tb) - 1
    f, g = payload + PAD, payload[::-1] + PAD  # forward stream, backward stream
    masks = [(1 << i) - 1 for i in range(33)]
    pf = pb = 0
    st = [0] * 5
    st[0] = lf(f, pf) & tmask
    pf += tb
    st[1] = lf(g, pb) & tmask
    pb += tb
    st[2] = lf(f, pf) & tmask
    pf += tb
    st[3] = lf(g, pb) & tmask
    pb += tb
    st[4] = lf(f, pf) & tmask
    pf += tb
    out, main = bytearray(out_len), out_len - 5
    for i in range(main):
        j = i % 5
        s = st[j]
        nb = nbits[s]
        out[i] = symbol[s]
        if (i // 5) & 1 == 0:  # the groups of five alternate between the two streams
            x = pf >> 3
            st[j] = base[s] + (((f[x] | f[x + 1] << 8 | f[x + 2] << 16) >> (pf & 7)) & masks[nb])
            pf += nb
        else:
            x = pb >> 3
            st[j] = base[s] + (((g[x] | g[x + 1] << 8 | g[x + 2] << 16) >> (pb & 7)) & masks[nb])
            pb += nb
    for k, s in enumerate(st):
        if s > 255:
            bad("tans: final state is not a byte")
        out[main + k] = s
    if start + ((pf + 7) >> 3) != len(body) - ((pb + 7) >> 3):
        bad("tans: bit streams not exactly consumed")
    return out


# ------------------------------------------------------------------ byte arrays
def lz_array(src, limit: int, depth: int):
    """One array from the start of src -> (bytes, input bytes used)."""
    if depth > LZ_DEPTH:
        bad("arrays nested too deeply")
    if not len(src):
        bad("truncated")
    h0 = src[0]
    ty = (h0 >> 4) & 7
    if ty == 0:
        if h0 >= 0x80:
            if len(src) < 2:
                bad("truncated")
            size, off = (h0 << 8 | src[1]) & 0x0FFF, 2
        else:
            if len(src) < 3:
                bad("truncated")
            v = h0 << 16 | src[1] << 8 | src[2]
            if v >> 18:
                bad("stored array: size")
            size, off = v, 3
        if size > limit:
            bad("array larger than its limit")
        if off + size > len(src):
            bad("truncated")
        return src[off:off + size], off + size
    if ty > 5:
        bad("invalid array type")
    if h0 >= 0x80:
        if len(src) < 3:
            bad("truncated")
        b = h0 << 16 | src[1] << 8 | src[2]
        body_len = b & 0x3FF
        out_len, hdr = body_len + ((b >> 10) & 0x3FF) + 1, 3
    else:
        if len(src) < 5:
            bad("truncated")
        c = src[1] << 24 | src[2] << 16 | src[3] << 8 | src[4]
        body_len = c & 0x3FFFF
        out_len = ((h0 & 0x0F) * 16384 + c // 262144) + 1
        if body_len >= out_len:
            bad("array: source size not below decoded size")
        hdr = 5
    if out_len > limit:
        bad("array larger than its limit")
    if hdr + body_len > len(src):
        bad("truncated")
    body = src[hdr:hdr + body_len]
    data = (tans_decode(body, out_len) if ty == 1 else huff_decode(body, out_len, False) if ty == 2
            else rle_decode(body, out_len, depth) if ty == 3 else huff_decode(body, out_len, True) if ty == 4
            else lz_concat(body, out_len, depth))
    return data, hdr + body_len


def lz_concat(body, out_len: int, depth: int):
    if not len(body):
        bad("truncated")
    b = body[0]
    n = b & 0x7F
    if n < 2 or len(body) < 6:
        bad("concatenated array: too small")
    if b & 0x80:
        outs, used = lz_sliced(body, 1, out_len, depth)
        if len(outs[0]) != out_len or used != len(body):
            bad("sliced container: size mismatch")
        return outs[0]
    out, pos, o = bytearray(out_len), 1, 0
    for _ in range(n):
        a, used = lz_array(body[pos:], out_len - o, depth + 1)
        out[o:o + len(a)] = a
        o += len(a)
        pos += used
    if o != out_len or pos != len(body):
        bad("concatenated array: size mismatch")
    return out


def lz_sliced(src, n_out: int, limit: int, depth: int):
    """The multi-array container of type-5 arrays and of literals and commands -> (arrays, input bytes used)."""
    if len(src) < 4:
        bad("truncated")
    b = src[0]
    if not b & 0x80:
        bad("sliced container: count byte")
    n_in, pos = b & 0x3F, 1
    if n_in == 0:
        outs, left = [], limit
        for _ in range(n_out):
            a, n = lz_array(src[pos:], left, depth + 1)
            left -= len(a)
            pos += n
            outs.append(a)
        return outs, pos
    sources, total = [], 0
    for _ in range(n_in):
        a, n = lz_array(src[pos:], limit - total, depth + 1)
        total += len(a)
        pos += n
        sources.append(a)
    if len(src) < pos + 2:
        bad("truncated")
    q = src[pos] | src[pos + 1] << 8
    pos += 2
    vb, combined = q & 0x3FFF, bool(q & 0x8000)
    if combined:
        a, n = lz_array(src[pos:], total, depth + 1)
        pos += n
        index, exps = [t & 15 for t in a], [t >> 4 for t in a]
        n_exp = len(index)
    else:
        a, n = lz_array(src[pos:], total, depth + 1)
        pos += n
        if len(a) < n_out:
            bad("sliced container: fewer intervals than arrays")
        n_exp = len(a) - n_out
        e, n2 = lz_array(src[pos:], n_exp, depth + 1)
        pos += n2
        if len(e) != n_exp:
            bad("sliced container: exponent count")
        if any(x > 16 for x in e):
            bad("sliced container: exponent above 16")
        index, exps = list(a), list(e)
    if len(index) > total:
        bad("sliced container: too many intervals")
    if vb > len(src) - pos:
        bad("truncated")
    streams = src[pos:pos + vb]
    pos += vb
    if not index or index[-1] != 0:
        bad("sliced container: last index is not zero")
    fwd, bwd = Mf(streams), Mb(streams)
    lens = [(1 << exps[i]) + (fwd.read(exps[i]) if i % 2 == 0 else bwd.read(exps[i])) for i in range(n_exp)]
    if fwd.overrun() or bwd.overrun():
        bad("sliced container: length streams overrun")
    cursors, outs, ci, cl = [0] * n_in, [], 0, 0
    for _ in range(n_out):
        parts = []
        while True:
            if ci >= len(index):
                bad("sliced container: index list ended")
            s = index[ci]
            ci += 1
            if s == 0:
                break
            if s > n_in:
                bad("sliced container: source index out of range")
            if cl >= len(lens):
                bad("sliced container: length list ended")
            ln, c, frm = lens[cl], cursors[s - 1], sources[s - 1]
            cl += 1
            if ln > len(frm) - c:
                bad("sliced container: interval beyond its source")
            parts.append(bytes(frm[c:c + ln]))
            cursors[s - 1] = c + ln
        if combined:
            cl += 1
        outs.append(b"".join(parts))
    if ci != len(index) or cl != n_exp:
        bad("sliced container: unused intervals")
    if any(c != len(sources[i]) for i, c in enumerate(cursors)):
        bad("sliced container: source not fully used")
    return outs, pos


# ------------------------------------------------------------------ one LZ sub-chunk
def lz_side(src, oc, ox, scale: int, lc):
    """Offsets and lengths, from the two bit streams after the last array of the sub-chunk."""
    if not len(src):
        bad("truncated")
    fwd, bwd = Mf(src), Mb(src)
    z = bwd.zeros()
    if z < 0 or z > 10:
        bad("long-length count")
    bwd.consume(z)
    n_long = bwd.read(z + 1) - 1
    if n_long > 512:
        bad("too many long lengths")
    offsets = [0] * len(oc)
    for i, c in enumerate(oc):
        r = fwd if i % 2 == 0 else bwd
        if scale == 0:
            if c < 0xF0:
                n = (c >> 4) + 4
                dist = ((1 << n) + r.read(n)) * 16 + (c & 15) - 248
            else:
                n = c - 0xF0 + 4
                m = (1 << n) + r.read(n)
                dist = 8322816 + m * 4096 + r.read(12)
        else:
            nb = c >> 3
            if nb > 26:
                bad("scaled offset: too many bits")
            od = (8 + (c & 7)) * (1 << nb) + r.read(nb) - 8
            if scale == 1:
                dist = od
            else:
                if ox is None or i >= len(ox):
                    bad("offset extras")
                dist = od * scale + ox[i]
            if dist == 0:
                bad("scaled offset: zero distance")
        offsets[i] = dist
    longs = []
    for i in range(n_long):
        r = fwd if i % 2 == 0 else bwd
        y = r.zeros()
        if y < 0 or y > 12:
            bad("long length code")
        r.consume(y)
        longs.append(r.read(y + 7) - 64)
    if fwd.overrun() or bwd.overrun() or fwd.byte_pos() + bwd.byte_pos() != len(src):
        bad("offset/length streams not exactly consumed")
    lens, li = [0] * len(lc), 0
    for i, b in enumerate(lc):
        if b == 255:
            if li >= len(longs):
                bad("long lengths exhausted")
            lens[i] = longs[li] + 255 + 3
            li += 1
        else:
            lens[i] = b + 3
    if li != len(longs):
        bad("unused long lengths")
    return offsets, lens


def add_bytes(x: bytes, y: bytes) -> bytes:
    """Byte by byte (x + y) & 255, carries kept inside each byte."""
    n = len(x)
    lo, hi = int.from_bytes(b"\x7f" * n, "big"), int.from_bytes(b"\x80" * n, "big")
    a, b = int.from_bytes(x, "big"), int.from_bytes(y, "big")
    return (((a & lo) + (b & lo)) ^ ((a ^ b) & hi)).to_bytes(n, "big")


class Literals:
    """Modes 0 delta, 1 raw, 2 delta with a first array, 3 and 5 delta over 4 and 16 arrays, 4 by previous byte."""
    __slots__ = ("mode", "arrays", "cur", "out", "start", "base", "end")

    def __init__(self, mode, arrays, out, start, base, end):
        self.mode, self.arrays, self.cur = mode, [bytes(a) for a in arrays], [0] * len(arrays)
        self.out, self.start, self.base, self.end = out, start, base, end

    def take(self, i: int) -> int:
        c = self.cur[i]
        if c >= len(self.arrays[i]):
            bad("literal array exhausted")
        self.cur[i] = c + 1
        return self.arrays[i][c]

    def reach(self, p: int, dist: int):
        if dist == 0 or p < self.base or dist > p - self.base:
            bad("delta literal reaches before the window")

    def run(self, p: int, n: int, dist: int):
        if n == 0:
            return
        mode, out = self.mode, self.out
        if mode in (2, 3, 5) and dist < 8 and n > dist:
            bad("delta literal run longer than a short distance")
        if n > self.end - p:
            bad("literal run past the sub-chunk")
        if mode == 1:
            a, c = self.arrays[0], self.cur[0]
            if n > len(a) - c:
                bad("literal run beyond its array")
            out[p:p + n] = a[c:c + n]
            self.cur[0] = c + n
        elif mode in (0, 2):
            q = p
            if mode == 2:
                self.reach(p, dist)
                out[q] = (self.take(1) + out[q - dist]) & 255
                q += 1
            left = p + n - q
            if not left:
                return
            a, c = self.arrays[0], self.cur[0]
            if left > len(a) - c:
                bad("literal run beyond its array")
            if dist < 8 and left > dist:
                bad("delta literal run longer than a short distance")
            self.reach(q, dist)
            done = 0
            while done < left:  # by pieces no longer than dist: each one adds bytes already written
                k = min(dist, left - done)
                at = q + done
                out[at:at + k] = add_bytes(a[c + done:c + done + k], bytes(out[at - dist:at - dist + k]))
                done += k
            self.cur[0] = c + left
        elif mode in (3, 5):
            self.reach(p, dist)
            m = 4 if mode == 3 else 16
            for q in range(p, p + n):
                out[q] = (self.take((q - self.start) % m) + out[q - dist]) & 255
        else:
            if p == 0:
                bad("no previous byte")
            for q in range(p, p + n):
                out[q] = self.take(out[q - 1] >> 4)

    def all_used(self) -> bool:
        return all(len(a) == self.cur[i] for i, a in enumerate(self.arrays))


def lz_sub_chunk(body, mode: int, out: bytearray, base: int, start: int, end: int):
    if mode > 5:
        bad("invalid mode")
    sub_len, pos = end - start, 0
    if start == base:  # the window starts with eight raw bytes
        if sub_len < 8:
            bad("sub-chunk too short for its eight raw bytes")
        if len(body) < 8:
            bad("truncated")
        out[start:start + 8] = body[:8]
        pos = 8
    p = start + pos
    if pos >= len(body):
        bad("truncated")
    x, scale = body[pos], 0
    if x & 0x80:
        pos += 1
        scale = x - 127
    third = sub_len // 3
    oc, n = lz_array(body[pos:], third, 0)
    pos += n
    ox = None
    if scale >= 2:
        ox, n = lz_array(body[pos:], third, 0)
        pos += n
        if len(ox) != len(oc):
            bad("offset extras length")
    lc, n = lz_array(body[pos:], sub_len // 5, 0)
    pos += n
    if mode < 2:
        a, used = lz_array(body[pos:], sub_len, 0)
        pos += used
        arrays = [a]
    else:
        arrays, used = lz_sliced(body[pos:], 2 if mode == 2 else 4 if mode == 3 else 16, sub_len, 0)
        pos += used
    lits = Literals(mode, arrays, out, start, base, end)
    if pos >= len(body):
        bad("truncated")
    first = body[pos]
    if not first & 0x80:
        a, used = lz_array(body[pos:], sub_len, 0)
        pos += used
        lanes = [bytes(a)]
    else:
        if first != 0x83:
            bad("bad command lane marker")
        pos += 1
        v, used = lz_sliced(body[pos:], 8, sub_len, 0)
        pos += used
        lanes = [bytes(x) for x in v]
    offsets, lens = lz_side(body[pos:], oc, ox, scale, lc)

    total = sum(len(x) for x in lanes)
    eight, lane_cur = len(lanes) == 8, [0] * 8
    recent = [8] * 7
    lo, off_cur, front, back = 8, 0, 0, len(lens)
    run = lits.run
    cmds = lanes[0]
    for k in range(total):
        if eight:
            lane = (p - start) & 7
            if lane_cur[lane] >= len(lanes[lane]):
                bad("command lane exhausted")
            cmd = lanes[lane][lane_cur[lane]]
            lane_cur[lane] += 1
        else:
            cmd = cmds[k]
        oidx, litc, mlc = cmd >> 5, (cmd >> 3) & 3, cmd & 7
        lit_n = litc
        if litc == 3:
            if front >= back:
                bad("lengths exhausted")
            lit_n = lens[front]
            front += 1
        run(p, lit_n, lo)
        p += lit_n
        if oidx == 7:
            if off_cur >= len(offsets):
                bad("offsets exhausted")
            dist = offsets[off_cur]
            off_cur += 1
            recent.pop()
            recent.insert(0, dist)
        else:
            dist = recent[oidx]
            del recent[oidx]
            recent.insert(0, dist)
        lo = dist
        mlen = mlc + 2
        if mlc == 7:
            if front >= back:
                bad("lengths exhausted")
            back -= 1
            mlen = lens[back] + 6
        # the match: out[p + i] = out[p + i - dist]
        if p < base or dist == 0 or dist > p - base:
            bad("match reaches before the window")
        if mlen > end - p:
            bad("match runs past the end of its sub-chunk")
        if dist >= mlen:
            out[p:p + mlen] = out[p - dist:p - dist + mlen]
        else:
            if dist < 8:
                bad("overlapping match with distance below 8")
            out[p:p + mlen] = (out[p - dist:p] * (mlen // dist + 1))[:mlen]
        p += mlen
    run(p, end - p, lo)
    if not lits.all_used():
        bad("unused literals")
    if off_cur != len(offsets):
        bad("unused offsets")
    if front != back:
        bad("unused lengths")


def lz_payload(payload, out: bytearray, block_start: int, left: int, base: int):
    q = d = 0
    while d < left:
        sub_len = min(left - d, LZ_SUB)
        if len(payload) - q < 4:
            bad("truncated")
        h, start = payload[q] << 16 | payload[q + 1] << 8 | payload[q + 2], block_start + d
        if not h & 0x800000:
            arr, used = lz_array(payload[q:], sub_len, 0)
            if len(arr) != sub_len:
                bad("entropy sub-chunk has the wrong size")
            out[start:start + sub_len] = arr
            q += used
        else:
            mode, n = (h >> 19) & 15, h & 0x7FFFF
            if q + 3 + n > len(payload):
                bad("truncated")
            body = payload[q + 3:q + 3 + n]
            if n < sub_len:
                lz_sub_chunk(body, mode, out, base, start, start + sub_len)
            elif n == sub_len and mode == 0:
                out[start:start + sub_len] = body
            else:
                bad("bad sub-chunk header")
            q += 3 + n
        d += sub_len
    if q != len(payload):
        bad("quantum payload not exactly consumed")


def decode(src: bytes, raw_size: int) -> bytes:
    """The whole stream: raw_size bytes out, or LzError."""
    src = memoryview(bytes(src))
    out = bytearray(raw_size)
    ip = produced = base = 0
    try:
        while produced < raw_size:
            left = min(raw_size - produced, LZ_BLOCK)
            if ip + 2 > len(src):
                bad("truncated")
            b0, b1 = src[ip], src[ip + 1]
            ip += 2
            if (b0 & 0x0F) != 0x0C or (b0 & 0x30) != 0:
                bad("bad block header")
            if b1 & 0x80:
                bad("checksummed blocks are not supported")
            if (b1 & 0x7F) != 0x0C:
                bad("only the Leviathan block format is supported")
            if b0 & 0x80:
                base = produced
            if b0 & 0x40:
                if ip + left > len(src):
                    bad("truncated")
                out[produced:produced + left] = src[ip:ip + left]
                ip += left
                produced += left
                continue
            if ip + 3 > len(src):
                bad("truncated")
            v = src[ip] << 16 | src[ip + 1] << 8 | src[ip + 2]
            size = v & 0x3FFFF
            ip += 3
            if size != 0x3FFFF:
                if ip + size + 1 > len(src):
                    bad("truncated")
                lz_payload(src[ip:ip + size + 1], out, produced, left, base)
                ip += size + 1
            elif v >> 18 == 1:
                if ip >= len(src):
                    bad("truncated")
                out[produced:produced + left] = bytes((src[ip],)) * left
                ip += 1
            else:
                bad("bad quantum header")
            produced += left
    except IndexError:  # a corrupt stream read past one of its arrays
        bad("truncated")
    return bytes(out)
