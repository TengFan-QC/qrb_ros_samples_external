---
name: qrb-ros-pipeline-diagram
description: Generate or regenerate a QRB ROS "pipeline flow" diagram as an SVG for the qir-sdk2.0-user-guide docs, in the ga1.6-hand-detection house style, with the graph derived from the upstream ROS 2 launch files rather than from the doc's own tables. Use when asked to create, regenerate, restyle, or fix a pipeline/dataflow figure for a QRB ROS sample or component page, or to review such a page's ROS node/topic tables against upstream source.
---

# QRB ROS pipeline diagrams

Produces the pipeline figures for `qir-sdk2.0-user-guide` (Mintlify MDX, media under
`media/80-65220-2-qirp-sdk-qsg/`).

Two things make a figure here acceptable, and they are separate problems:

1. **Correctness** — the graph must come from the upstream launch files, not the doc tables.
   Every page checked so far had at least one topic name that does not exist at runtime.
2. **Style** — it must match `ga1.6-hand-detection.svg` exactly.

Solve them separately. You write a JSON **spec** (the semantics); a calibrated renderer produces
the SVG (the geometry). **Never hand-write SVG** — it yields misaligned arrows and spacing that
drifts between figures.

## Workflow

### 1. Read the page
Its ROS nodes table, ROS topics table, the prose describing the flow, and — most importantly —
the actual `ros2 launch` command in "Run out-of-the-box". Note the current figure and what it
claims.

### 2. Establish ground truth
Read `references/ground-truth.md` and follow it. In short: fetch the launch file named by the
documented command **at the ref the page tells the reader to clone**, plus the node sources it
references, and resolve every remapping and namespace. `WebFetch` is blocked; use `curl` / `gh`.

Do not skip this even when the doc looks self-consistent. Record every discrepancy as a doc issue
with `file:line` and the upstream snippet that proves it.

### 3. Write the spec
Read `references/spec-schema.md` for the format, the route modes, and the routing gotchas —
the gotchas list is the accumulated bug history and will save you a rendering round-trip.
Read `references/design-system.md` for the kinds and the layout idiom.

Start from a worked example in `references/examples/` that resembles your case:

| Example | Shape |
| :- | :- |
| `_reference-hand-detection.json` | the canonical reference figure, reproduced |
| `resnet101.json`, `depth.json` | dashed "or" provider group, single input edge |
| `objdet.json`, `objseg.json` | 4-column row 0 + a side-feed that must not cross the wrap |
| `apriltag.json` | `above` trunk lanes for a fan-out to two consumers |
| `video.json` | two independent pipelines, `stack: false` container groups |
| `audio.json`, `colorspace.json` | bidirectional edges, internal modules, external app |

### 4. Render and audit
```bash
S=~/.claude/skills/qrb-ros-pipeline-diagram/scripts
python3 $S/render.py spec.json out.svg      # warns on label collisions and text overflow
python3 $S/audit.py out.svg                 # crossings, labels on lines, overflow, XML
```

`audit.py` exits non-zero on any finding, so it is a gate, not advice. Both must be clean.

### 5. Look at it
```bash
python3 -c "import cairosvg; cairosvg.svg2png(url='out.svg', write_to='out.png', scale=1.5, background_color='white')"
```
Then Read the PNG. The audit catches geometry, not sense — only your eyes catch a diagram that
is technically clean and still reads wrong (e.g. a provider group that appears to feed a pipeline
it has nothing to do with). Iterate until it reads correctly.

### 6. Install
- Name it **`<original-image-basename>-regenerate.svg`**, whatever the original extension was.
- **Never overwrite an existing file**; assert the destination does not exist first.
- Do not change the `.mdx` `<img src>` unless asked — the suffix exists so the new figure can be
  compared with the old one.

## House rules

These keep new figures consistent with the eight already shipped.

1. **Label a box with the launch file's node instance name on line 1 and the owning package or
   plugin in parentheses below** — `yolo_preprocess_node` / `(qrb_ros_cv_tensor_` /
   `common_process)`. Not abbreviations, not package-only, not invented names.
2. **No `rqt` / `rviz2` / `Rviz` boxes.** The reference ends at a black terminal topic box. This
   also sidesteps the rqt-vs-rviz2 ambiguity several pages have.
3. **Dashed groups only for genuinely interchangeable inputs** (the "Image raw data provider" /
   "or" idiom) or, with `stack: false`, to bound one container's chain. Do not wrap a
   `component_container` around a single chain just to show composition — note it in prose.
4. **The arrow into a terminal topic box carries no label** — the box already is the name.
5. **Show fully-qualified topic names**, including namespace prefixes, even when long.
6. **Zero line crossings.** They are always avoidable; see the gotchas.
7. Keep the legend to the kinds actually present; override wording with `legendLabels`.

## When the figure and the tables disagree

The figure will be right and the page's own tables wrong. Say so explicitly and offer to fix the
tables — a correct figure next to a contradictory table is worse than either alone. Grep the repo
for each topic name: `explore-the-available-apis.mdx` mirrors the per-sample tables and needs the
same corrections.

## Cost

Working one page at a time is normal. Upstream fetching plus visual iteration is token-heavy; a
7-page batch with independent adversarial verification exhausted a daily cost allowance once. Do
not fan out large numbers of parallel agents unless asked.

## Pages already done

`resnet101`, `depth-estimation`, `object-detection`, `object-segmentation`, `apriltag`,
`colorspace-convert`, `audio-service`, `qrb_ros_video`. `detect-faces` and
`estimate-human-poses` already ship `ga1.6-*.drawio.svg` figures in the target style — leave
them alone. Still on old-style figures: `qrb-ros-camera`, `nn-inference`, `ocr-service`,
`system-monitor`, `orbbec-camera`, `rplidar-ros2`, and the four simulation pages.
