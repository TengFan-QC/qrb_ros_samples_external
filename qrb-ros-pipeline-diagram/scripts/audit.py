#!/usr/bin/env python3
"""Audit a rendered pipeline SVG for the defects that actually occur in practice.

Every check here corresponds to a real bug that shipped at least once:
  - lines crossing each other        (apriltag camera_info fan-out)
  - an edge label sitting on a line  (/cam0_stream1 touching its riser)
  - an edge label over a node box    (wrap labels drifting into a box)
  - node text wider than its box     (long plugin names)
  - foreignObject / invalid XML      (draw.io exports don't belong here)

Usage:  python3 audit.py <file.svg> [more.svg ...]
Exit code is non-zero if any file has a finding, so it works as a gate.
"""
import os
import re
import sys
import xml.dom.minidom

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from metrics import text_width

NODE_W, NODE_H = 151.0, 72.0
BASELINE = 0.36
NODE_FILLS = {"#6280cc", "#007aa4", "#000000", "#7c8aa3", "#d2d7e1"}


def parse(svg):
    """Return (segments, texts, node_rects) in user units."""
    segs = []
    for d in re.findall(r'<path d="(M [^"]*)" fill="none"', svg):
        pts = [tuple(map(float, p.split())) for p in d[2:].split(" L ")]
        segs += list(zip(pts, pts[1:]))

    texts = []
    for m in re.finditer(
        r'<text x="([-\d.]+)" y="([-\d.]+)"[^>]*?font-size="([\d.]+)"[^>]*?'
        r'text-anchor="(\w+)"([^>]*)>([^<]*)</text>', svg):
        x, y, fs, anchor, rest, body = m.groups()
        x, y, fs = float(x), float(y), float(fs)
        w = text_width(body, fs, bold="bold" in rest)
        x0 = {"middle": x - w / 2, "start": x, "end": x - w}[anchor]
        top = y - fs * BASELINE - fs * 0.72
        texts.append({"s": body, "box": (x0, top, x0 + w, top + fs), "fs": fs})

    rects = []
    for m in re.finditer(
        r'<rect x="([-\d.]+)" y="([-\d.]+)" width="([\d.]+)" height="([\d.]+)" '
        r'rx="4"[^>]*fill="(#[0-9a-fA-F]{6})"', svg):
        x, y, w, h, fill = m.groups()
        w, h = float(w), float(h)
        # node boxes only: the legend swatches are 22x22 and share the same fills
        if fill.lower() in NODE_FILLS and w > 100 and h > 40:
            rects.append((float(x), float(y), float(x) + w, float(y) + h))
    return segs, texts, rects


def overlaps(a, b, pad=0.0):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return not (ax1 + pad <= bx0 or bx1 <= ax0 - pad or
                ay1 + pad <= by0 or by1 <= ay0 - pad)


def seg_box(s):
    (x0, y0), (x1, y1) = s
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def audit(path):
    svg = open(path, encoding="utf-8").read()
    findings = []

    try:
        xml.dom.minidom.parseString(svg)
    except Exception as e:
        return [f"invalid XML: {e}"]
    if "foreignObject" in svg:
        findings.append("contains <foreignObject>; use plain <text> instead")

    segs, texts, rects = parse(svg)

    # 1. interior line crossings (shared endpoints and T-junctions are fine)
    horiz = lambda s: abs(s[0][1] - s[1][1]) < 0.5
    for i, A in enumerate(segs):
        for B in segs[i + 1:]:
            if horiz(A) == horiz(B):
                continue
            h, v = (A, B) if horiz(A) else (B, A)
            x1, x2 = sorted((h[0][0], h[1][0]))
            y = h[0][1]
            vx = v[0][0]
            y1, y2 = sorted((v[0][1], v[1][1]))
            if x1 + 0.5 < vx < x2 - 0.5 and y1 + 0.5 < y < y2 - 0.5:
                findings.append(f"lines cross at ({vx:.0f}, {y:.0f})")

    # 2/3. a label that is not inside a node box must clear both lines and boxes
    for t in texts:
        cx = (t["box"][0] + t["box"][2]) / 2
        cy = (t["box"][1] + t["box"][3]) / 2
        if any(r[0] <= cx <= r[2] and r[1] <= cy <= r[3] for r in rects):
            continue                                  # node label, legitimately inside
        for s in segs:
            if overlaps(t["box"], seg_box(s), pad=-1.0):
                findings.append(f'label "{t["s"]}" overlaps a line')
                break
        for r in rects:
            if overlaps(t["box"], r, pad=-1.0):
                findings.append(f'label "{t["s"]}" overlaps a node box')
                break

    # 4. node text must fit its box
    for r in rects:
        inside = [t for t in texts
                  if r[0] <= (t["box"][0] + t["box"][2]) / 2 <= r[2]
                  and r[1] <= (t["box"][1] + t["box"][3]) / 2 <= r[3]]
        for t in inside:
            w = t["box"][2] - t["box"][0]
            if w > NODE_W - 10:
                findings.append(f'node text "{t["s"]}" is {w:.0f}px (max {NODE_W - 10:.0f})')
        if len(inside) * 14.4 > NODE_H - 6:
            findings.append(f"a node box holds {len(inside)} lines, too many for 72px")

    return findings


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    bad = 0
    for p in sys.argv[1:]:
        f = audit(p)
        name = os.path.basename(p)
        if f:
            bad += 1
            print(f"FAIL  {name}")
            for x in sorted(set(f)):
                print(f"        {x}")
        else:
            print(f"ok    {name}")
    if bad:
        print(f"\n{bad} file(s) with findings")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
