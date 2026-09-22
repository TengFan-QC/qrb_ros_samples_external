#!/usr/bin/env python3
"""Render a pipeline-graph spec (JSON) to SVG in the ga1.6-hand-detection.svg design system.

Every geometry constant below is calibrated directly against
media/80-65220-2-qirp-sdk-qsg/ga1.6-hand-detection.svg (a draw.io export):
  canvas 1246x322 rx=6 fill #fafafa stroke #d2d7e1 sw=2
  node   150.97x71.67 rx=4 fill #6280cc, white 12px Roboto, row pitch 152.29
  topic labels: plain black 12px Roboto, 16px above the arrow line
  arrowheads: solid black triangle, 7 long x 7 wide
  legend: 22x22 rounded swatches + bold 11px labels, bottom right

Feeding the reference's own graph back through this renderer reproduces a
1265x323 canvas against the original's 1246x322 (~1.5%).

Spec format
-----------
{
  "nodes": [{"id","lines":[..],"kind","row","col"}],
  "edges": [{"from","to","label","route"?,"lane"?,"exitDx"?,"enterDx"?,
             "bidirectional"?,"dashed"?}],
  "groups":[{"id"?,"title","members":[ids],"innerLabel"?}],
  "legendLabels": {"<kind>": "override"}       # optional
  "colGap": {"<col index>": px}                # optional manual gap override
}
kind: qualcomm | opensource | topic | module | external
route: h | v | step | wrap | wrapup | under   (auto-detected when omitted)
"""
import json
import os
import sys
import xml.sax.saxutils as sx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from metrics import text_width

# ---------------------------------------------------------------- geometry
NODE_W = 151.0
NODE_H = 72.0
NODE_RX = 4
ROW_GAP = 80.0                 # 152.29 row pitch - 72 node height
MIN_COL_GAP = 96.0
LABEL_PAD = 52.0               # calibrated: reproduces the reference column pitch
PAD_L = 34.0
PAD_R = 34.0
PAD_T = 31.5
LEGEND_BAND = 66.0             # reserved strip below the last row

GROUP_PAD_X = 20.13
GROUP_PAD_Y = 17.9
GROUP_MEMBER_GAP = 26.87
GROUP_TITLE_DY = 23.0          # title centre above the dashed rect

ARROW_LEN = 7.0
ARROW_HALF = 3.5
LANE_STEP = 22.0
ABOVE_BASE = 30.0              # first trunk lane above row 0
ABOVE_STEP = 34.0              # stacked trunk spacing: must exceed TOPIC_DY +
                               # TOPIC_FS, or the lower trunk's label lands on
                               # the trunk above it

FONT = "Roboto, Helvetica, Arial, sans-serif"
NODE_FS = 12.0
NODE_LINE_H = 14.4             # 12px * 1.2
TOPIC_FS = 12.0
TOPIC_DY = 16.0                # label centre above the arrow line
GROUP_TITLE_FS = 15.0
LEGEND_FS = 11.0
BASELINE = 0.36                # baseline offset as a fraction of font size

KINDS = {
    "qualcomm":   {"fill": "#6280cc", "text": "#FFFFFF", "legend": "ROS node"},
    "opensource": {"fill": "#007aa4", "text": "#FFFFFF", "legend": "Open-source ROS node"},
    "topic":      {"fill": "#000000", "text": "#FFFFFF", "legend": "topic"},
    "module":     {"fill": "#7c8aa3", "text": "#FFFFFF", "legend": "Internal module"},
    "external":   {"fill": "#d2d7e1", "text": "#000000", "legend": "External app"},
}
LEGEND_ORDER = ["qualcomm", "opensource", "module", "external", "topic"]


def label_lines(label):
    """An edge label is either a string or a list of stacked lines."""
    if not label:
        return []
    return list(label) if isinstance(label, (list, tuple)) else [label]


def label_width(label):
    return max((text_width(l, TOPIC_FS) for l in label_lines(label)), default=0.0)


def esc(s):
    return sx.escape(str(s))


def fmt(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


class Renderer:
    def __init__(self, spec):
        self.spec = spec
        self.nodes = {n["id"]: dict(n) for n in spec["nodes"]}
        self.order = [n["id"] for n in spec["nodes"]]
        self.edges = spec.get("edges", [])
        self.groups = [dict(g) for g in spec.get("groups", [])]
        self.out = []
        self.warnings = []

    # ------------------------------------------------------------ layout
    def layout(self):
        self.n_rows = max(n["row"] for n in self.nodes.values()) + 1
        self.n_cols = max(n["col"] for n in self.nodes.values()) + 1

        # columns carrying group members need room for the dashed boundary
        self.col_group_pad = {c: 0.0 for c in range(self.n_cols)}
        for g in self.groups:
            for mid in g["members"]:
                self.col_group_pad[self.nodes[mid]["col"]] = GROUP_PAD_X

        # column gap driven by the widest label on a same-row adjacent edge
        gap = {}
        for i in range(self.n_cols - 1):
            widest = 0.0
            for e in self.edges:
                if e.get("route") not in (None, "h", "step"):
                    continue
                a = self.endpoint_cell(e["from"])
                b = self.endpoint_cell(e["to"])
                if not a or not b:
                    continue
                # a group spans rows, so only compare rows when both are nodes
                if a[1] is not None and b[1] is not None and a[1] != b[1]:
                    continue
                lo, hi = sorted((a[0], b[0]))
                if lo != i or hi != i + 1 or not e.get("label"):
                    continue
                need = label_width(e["label"]) + LABEL_PAD
                # an edge leaving a dashed group starts at the group border, which is
                # GROUP_PAD_X further along, so it needs that much more room
                if a[1] is None or b[1] is None:
                    need += GROUP_PAD_X
                widest = max(widest, need)
            explicit = self.spec.get("colGap", {}).get(str(i))
            base = explicit if explicit else max(MIN_COL_GAP, widest)
            gap[i] = base + self.col_group_pad[i] + self.col_group_pad.get(i + 1, 0.0)

        self.col_x = {}
        x = PAD_L + self.col_group_pad[0]
        for c in range(self.n_cols):
            self.col_x[c] = x
            if c < self.n_cols - 1:
                x += NODE_W + gap[c]

        self.row_y = {r: PAD_T + r * (NODE_H + ROW_GAP) for r in range(self.n_rows)}

        # "above" edges run their trunk over the top of row 0, so row 0 has to be
        # pushed down far enough to fit every stacked lane plus its label
        above = [e.get("lane", 0) for e in self.edges if e.get("route") == "above"]
        if above:
            need = ABOVE_BASE + max(above) * ABOVE_STEP + TOPIC_DY + TOPIC_FS + 6
            if need > PAD_T:
                shift = need - PAD_T
                self.row_y = {r: y + shift for r, y in self.row_y.items()}

        for n in self.nodes.values():
            n["x"] = self.col_x[n["col"]]
            n["y"] = self.row_y[n["row"]]

        # group members are stacked and vertically centred across all rows
        rows_bottom = self.row_y[self.n_rows - 1] + NODE_H
        centre_y = (self.row_y[0] + rows_bottom) / 2.0
        for gi, g in enumerate(self.groups):
            members = g["members"]
            # stack=False: leave members where the grid put them and just draw the
            # bounding box, for grouping a horizontal chain (e.g. one container)
            if len(members) > 1 and g.get("stack", True):
                stack_h = len(members) * NODE_H + (len(members) - 1) * GROUP_MEMBER_GAP
                top = centre_y - stack_h / 2.0
                for k, mid in enumerate(members):
                    self.nodes[mid]["y"] = top + k * (NODE_H + GROUP_MEMBER_GAP)
            xs = [self.nodes[m]["x"] for m in members]
            ys = [self.nodes[m]["y"] for m in members]
            g["_box"] = (min(xs) - GROUP_PAD_X,
                         min(ys) - GROUP_PAD_Y,
                         (max(xs) + NODE_W) - min(xs) + 2 * GROUP_PAD_X,
                         (max(ys) + NODE_H) - min(ys) + 2 * GROUP_PAD_Y)
            g.setdefault("id", f"group{gi}")

        self.width = (self.col_x[self.n_cols - 1] + NODE_W
                      + self.col_group_pad[self.n_cols - 1] + PAD_R)
        self.height = rows_bottom + LEGEND_BAND

        # keep group titles from being clipped at the top
        tops = [g["_box"][1] for g in self.groups]
        need = GROUP_TITLE_DY + GROUP_TITLE_FS
        if tops and min(tops) - need < 4:
            shift = 4 + need - min(tops)
            for n in self.nodes.values():
                n["y"] += shift
            for r in self.row_y:
                self.row_y[r] += shift
            for g in self.groups:
                bx, by, bw, bh = g["_box"]
                g["_box"] = (bx, by + shift, bw, bh)
            self.height += shift

        self.base_lane = {r: (self.row_y[r] + NODE_H + self.row_y[r + 1]) / 2.0
                          for r in range(self.n_rows - 1)}

    # ------------------------------------------------------------ anchors
    def group_of(self, node_id):
        for g in self.groups:
            if node_id in g["members"]:
                return g
        return None

    def endpoint_cell(self, ref):
        """(col, row) for an edge endpoint; row is None for a group, which spans rows."""
        if ref in self.nodes:
            n = self.nodes[ref]
            return (n["col"], n["row"])
        for gi, g in enumerate(self.groups):
            if ref in (g.get("id", f"group{gi}"), g.get("title")):
                return (max(self.nodes[m]["col"] for m in g["members"]), None)
        return None

    def anchor(self, ref):
        if ref in self.nodes:
            n = self.nodes[ref]
            return {"x": n["x"], "y": n["y"], "w": NODE_W, "h": NODE_H,
                    "row": n["row"], "col": n["col"]}
        for g in self.groups:
            if ref in (g["id"], g.get("title")):
                bx, by, bw, bh = g["_box"]
                rows = [self.nodes[m]["row"] for m in g["members"]]
                return {"x": bx, "y": by, "w": bw, "h": bh,
                        "row": min(rows), "col": max(self.nodes[m]["col"] for m in g["members"])}
        raise KeyError(f"unknown edge endpoint: {ref}")

    # ------------------------------------------------------------ emit
    def add(self, s):
        self.out.append(s)

    def rect(self, x, y, w, h, fill, stroke=None, rx=None, dash=None, sw=None):
        a = [f'x="{fmt(x)}"', f'y="{fmt(y)}"', f'width="{fmt(w)}"', f'height="{fmt(h)}"']
        if rx:
            a += [f'rx="{fmt(rx)}"', f'ry="{fmt(rx)}"']
        a.append(f'fill="{fill}"')
        a.append(f'stroke="{stroke}"' if stroke else 'stroke="none"')
        if sw:
            a.append(f'stroke-width="{fmt(sw)}"')
        if dash:
            a.append(f'stroke-dasharray="{dash}"')
        self.add(f'<rect {" ".join(a)}/>')

    def text(self, x, y, s, size, fill, anchor="middle", bold=False):
        w = ' font-weight="bold"' if bold else ""
        self.add(f'<text x="{fmt(x)}" y="{fmt(y)}" font-family="{FONT}" '
                 f'font-size="{fmt(size)}" fill="{fill}" text-anchor="{anchor}"{w}>'
                 f'{esc(s)}</text>')

    def block_text(self, cx, cy, lines, size, fill, line_h=None, bold=False):
        lh = line_h or size * 1.2
        first = cy - (len(lines) - 1) * lh / 2.0 + size * BASELINE
        for i, ln in enumerate(lines):
            self.text(cx, first + i * lh, ln, size, fill, bold=bold)

    def polyline(self, pts, dashed=False, head_end=True, head_start=False):
        pts = [list(p) for p in pts]
        heads = []
        if head_end:
            heads.append(self._trim(pts, -1))
        if head_start:
            heads.append(self._trim(pts, 0))
        d = "M " + " L ".join(f"{fmt(x)} {fmt(y)}" for x, y in pts)
        dash = ' stroke-dasharray="3 3"' if dashed else ""
        self.add(f'<path d="{d}" fill="none" stroke="#000000" stroke-miterlimit="10"{dash}/>')
        for h in heads:
            self.add(h)

    def _trim(self, pts, end):
        """Shorten the polyline at `end` by ARROW_LEN; return the arrowhead path."""
        tip, prev = (pts[-1], pts[-2]) if end == -1 else (pts[0], pts[1])
        dx, dy = tip[0] - prev[0], tip[1] - prev[1]
        ln = (dx * dx + dy * dy) ** 0.5 or 1.0
        ux, uy = dx / ln, dy / ln
        bx, by = tip[0] - ux * ARROW_LEN, tip[1] - uy * ARROW_LEN
        px, py = -uy * ARROW_HALF, ux * ARROW_HALF
        pts[-1 if end == -1 else 0] = [bx, by]
        return (f'<path d="M {fmt(tip[0])} {fmt(tip[1])} L {fmt(bx + px)} {fmt(by + py)} '
                f'L {fmt(bx - px)} {fmt(by - py)} Z" fill="#000000" stroke="#000000" '
                f'stroke-miterlimit="10"/>')

    # ------------------------------------------------------------ routing
    def route(self, e):
        a, b = self.anchor(e["from"]), self.anchor(e["to"])
        acy, bcy = a["y"] + a["h"] / 2, b["y"] + b["h"] / 2
        acx = a["x"] + a["w"] / 2 + e.get("exitDx", 0.0)
        bcx = b["x"] + b["w"] / 2 + e.get("enterDx", 0.0)
        lane_off = e.get("lane", 0) * LANE_STEP
        mode = e.get("route")

        if mode is None:
            if abs(acy - bcy) < 1.0:
                mode = "h"
            elif abs(acx - bcx) < 1.0:
                mode = "v"
            elif b["row"] > a["row"]:
                mode = "wrap"
            elif b["row"] < a["row"]:
                mode = "wrapup"
            else:
                mode = "step"

        # a straight horizontal run is only valid when both boxes share a centre
        # line; group members are re-centred vertically, so step around instead
        if mode == "h" and abs(acy - bcy) > 1.0:
            mode = "step"

        if mode == "h":
            if b["x"] > a["x"]:
                pts = [(a["x"] + a["w"], acy), (b["x"], bcy)]
            else:
                pts = [(a["x"], acy), (b["x"] + b["w"], bcy)]
            return pts, ((pts[0][0] + pts[1][0]) / 2, acy - TOPIC_DY, "middle")

        if mode == "v":
            if b["y"] > a["y"]:
                pts = [(acx, a["y"] + a["h"]), (bcx, b["y"])]
            else:
                pts = [(acx, a["y"]), (bcx, b["y"] + b["h"])]
            return pts, (acx + 8, (pts[0][1] + pts[1][1]) / 2, "start")

        if mode == "step":
            # out the side, across the gap at a mid-x, then into the target's side
            if b["x"] >= a["x"] + a["w"]:
                sx_, ex = a["x"] + a["w"], b["x"]
            else:
                sx_, ex = a["x"], b["x"] + b["w"]
            # leave from the dashed group boundary rather than from inside it
            if e.get("fromGroupEdge"):
                g = self.group_of(e["from"])
                if g:
                    gx, _, gw, _ = g["_box"]
                    sx_ = gx + gw if b["x"] >= a["x"] + a["w"] else gx
            mx = (sx_ + ex) / 2 + lane_off
            # The label is centred over the first horizontal run, so that run has to be
            # long enough to hold it. Push the riser away from the source until it fits
            # (draw.io does the same by hand in the reference diagram), then warn only
            # if even the full column gap is too narrow.
            if e.get("label") and not lane_off:
                half = label_width(e["label"]) / 2 * 1.12   # slack for font fallback
                need = 2 * half + 20
                if ex > sx_:
                    mx = min(max(mx, sx_ + need), ex - 24)
                else:
                    mx = max(min(mx, sx_ - need), ex + 24)
                if abs(mx - sx_) < need - 0.5:
                    self.warnings.append(
                        f'label "{e["label"]}" does not fit before its riser on '
                        f'{e["from"]}->{e["to"]}: widen colGap for that column')
            pts = [(sx_, acy), (mx, acy), (mx, bcy), (ex, bcy)]
            return pts, ((sx_ + mx) / 2, acy - TOPIC_DY, "middle")

        lane_row = min(a["row"], b["row"])
        if mode == "wrap":
            lane = self.base_lane.get(lane_row, acy + NODE_H) + lane_off
            pts = [(acx, a["y"] + a["h"]), (acx, lane), (bcx, lane), (bcx, b["y"])]
            return pts, ((acx + bcx) / 2, lane - TOPIC_DY + 2, "middle")

        if mode == "wrapup":
            lane = self.base_lane.get(lane_row, acy - NODE_H) + lane_off
            pts = [(acx, a["y"]), (acx, lane), (bcx, lane), (bcx, b["y"] + b["h"])]
            return pts, ((acx + bcx) / 2, lane - TOPIC_DY + 2, "middle")

        if mode == "under":
            lane = self.row_y[self.n_rows - 1] + NODE_H + 22 + lane_off
            pts = [(acx, a["y"] + a["h"]), (acx, lane), (bcx, lane), (bcx, b["y"] + b["h"])]
            return pts, ((acx + bcx) / 2, lane + 14, "middle")

        if mode == "below":
            # drop into the inter-row lane, run sideways, then come back up into
            # the target's bottom edge - for same-row feeds that must skip a box
            lane = self.base_lane.get(a["row"], a["y"] + a["h"] + 40) + lane_off
            pts = [(acx, a["y"] + a["h"]), (acx, lane), (bcx, lane), (bcx, b["y"] + b["h"])]
            return pts, ((acx + bcx) / 2, lane - TOPIC_DY + 2, "middle")

        if mode == "above":
            # trunk routed over the top of row 0: out the top, across, back down into
            # the target's top. Keeps a fan-out clear of everything below the chain,
            # so output edges leaving the same row never cross it.
            lane = self.row_y[0] - ABOVE_BASE - e.get("lane", 0) * ABOVE_STEP
            pts = [(acx, a["y"]), (acx, lane), (bcx, lane), (bcx, b["y"])]
            return pts, ((acx + bcx) / 2, lane - TOPIC_DY, "middle")

        raise ValueError(f"unknown route {mode}")

    # ------------------------------------------------------------ draw
    def render(self):
        self.layout()
        self.add(f'<svg xmlns="http://www.w3.org/2000/svg" '
                 f'xmlns:xlink="http://www.w3.org/1999/xlink" version="1.1" '
                 f'width="{fmt(self.width)}px" height="{fmt(self.height)}px" '
                 f'viewBox="-0.5 -0.5 {fmt(self.width)} {fmt(self.height)}" '
                 f'style="background-color: transparent;">')
        self.add("<defs/>")
        self.add("<g>")

        self.rect(1, 1, self.width - 2, self.height - 2, "#fafafa", "#d2d7e1", rx=6, sw=2)

        for g in self.groups:
            gx, gy, gw, gh = g["_box"]
            self.rect(gx, gy, gw, gh, "none", "#000000", dash="3 3")
            if g.get("title"):
                self.text(gx + gw / 2, gy - GROUP_TITLE_DY + GROUP_TITLE_FS * BASELINE,
                          g["title"], GROUP_TITLE_FS, "#000000")
            if g.get("innerLabel") and len(g["members"]) > 1:
                m0, m1 = self.nodes[g["members"][0]], self.nodes[g["members"][1]]
                cy = (m0["y"] + NODE_H + m1["y"]) / 2
                self.text(m0["x"] + NODE_W / 2, cy + TOPIC_FS * BASELINE,
                          g["innerLabel"], TOPIC_FS, "#000000")

        # edges first so that boxes always sit on top of any line
        for e in self.edges:
            pts, (lx, ly, anch) = self.route(e)
            self.polyline(pts, dashed=e.get("dashed", False),
                          head_end=True, head_start=e.get("bidirectional", False))
            lines = label_lines(e.get("label"))
            for i, ln in enumerate(lines):
                dy = -(len(lines) - 1 - i) * NODE_LINE_H
                self.text(lx + e.get("labelDx", 0.0),
                          ly + e.get("labelDy", 0.0) + dy + TOPIC_FS * BASELINE,
                          ln, TOPIC_FS, "#000000",
                          anchor=e.get("labelAnchor", anch))

        for nid in self.order:
            n = self.nodes[nid]
            k = KINDS[n["kind"]]
            self.rect(n["x"], n["y"], NODE_W, NODE_H, k["fill"], rx=NODE_RX)
            self.block_text(n["x"] + NODE_W / 2, n["y"] + NODE_H / 2,
                            n["lines"], NODE_FS, k["text"], line_h=NODE_LINE_H)

        self.legend()
        self.add("</g>")
        self.add("</svg>")
        return "\n".join(self.out)

    def legend(self):
        used = [k for k in LEGEND_ORDER if any(n["kind"] == k for n in self.nodes.values())]
        overrides = self.spec.get("legendLabels", {})
        entries = [(k, overrides.get(k, KINDS[k]["legend"])) for k in used]
        if not entries:
            return
        sw = 22.0
        widths = [sw + 5 + text_width(lab, LEGEND_FS, bold=True) for _, lab in entries]
        total = sum(widths) + 30.0 * (len(entries) - 1)
        x = self.width - PAD_R - total
        cy = self.height - 27.0
        for (k, lab), w in zip(entries, widths):
            spec = KINDS[k]
            self.rect(x, cy - sw / 2, sw, sw, spec["fill"],
                      stroke="#b9c0cf" if spec["fill"] == "#d2d7e1" else None, rx=4)
            self.text(x + sw + 5, cy + LEGEND_FS * BASELINE, lab, LEGEND_FS,
                      "#000000", anchor="start", bold=True)
            x += w + 30.0


def main():
    spec = json.load(open(sys.argv[1], encoding="utf-8"))
    r = Renderer(spec)
    svg = r.render()
    open(sys.argv[2], "w", encoding="utf-8").write(svg + "\n")
    # guard: box text must fit inside the 151px box, else the label bleeds out
    over = []
    for n in spec["nodes"]:
        for ln in n["lines"]:
            w = text_width(ln, NODE_FS)
            if w > NODE_W - 10:
                over.append(f'    {n["id"]}: "{ln}" is {w:.0f}px (max {NODE_W - 10:.0f})')
    if len(spec["nodes"]) and any(len(n["lines"]) * NODE_LINE_H > NODE_H - 6 for n in spec["nodes"]):
        over.append("    a box has too many lines for its 72px height")
    print(f"{sys.argv[2]}: {len(svg)} bytes")
    for w in r.warnings:
        print(f"  LABEL COLLISION: {w}")
    if over:
        print("  TEXT OVERFLOW:")
        print("\n".join(over))


if __name__ == "__main__":
    main()
