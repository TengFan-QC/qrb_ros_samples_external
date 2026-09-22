# Establishing ground truth

A pretty diagram that repeats the doc's mistakes is worse than no diagram, because it looks
authoritative. **The launch file is the source of truth. The doc tables are not.**

Across eight pages of `qir-sdk2.0-user-guide`, every single one had at least one topic name that
did not exist at runtime.

## Network access

`WebFetch` is blocked for `raw.githubusercontent.com` in this environment. Use the shell:

```bash
curl -sS --max-time 30 https://raw.githubusercontent.com/<owner>/<repo>/<ref>/<path>
gh api repos/<owner>/<repo>/git/trees/<ref>?recursive=1 --jq '.tree[].path'   # list a tree
gh api "repos/<o>/<r>/contents/<path>?ref=<ref>" --jq '.content' | base64 -d  # slash in ref
```

`gh` is installed and authenticated. Unauthenticated `api.github.com` gets rate-limited (403).

## Use the ref the page tells the reader to clone

Check the page for `git clone -b <ref>` or a `stable-*` / `stable/*` ref in its Note block, and
read **that** ref, not `main`. When they differ, `main` is the wrong answer. If a path 404s, list
the parent tree to find the real path rather than guessing.

Confirm whether the ref actually differs before reporting a discrepancy:

```bash
gh api "repos/o/r/contents/path?ref=stable/0.1.7" --jq '.content' | base64 -d > a.py
curl -sS https://raw.githubusercontent.com/o/r/main/path > b.py
diff a.py b.py
```

## What to extract from a launch file

1. **Every `remappings=[(from, to)]` pair.** This is where real topic names come from. A node's
   `create_publisher("output", ...)` means nothing until you apply the remap.
2. **Every `namespace=`** on a node or `ComposableNodeContainer`. It prefixes every *relative*
   topic that node publishes or subscribes to.
3. **Relative vs absolute in the node source.** `create_subscription(Image, 'topic', ...)` is
   namespaced; `'/topic'` escapes the namespace. Both appear in the same file in real samples —
   `sample_depth_estimation` namespaces `cam0_stream1` but not `/image_raw`.
4. **Which nodes this launch file actually instantiates.** A node in the repo is not necessarily
   in this pipeline. `sample_resnet101`'s doc listed 2 of its 4 nodes.
5. **Whether a viewer (`rviz2`, `rqt`) is launched** or merely suggested in prose. Usually the
   latter — do not draw it.
6. **Whether two launch files are actually one pipeline.** `qrb_ros_video` ships
   `encoder_launch.py` and `decoder_launch.py` that create two *independent* containers in
   different namespaces; the doc's diagram wrongly linked them.
7. **`url` / file-path parameters**, which often answer open TODOs in the doc.

## Recurring doc defects

Search for these specifically. Every one was a real finding.

- A camera topic copied from a different launch variant (`/camera/color/image_raw` belongs to the
  Orbbec variant; the `qrb_ros_camera` path publishes `/cam0_stream1`).
- **"Published By" swapped** between an inference node and a post-process node, inverting the
  pipeline direction. Found on two sibling pages.
- A namespace missing from every topic in a table while a command elsewhere on the page uses the
  namespaced name.
- Pre-remap relative names (`/input`, `/output`) documented as if they were runtime topics.
- A node's **second publisher** omitted, where a downstream node exact-time-synchronizes two
  inputs — the graph becomes unexplainable, and it is the most common runtime failure.
- Message types that do not exist (`sensor_msgs.msg.String`) or lack the needed fields
  (`vision_msgs/msg/Detection2DArray` for a segmentation mask).
- Wrong `*_msgs` package (`qrb_ros_audio_common_msgs` vs `qrb_ros_audio_service_msgs`).
- Parameter names with `_` where the node reads `-` (`pixel_format` vs `pixel-format`).
- Node table, topic table, and figure using three different vocabularies for the same node.
- Repo links to a monorepo root, hiding which of two packages a node belongs to; links containing
  `/edit/` (broken).
- `ROS_DOMAIN_ID` exported on the device but not in the host-side verification step.
- A verify command pointed at a topic that does not exist, so it silently produces nothing.
- Backend claims contradicting the launch file (page says QNN, launch loads `.tflite` with
  `backend_option` empty).

## Reporting

For every issue give **severity, `file:line`, the problem, the exact correction, and the upstream
file plus snippet that proves it.** No unevidenced claims. If you cannot prove it, say so.

## Mirror pages

Corrections often need to land in more than one place. `explore-the-available-apis.mdx` duplicates
the per-sample topic tables; fixing only the sample page leaves the guide contradicting itself.
Grep the whole repo for a topic name before considering it fixed.
