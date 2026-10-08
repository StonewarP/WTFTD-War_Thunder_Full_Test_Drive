"""Weapons page data: stats of every missile, bomb, rocket and torpedo of the game, and who carries it.

data/armament.json = {"items": [...], "carriers": {id: [vehicle ids]}}. Item fields (short keys, missing = n/a):
  id, c category, g guidance, ic icon, nat nations, br lowest carrier BR (RB), nk nuclear
  m mass kg, e explosive kg, tnt TNT equivalent kg, cal caliber mm, v top speed m/s, rng max range m,
  acc launch acceleration G,
  gl max G, burn motor burn s, pen penetration mm, pf proximity fuse radius m,
  IR seeker: lk lock range (rear) m, aa all-aspect lock range m, ob off-boresight lock angle deg,
             trk tracking rate deg/s, ccm flare rejection (IRCCM),
  radar: act active seeker (fire & forget), ins inertial guidance, dl datalink, loft, sr seeker range m,
  ff fire-and-forget, wire wire-guided, beam beam rider.
"""
from __future__ import annotations

import json
import math
import re

from .builder import DATA, DM, NUKES, ICON_VOTES, Lang, aslist, first_str, humanize, load, log, report

W = DM / "aces.vromfs.bin_u" / "gamedata" / "weapons"
FOLDERS = ("rocketguns", "bombguns", "torpedoes", "groundmodels_weapons", "navalmodels_weapons")
SURFACE = ("groundmodels_weapons", "navalmodels_weapons")
SKIP_TYPES = re.compile(r"^(flare|chaff|smoke|.*grenade)")

ICONS = {"aam_ir": "missile_air_to_air", "aam_radar": "missile_air_to_air_midrange", "sam": "missile_air_to_air",
         "atgm": "missile_air_to_uni_middle", "agm": "missile_air_to_uni", "gbomb": "guided_bomb_middle_laser",
         "bomb": "bombs_middle", "rocket": "rockets_he_large", "torpedo": "torpedo"}


def _n(v):
    for x in aslist(v):
        if isinstance(x, (int, float)) and not isinstance(x, bool):
            return float(x)
    return None


def _payloads(o, parent=None, out=None):
    """(kind, merged dict) of every rocket / bomb / torpedo in a weapon file. Ground launchers keep the
    projectile fields (mass, warhead...) on `bullet` and the flight model on `bullet.rocket`: merged."""
    if out is None:
        out = []
    if isinstance(o, dict):
        for k, v in o.items():
            if k in ("rocket", "bomb", "torpedo") and isinstance(v, (dict, list)):
                for x in aslist(v):
                    if isinstance(x, dict):
                        m = {kk: vv for kk, vv in o.items() if kk != k} if parent == "bullet" else {}
                        m.update(x)
                        out.append((k, m))
            else:
                _payloads(v, k, out)
    elif isinstance(o, list):
        for x in o:
            _payloads(x, parent, out)
    return out


def _category(kind: str, p: dict, folder: str, stem: str):
    bt = first_str(p.get("bulletType")).lower()
    gd = p.get("guidance") if isinstance(p.get("guidance"), dict) else None
    gt = first_str(p.get("guidanceType")).lower()
    guided = bool(gt and gt != "none") or gd is not None or bool(p.get("operated"))  # operated = MCLOS
    if folder == "torpedoes" or kind == "torpedo":
        return "torpedo"
    if SKIP_TYPES.match(bt):
        return None
    if kind == "bomb":
        if folder != "bombguns":
            return None  # ships' depth charges / ASW mortars
        return "gbomb" if guided else "bomb"
    if folder == "bombguns":
        return "gbomb" if guided else "rocket"
    if bt.startswith("aam") or bt.startswith("sam"):
        if not guided:
            return "rocket"
        if folder in SURFACE or bt.startswith("sam"):
            return "sam"
        return "aam_ir" if gt == "optical" else "aam_radar"
    if bt.startswith("atgm"):
        return "atgm"
    if guided:
        return "agm"
    if bt.startswith(("rocket", "heat", "he", "ap", "frag")) or not bt:
        return "rocket"
    return None


def _guidance(cat: str, p: dict) -> str:
    gt = first_str(p.get("guidanceType")).lower()
    gd = p.get("guidance") if isinstance(p.get("guidance"), dict) else {}
    if cat == "torpedo":
        return "sonar" if gt == "sonar" else ""
    if gt == "optical":
        os_ = gd.get("opticalSeeker") if isinstance(gd.get("opticalSeeker"), dict) else {}
        sig = first_str(os_.get("targetSignatureType")).lower()
        return "tv" if sig == "optic" else "ir"
    if gt == "radar":
        rs = gd.get("radarSeeker") if isinstance(gd.get("radarSeeker"), dict) else {}
        if first_str(rs.get("targetSignatureType")).lower() == "radarintercept":
            return "arm"
        return "arh" if rs.get("active") else "sarh"
    if gt == "saclos":
        return "beam" if gd.get("beamRider") else "saclos"
    if gt == "sns":
        return "gps"
    if gt == "laser":
        return "laser"
    return "mclos" if cat in ("atgm", "sam", "aam_radar", "agm", "gbomb") else ""


def _stages(p: dict) -> list:
    """Motor stages as (thrust N, burn s, mass lost kg). Two formats: force / timeFire / massEnd (+1, 2) or
    propulsion<N>.impulse<K> {force, time, massLost} (newer missiles, e.g. AIM-54)."""
    out, m0 = [], _n(p.get("mass"))
    for i in ("", "1", "2"):
        force, t, m1 = _n(p.get("force" + i)), _n(p.get("timeFire" + i)), _n(p.get("massEnd" + i))
        if not (force and t and m0 and m1 and m0 > m1):
            break
        out.append((force, t, m0 - m1))
        m0 = m1
    if not out:
        for i in range(4):
            pr = p.get(f"propulsion{i}")
            if not isinstance(pr, dict):
                break
            for j in range(8):
                im = pr.get(f"impulse{j}")
                if not isinstance(im, dict):
                    break
                force, t, lost = _n(im.get("force")), _n(im.get("time")), _n(im.get("massLost"))
                if force and t and lost:
                    out.append((force, t, lost))
    return out


def _motor_dv(p: dict) -> float:
    """Speed the motor adds (rocket equation, stage by stage, no drag)."""
    total, m0 = 0.0, _n(p.get("mass")) or 0
    for force, t, lost in _stages(p):
        if m0 <= lost:
            break
        total += force * t / lost * math.log(m0 / (m0 - lost))  # exhaust velocity x ln(mass ratio)
        m0 -= lost
    return total


def _launch_accel(p: dict) -> float:
    """Acceleration off the rail, in G: first-stage thrust / launch mass."""
    st, m = _stages(p), _n(p.get("mass"))
    return st[0][0] / m / 9.81 if st and m else 0


def _stats(cat: str, g: str, p: dict, tnt_eq: dict) -> dict:
    s: dict = {}

    def put(k, v, nd=1):
        if v is not None and v > 0:
            s[k] = round(v, nd) if nd else round(v)

    put("m", _n(p.get("mass")), 1)
    e = _n(p.get("explosiveMass"))
    put("e", e, 2)
    if e:
        put("tnt", e * tnt_eq.get(first_str(p.get("explosiveType")).lower(), 1.0), 2)
    cal = _n(p.get("caliber"))
    put("cal", cal * 1000 if cal else None, 0)
    if cat == "torpedo":
        put("v", _n(p.get("maxSpeedInWater")) or _n(p.get("speed")), 1)
        put("rng", _n(p.get("distToLive")), 0)
        return s
    if cat in ("bomb",):
        return s
    mach = _n(p.get("machMax"))
    vend = _n(p.get("endSpeed"))
    dv = _motor_dv(p) if cat in ("aam_ir", "aam_radar", "sam", "agm") else 0
    if dv:  # missiles: what the motor gives (machMax is only a cap)
        put("v", min(dv, mach * 340) if mach else dv, 0)
        put("acc", _launch_accel(p), 1)
    else:  # ATGMs, rockets: cruise / end speed
        put("v", vend if vend and vend < 1500 else (mach * 340 if mach else None), 0)
    rng = _n(p.get("maxDistance")) or _n(p.get("rangeMax"))
    put("rng", rng if rng and rng < 400000 else None, 0)
    gd = p.get("guidance") if isinstance(p.get("guidance"), dict) else {}
    ap = gd.get("guidanceAutopilot") if isinstance(gd.get("guidanceAutopilot"), dict) else {}
    put("gl", _n(p.get("loadFactorMax")) or _n(ap.get("reqAccelMax")), 0)
    burn = (_n(p.get("timeFire")) or 0) + (_n(p.get("timeFire1")) or 0)
    put("burn", burn, 1)
    cd = p.get("cumulativeDamage") if isinstance(p.get("cumulativeDamage"), dict) else {}
    pen = _n(cd.get("armorPower"))
    if not pen:
        apw = p.get("armorpower") if isinstance(p.get("armorpower"), dict) else {}
        pen = _n(apw.get("ArmorPower0m"))
    if cat in ("atgm", "agm", "rocket"):
        put("pen", pen, 0)
    pfz = p.get("proximityFuse") if isinstance(p.get("proximityFuse"), dict) else {}
    if p.get("hasProximityFuse") or pfz:
        put("pf", _n(pfz.get("radius")), 1)
    if p.get("wireGuidanceEffects") or p.get("wired"):
        s["wire"] = 1
    os_ = gd.get("opticalSeeker") if isinstance(gd.get("opticalSeeker"), dict) else None
    rs = gd.get("radarSeeker") if isinstance(gd.get("radarSeeker"), dict) else None
    if os_ is not None and cat in ("aam_ir", "sam"):
        put("lk", _n(os_.get("rangeBand0")) or _n(os_.get("rangeMax")), 0)
        put("aa", _n(os_.get("rangeBand1")), 0)
        put("ob", _n(os_.get("lockAngleMax")), 0)
        put("trk", _n(os_.get("rateMax")), 0)
        if os_.get("bandMaskToReject") is not None or os_.get("signalRelRejectedTreshold") is not None:
            s["ccm"] = 1
    if rs is not None:
        rcv = rs.get("receiver") if isinstance(rs.get("receiver"), dict) else {}
        put("sr", _n(rcv.get("range")) or _n(gd.get("lockDistance")), 0)
        put("ob", _n(rs.get("lockAngleMax")), 0)
        if rs.get("active"):
            s["act"] = 1
    if gd.get("inertialNavigation") or gd.get("inertialGuidance"):
        s["ins"] = 1
    ig = gd.get("inertialGuidance") if isinstance(gd.get("inertialGuidance"), dict) else {}
    if ig.get("datalink"):
        s["dl"] = 1
    if ap.get("loftEnabled"):
        s["loft"] = 1
    if g in ("ir", "tv", "arh", "gps", "arm") and cat in ("agm", "atgm", "gbomb"):
        s["ff"] = 1  # no designation needed once launched
    return s


def _name(lang: Lang, iid: str, stem: str) -> None:
    """Short game name ("R-73", not "R-73 air-to-air missiles") in the "arm" section."""
    if iid in lang.out["arm"]:
        return
    if not lang.put("arm", iid, f"weapons/{iid}/short", f"{iid}/short", iid, f"weapons/{stem}/short", stem,
                    f"weapons/{iid}", f"weapons/{stem}"):
        known = lang.out["weapons"].get(stem)
        lang.out["arm"][iid] = known if known else {"en": humanize(iid)}


def build_armament(lang: Lang, vehicles: list, progress=None) -> dict:
    log("Building the weapons page...", progress)
    report(progress, 0.88)
    ex = load(DM / "aces.vromfs.bin_u" / "gamedata" / "damage_model" / "explosive.blkx") or {}
    tnt_eq = {k.lower(): _n((v or {}).get("strengthEquivalent")) or 1.0
              for k, v in (ex.get("explosiveTypes") or {}).items() if isinstance(v, dict)}
    items: dict[str, dict] = {}
    by_file: dict[str, set] = {}  # weapon file key -> armament ids it fires
    for folder in FOLDERS:
        for f in sorted((W / folder).glob("*.blkx")):
            d = load(f)
            if not isinstance(d, dict):
                continue
            stem = f.stem.lower()
            for kind, p in _payloads(d):
                cat = _category(kind, p, folder, stem)
                if not cat:
                    continue
                iid = (first_str(p.get("bulletName")) or stem).lower()
                by_file.setdefault(stem, set()).add(iid)
                old = items.get(iid)
                if old and not old["_src"].endswith("_default") and not (old["c"] == "rocket" and cat != "rocket"):
                    continue
                g = _guidance(cat, p)
                it = {"id": iid, "c": cat, "g": g, "_src": stem, **_stats(cat, g, p, tnt_eq)}
                if stem in NUKES or iid in NUKES:
                    it["nk"] = 1
                icon = first_str(p.get("iconType"))
                votes = ICON_VOTES.get(stem)
                it["ic"] = icon or (max(votes, key=votes.get) if votes else ICONS[cat])
                items[iid] = it
    # carriers: pylon / preset weapons (file keys), launchers (file keys), ammunition (bullet names)
    carriers: dict[str, set] = {}
    for v in vehicles:
        ammo = set(v.get("wa") or [])
        for k in list(v.get("wp") or []) + list(v.get("wg") or []):
            ids = by_file.get(k) or by_file.get(re.sub(r"(_default|_\d+)$", "", k)) or set()
            mine = ids & ammo
            for iid in (mine or ids):
                carriers.setdefault(iid, set()).add(v["id"])
        for b in ammo:
            if b in items:
                carriers.setdefault(b, set()).add(v["id"])
    vmap = {v["id"]: v for v in vehicles}
    out = []
    for iid, it in items.items():
        car = carriers.get(iid, set())
        if not car:
            continue  # not carried by any vehicle: test / unused file
        if it["c"] == "bomb" and all(vmap[c]["c"] in ("boat", "ship") for c in car):
            continue  # depth charges, ASW mortars
        _name(lang, iid, it.pop("_src"))
        nats = sorted({vmap[c]["n"] for c in car if vmap[c].get("n")})
        if nats:
            it["nat"] = nats
        brs = [vmap[c]["br"][1] for c in car if not vmap[c].get("h") and isinstance(vmap[c].get("br"), list) and len(vmap[c]["br"]) > 1]
        if brs:
            it["br"] = min(brs)
        it["nv"] = len(car)
        out.append(it)
    # same weapon in several files under different keys: keep one per (name, category)
    names = lang.out["arm"]
    best: dict = {}
    for it in out:
        key = ((names.get(it["id"]) or {}).get("en", it["id"]).strip().lower(), it["c"], round(it.get("m", 0)), round(it.get("tnt", 0)))
        cur = best.get(key)
        if cur is None:
            best[key] = it
            continue
        cur.setdefault("alias", []).append(it["id"])
        carriers.setdefault(cur["id"], set()).update(carriers.get(it["id"], set()))
        cur["nv"] = len(carriers[cur["id"]])
        if "br" in it:
            cur["br"] = min(cur.get("br", 99), it["br"])
        cur["nat"] = sorted(set(cur.get("nat", [])) | set(it.get("nat", [])))
    final = list(best.values())
    for it in final:
        it.pop("alias", None)
    data = {"items": final, "carriers": {it["id"]: sorted(carriers[it["id"]]) for it in final}}
    with open(DATA / "armament.json", "w", encoding="utf-8") as fw:
        json.dump(data, fw, separators=(",", ":"))
    log(f"  {len(final)} weapons", progress)
    return data
