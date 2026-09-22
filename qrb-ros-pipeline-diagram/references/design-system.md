# The QRB ROS pipeline-diagram design system

Every constant here was measured from `media/80-65220-2-qirp-sdk-qsg/ga1.6-hand-detection.svg`
in the `qir-sdk2.0-user-guide` repo — a draw.io export that is the canonical reference figure
(used by `detect-hands-with-sample-hand-detection.mdx`).

> That file is ~1.8 MB because it embeds a 19-page mxfile in its `content="..."` attribute plus
> base64 PNG text fallbacks. Do not `Read` it whole. Strip everything up to the end of the
> `content` attribute, then strip base64 payloads, and you are left with ~20 KB of real markup.

## Canvas

| Property | Value |
| :- | :- |
| Panel | `<rect x=1 y=1 width=W-2 height=H-2 rx=6 ry=6 fill="#fafafa" stroke="#d2d7e1" stroke-width="2"/>` |
| Padding | left 34, right 34, top 31.5 |
| Legend band | 66 px reserved below the last row |

## Boxes

All boxes are `151 x 72`, `rx=4`, **solid fill, no stroke** (measured 150.97 x 71.67).

| Kind | Fill | Text | Legend label |
| :- | :- | :- | :- |
| `qualcomm` | `#6280cc` | `#FFFFFF` | ROS node |
| `opensource` | `#007aa4` | `#FFFFFF` | Open-source ROS node |
| `topic` | `#000000` | `#FFFFFF` | topic |
| `module` | `#7c8aa3` | `#FFFFFF` | Internal module |
| `external` | `#d2d7e1` | `#000000` | Application |

Box label: 12 px Roboto, centred, line-height 1.2 (14.4 px). Baseline offset is `0.36 * fontSize`
below the vertical centre of the line.

## Edges

- 1 px solid black orthogonal polyline, `stroke-miterlimit="10"`, `fill="none"`.
- Arrowhead: solid black filled triangle, 7 long x 7 wide, and the polyline is **trimmed** by 7
  so the line does not poke through the tip.
- Topic name: **plain black 12 px text, never in a box**, centred 16 px above the line.

## Grid

| Property | Value |
| :- | :- |
| Row pitch | 152.29 (72 box + 80 gap) |
| Column pitch | `151 + max(96, widest_label + 52)` |
| Group padding | 20.13 horizontal, 17.9 vertical around members |
| Group member gap | 26.87 |
| Group title | 15 px black, centred, 23 px above the dashed rect |

Trunk lanes for `above` routes: first lane 30 px above row 0, then **34 px** per extra lane.
34 is not arbitrary — a lane's label sits 16 px above its line and is 12 px tall, so anything
under ~30 puts the lower trunk's label on top of the trunk above it.

## Legend

Bottom right: 22 x 22 `rx=4` swatches + **bold** 11 px black labels, 5 px between swatch and
label, 30 px between entries, right edge 34 px from the canvas edge. Only the kinds actually
present appear.

## Layout idiom

A **serpentine**: row 0 reads left-to-right, the flow wraps down-and-across-and-down, and row 1
*also* reads left-to-right. 3–4 columns per row, never more than 4.

## Self-test

Feed the reference's own graph (`examples/_reference-hand-detection.json`) through the renderer.
You should get roughly `1305 x 323` against the original's `1246 x 322` (within ~5%). A wildly
different number means the renderer has been modified — investigate before trusting it.

## Do not use draw.io output

Emit plain `<text>` with `font-family="Roboto, Helvetica, Arial, sans-serif"`. This keeps files
around 6 KB instead of 1.8 MB, renders identically in browsers, and can be rasterized by
cairosvg for visual checking. `foreignObject` cannot be rasterized and `audit.py` rejects it.
