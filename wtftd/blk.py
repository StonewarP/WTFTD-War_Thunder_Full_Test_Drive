"""Serializes datamine-style JSON (blkx) back to War Thunder text BLK.

Type rules (the datamine keeps int/float distinct):
  bool -> b, int -> i, float -> r, str -> t
  [x, y(, z(, w))] numbers -> p2/p3/p4 (ip2/ip3/ip4 when all ints)
  'tm' or 4x[3 numbers]  -> m (matrix)
  list of dicts / strs / lists -> the key repeated once per item
"""
from __future__ import annotations

import math
import re


def _num(v: float) -> str:
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, int):
        return str(v)
    if math.isnan(v) or math.isinf(v):
        return "0"
    v = float(v)
    if v.is_integer() and abs(v) < 1e15:
        return str(int(v))
    s = repr(v)
    if "e" in s or "E" in s:
        s = f"{v:.12f}".rstrip("0")
        if s.endswith("."):
            s += "0"
    return s


def _str(s: str) -> str:
    if '"' in s and "'" not in s:
        return f"'{s}'"
    return '"' + s.replace('"', "'") + '"'


_PLAIN_KEY = re.compile(r"^[A-Za-z0-9_.\-@#$]+$")


def _key(k: str) -> str:
    return k if _PLAIN_KEY.match(k) else _str(k)


def _is_num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _is_vec(v) -> bool:
    return isinstance(v, list) and 2 <= len(v) <= 4 and all(_is_num(x) for x in v)


def _is_matrix(v) -> bool:
    return isinstance(v, list) and len(v) == 4 and all(isinstance(r, list) and len(r) == 3 and all(_is_num(x) for x in r) for r in v)


def _param(name: str, v, ind: str, out: list[str]):
    key = _key(name)
    if isinstance(v, dict):
        if not v:
            out.append(f"{ind}{key}{{}}")
            return
        out.append(f"{ind}{key}{{")
        _block(v, ind + "  ", out)
        out.append(f"{ind}}}")
    elif isinstance(v, bool):
        out.append(f"{ind}{key}:b={'yes' if v else 'no'}")
    elif isinstance(v, int):
        out.append(f"{ind}{key}:i={v}")
    elif isinstance(v, float):
        out.append(f"{ind}{key}:r={_num(v)}")
    elif isinstance(v, str):
        out.append(f"{ind}{key}:t={_str(v)}")
    elif v is None:
        out.append(f'{ind}{key}:t=""')
    elif isinstance(v, list):
        if name == "tm" or _is_matrix(v):
            rows = " ".join("[" + ", ".join(_num(float(x)) for x in r) + "]" for r in v)
            out.append(f"{ind}{key}:m=[{rows}]")
        elif _is_vec(v) and not key.lower().startswith("color"):
            if all(isinstance(x, int) for x in v):
                out.append(f"{ind}{key}:ip{len(v)}=" + ", ".join(str(x) for x in v))
            else:
                out.append(f"{ind}{key}:p{len(v)}=" + ", ".join(_num(float(x)) for x in v))
        elif key.lower().startswith("color") and len(v) == 4 and all(isinstance(x, int) for x in v):
            out.append(f"{ind}{key}:c=" + ", ".join(str(x) for x in v))
        else:
            for item in v:  # repeated key
                _param(name, item, ind, out)
    else:
        out.append(f"{ind}{key}:t={_str(str(v))}")


def _block(d: dict, ind: str, out: list[str]):
    for k, v in d.items():
        _param(k, v, ind, out)


def dumps(d: dict) -> str:
    out: list[str] = []
    _block(d, "", out)
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- parser (text BLK -> dict)

_re = re



def _parse_value(typ: str, raw: str):
    raw = raw.strip()
    if typ == "t":
        return raw[1:-1] if raw[:1] in "\"'" else raw
    if typ in ("i", "i64"):
        return int(raw)
    if typ == "r":
        return float(raw)
    if typ == "b":
        return raw.lower() in ("yes", "true", "on", "1")
    if typ == "m":
        rows = _re.findall(r"\[([^\[\]]*)\]", raw)
        return [[float(x) for x in r.replace(",", " ").split()] for r in rows]
    if typ in ("p2", "p3", "p4"):
        return [float(x) for x in raw.split(",")]
    if typ in ("ip2", "ip3", "ip4", "c"):
        return [int(x) for x in raw.split(",")]
    return raw


def _add(d: dict, k: str, v):
    if k in d:
        if isinstance(d[k], list) and d.get("\0rep_" + k):
            d[k].append(v)
        else:
            d[k] = [d[k], v]
            d["\0rep_" + k] = True
    else:
        d[k] = v


def _strip(d):
    if isinstance(d, dict):
        return {k: _strip(v) for k, v in d.items() if not k.startswith("\0rep_")}
    if isinstance(d, list):
        return [_strip(x) for x in d]
    return d


def loads(text: str) -> dict:
    root: dict = {}
    stack = [root]
    i, n = 0, len(text)
    while i < n:
        m = _re.compile(r"\s+|//[^\n]*|/\*.*?\*/", _re.S).match(text, i)
        if m and m.end() > i:
            i = m.end()
            continue
        if text[i] == "}":
            stack.pop()
            i += 1
            continue
        m = _re.compile(r'("[^"]*"|\'[^\']*\'|[^\s:{}=;]+)\s*').match(text, i)
        if not m:
            raise ValueError(f"BLK parse error at {i}: {text[i:i+40]!r}")
        key = m.group(1).strip("\"'")
        i = m.end()
        if text[i:i + 1] == "{":
            blk: dict = {}
            _add(stack[-1], key, blk)
            stack.append(blk)
            i += 1
            continue
        m = _re.compile(r":\s*([a-z0-9]+)\s*=\s*").match(text, i)
        if not m:
            raise ValueError(f"BLK parse error at {i}: {text[i:i+40]!r}")
        typ = m.group(1)
        i = m.end()
        if typ == "m":
            depth, j = 0, i
            while j < n:
                if text[j] == "[":
                    depth += 1
                elif text[j] == "]":
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                j += 1
            raw = text[i:j]
        elif text[i:i + 1] in "\"'":
            q = text[i]
            j = text.index(q, i + 1) + 1
            raw = text[i:j]
        else:
            m2 = _re.compile(r"[^\n;}]*").match(text, i)
            raw = m2.group(0)
            j = m2.end()
            # stop before a following "key:type=" on the same line
            m3 = _re.search(r"\s+[A-Za-z_][\w.\-]*\s*(?::[a-z0-9]+\s*=|\{)", raw)
            if m3:
                raw = raw[:m3.start()]
                j = i + m3.start()
        _add(stack[-1], key, _parse_value(typ, raw))
        i = j
        if text[i:i + 1] == ";":
            i += 1
    return _strip(root)
