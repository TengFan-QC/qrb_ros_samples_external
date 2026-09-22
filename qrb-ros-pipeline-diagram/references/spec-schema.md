# Spec format and routing

`render.py` takes a JSON spec and emits SVG. You write the spec; you never write SVG.

## Schema

```jsonc
{
  "_doc":  "which-page.mdx",                  // free-form provenance, ignored by the renderer
  "_out":  "<original-basename>-regenerate.svg",
  "_note": "why the graph looks like this",

  "nodes": [
    { "id": "camera",                                   // short stable slug
      "lines": ["camera_node", "(qrb_ros_camera)"],     // each line <= ~141 px wide
      "kind": "qualcomm",                               // see design-system.md
      "row": 0, "col": 0 }                              // 0-based; cols contiguous per row
  ],

  "edges": [
    { "from": "camera", "to": "preprocess",
      "label": "/cam0_stream1",         // "" for none; or ["line 1","line 2"] to stack
      "route": "wrap",                  // optional, auto-detected when omitted
      "lane": -1,                       // optional lane offset (x22 px, or x34 for "above")
      "exitDx": 40, "enterDx": -36,     // shift where the edge leaves / lands
      "labelDx": -150, "labelDy": -28,  // nudge the label clear of something
      "labelAnchor": "start",
      "bidirectional": true, "dashed": false,
      "fromGroupEdge": true }           // start at the dashed group border, not inside a box
  ],

  "groups": [
    { "id": "provider", "title": "Image raw data provider",
      "members": ["image_publisher", "camera"],
      "innerLabel": "or",               // small label between two stacked members
      "stack": false }                  // false = don't restack; just bound a horizontal chain
  ],

  "legendLabels": { "external": "Your ROS node" },   // optional per-kind override
  "colGap": { "0": 400 }                             // optional manual column gap in px
}
```

## Route modes

Omit `route` and it is inferred. Set it explicitly when the inference is wrong.

| Mode | Shape | Use for |
| :- | :- | :- |
| `h` | straight horizontal | same row, adjacent columns |
| `v` | straight vertical | same column, adjacent rows |
| `step` | out the side, across at a mid-x, into the target's side | endpoints at different heights (e.g. leaving a group) |
| `wrap` | down / across / down into the target's **top** | the serpentine turn |
| `wrapup` | up / across / up into the target's **bottom** | a feed from a lower row |
| `below` | into the inter-row lane, sideways, back up into the target's **bottom** | a same-row feed that must skip over a box |
| `under` | below the last row | a long return path |
| `above` | out the **top**, across a trunk lane over row 0, down into the target's **top** | a fan-out to several consumers in row 0 |

## Routing gotchas

Each of these produced a defect that shipped at least once.

**Two arrows landing on one box overlap at its top centre.** Separate them with `enterDx`
(e.g. `-36` and `+36`) and give them different `lane` values.

**Group members are re-centred vertically**, so a same-row `h` edge from one comes out slanted.
The renderer auto-promotes it to `step`; add `fromGroupEdge: true` so the line starts at the
dashed border rather than inside the box.

**A `v` edge with only `exitDx` set draws a diagonal.** Set `exitDx` and `enterDx` to the same
value.

**Two providers publishing different topics should share one riser.** Give both edges the same
`lane` so they meet in a T-junction and a single arrow enters the consumer — the alternative
(different lanes) leaves a visible staggered stub. Better still, if the consumer really has one
subscription that is merely remapped per launch file, emit **one** edge from the group with a
stacked two-line label.

**A fan-out in a two-row grid always crosses the output edges.** If one node feeds several
consumers in row 0 while also driving outputs into row 1, route the fan-out with `above`. In the
`above` lanes, the **higher lane must leave further left** (`exitDx: -38` vs `+38`), or its riser
cuts through the lower lane's horizontal run.

**A row-0 to row-1 feed crosses the serpentine wrap** when the wrap spans the full width. A
4-column row 0 fixes it: the feed's column then sits at the left end of the wrap's span, so
offsetting the two entry points (`enterDx` `+36` on the wrap, `-36` on the feed) separates them.

**The inter-row band is only 80 px** — about three lanes (`-1`, `0`, `1`).

**Long labels need column room.** The renderer sizes columns from the widest label on a
same-row adjacent edge and pushes a `step` riser back until its label fits, but a very long
namespaced topic can still need an explicit `colGap`. It warns when it cannot fit.
