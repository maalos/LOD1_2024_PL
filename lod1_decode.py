#!/usr/bin/env python3
"""Reference decoder for the GBLD v2 (.bld) building files. Needs numpy only.

    python3 lod1_decode.py bld/0264_M-33.bld            # summary
    from lod1_decode import read_buildings
    for b in read_buildings("bld/0264_M-33.bld"): ...   # b["rings"], b["height"], ...

Coordinates are EPSG:2180 metres (x = easting, y = northing). For lon/lat see README.md ("Coordinate system").
"""
import math
import sys
import zlib

import numpy as np

ANGLE_UNIT = math.pi / 2 / 16384            # one unit of an ortho ring's `k`, radians


def _uv(b, o):
    r = s = 0
    while True:
        c = b[o]
        o += 1
        r |= (c & 127) << s
        if c < 128:
            return r, o
        s += 7


def _sv(b, o):
    v, o = _uv(b, o)
    return (v >> 1) ^ -(v & 1), o


def _varints(buf):
    a = np.frombuffer(buf, np.uint8)
    if not len(a):
        return np.zeros(0, np.int64)
    ends = np.flatnonzero(a < 128)
    starts = np.concatenate(([0], ends[:-1] + 1))
    ln = ends - starts + 1
    out = np.zeros(len(ends), np.int64)
    for i in range(int(ln.max())):
        m = ln > i
        out[m] |= (a[starts[m] + i].astype(np.int64) & 127) << (7 * i)
    return out


def _zz(v):
    return (v >> 1) ^ -(v & 1)


def read_header(b):
    if b[:4] != b"GBLD" or b[4] != 2:
        raise ValueError("not a GBLD v2 file")
    xy_cm, z_cm = b[6], b[7]
    n, o = _uv(b, 8)
    tiles, px, py = [], 0, 0
    for _ in range(n):
        dx, o = _sv(b, o)
        dy, o = _sv(b, o)
        ex, o = _uv(b, o)
        ey, o = _uv(b, o)
        c, o = _uv(b, o)
        px, py = px + dx, py + dy
        tiles.append((px, py, ex, ey, c))
    nb, o = _uv(b, o)
    blocks = []
    for _ in range(nb):
        t, o = _uv(b, o)
        m, o = _uv(b, o)
        blocks.append((t, m >> 1, m & 1))
    return dict(xy_cm=xy_cm, z_cm=z_cm, tiles=tiles, blocks=blocks, data=o)


def ortho_ring(p0, k, swap, steps, n):
    """An ortho ring: a rectilinear outline in a frame turned by k * ANGLE_UNIT. `steps` are the first n - 2
    edges' signed lengths (alternating along the two axes); the last two edges close the ring."""
    th = k * ANGLE_UNIT
    u = np.array([math.cos(th), math.sin(th)])
    v = np.array([-u[1], u[0]])
    ax = (v, u) if swap else (u, v)
    d = np.where((np.arange(len(steps)) & 1)[:, None] == 0, ax[0], ax[1]) * steps[:, None]
    pts = p0 + np.vstack([[0.0, 0.0], np.cumsum(d, axis=0)])
    side = (n - 2) & 1
    return np.vstack([pts, pts[-1] - steps[side::2].sum() * ax[side]])


def read_buildings(path):
    """Yield one dict per building: tile (index), anchor (x, y metres), height (m, None if unknown),
    base_z (m, as stored: see README), rings [(is_hole, (n, 2) array of EPSG:2180 metres, not closed)]."""
    b = open(path, "rb").read()
    h = read_header(b)
    spm, zs = 100.0 / h["xy_cm"], h["z_cm"] / 100.0
    o, t0 = h["data"], 0
    base = 0
    for tcount, ln, defl in h["blocks"]:
        raw = b[o:o + ln]
        o += ln
        raw = zlib.decompress(raw, -15) if defl else raw
        po, streams = 0, []
        for _ in range(6):
            n, po = _uv(raw, po)
            streams.append(raw[po:po + n])
            po += n
        ax_s, ay_s, bz_s, ht_s, rg_s, vx_s = streams
        ax, ay, bz = _zz(_varints(ax_s)), _zz(_varints(ay_s)), _zz(_varints(bz_s))
        hv = _varints(ht_s)
        pal = hv[1:1 + int(hv[0])] * zs
        hidx = hv[1 + int(hv[0]):]
        rg = _varints(rg_s).tolist()
        vu = _varints(vx_s)
        vs = _zz(vu)
        vu = vu.tolist()
        rp = vp = i = 0
        for ti in range(t0, t0 + tcount):
            ox, oy, _, _, cnt = h["tiles"][ti]
            gx = gy = 0                                   # anchors restart at every tile
            for _ in range(cnt):
                gx += int(ax[i])
                gy += int(ay[i])
                base += int(bz[i])
                rc = rg[rp]
                rp += 1
                sx, sy, rings = gx, gy, []
                for r in range(rc):
                    v = rg[rp]
                    rp += 1
                    n, hole, ortho = v >> 2, (v >> 1) & 1, v & 1
                    if r:                                 # a further ring starts relative to the previous ring's start
                        sx += int(vs[vp])
                        sy += int(vs[vp + 1])
                        vp += 2
                    p0 = np.array([sx, sy], np.float64)
                    if not ortho:
                        d = vs[vp:vp + 2 * (n - 1)].reshape(-1, 2).astype(np.float64)
                        vp += 2 * (n - 1)
                        pts = p0 + np.vstack([[0.0, 0.0], np.cumsum(d, axis=0)])
                    else:
                        ks = vu[vp]
                        steps = vs[vp + 1:vp + n - 1].astype(np.float64)
                        vp += n - 1
                        pts = ortho_ring(p0, ks >> 1, ks & 1, steps, n)
                    rings.append((bool(hole), pts / spm + (ox, oy)))
                ht = float(pal[hidx[i]])
                yield dict(tile=ti, anchor=(ox + gx / spm, oy + gy / spm), height=ht or None,
                           base_z=base * zs, rings=rings)
                i += 1
        t0 += tcount


if __name__ == "__main__":
    n = holes = 0
    hs = []
    for bd in read_buildings(sys.argv[1]):
        n += 1
        holes += sum(1 for h, _ in bd["rings"] if h)
        if bd["height"]:
            hs.append(bd["height"])
    print(f"{n} buildings, {holes} holes, median height {np.median(hs):.1f} m")
