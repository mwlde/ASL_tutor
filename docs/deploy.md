# Deploying to Cloudflare Pages

## What can actually go on Pages

Cloudflare Pages serves static files. It cannot run the tutor as it exists
today: `src/` is a desktop Python app that needs a local webcam, TensorFlow,
and MediaPipe's Python wheels. None of that survives a static host.

What builds and deploys right now is **`design/`** — the React app, published
as an **interactive demo** of the desktop tutor. The screens are real, the
navigation works, and the 24 reference hand shapes are the genuine ones loaded
from `reference_poses.json`. What is not live are the readings: the CNN
confidence and match percentages are sample values, because a static page has
no camera and no model behind it.

That is disclosed rather than hidden:

- A **Demo** chip sits over the camera area on every screen, next to a line
  saying the real app draws your webcam there.
- Each side panel carries a short "What you are seeing" note explaining that
  screen and which parts are standing in for live data.
- An **About** page (fifth item in the rail, and linked from the home screen)
  explains what the page is, why the real app needs a camera, how the
  two-signal scoring works, and what the project leaves out.

The remaining step is the real browser port, which replaces the sample values
with live ones — see the checklist below.

## Build settings

In the Cloudflare dashboard: **Workers & Pages → Create → Pages → Connect to
Git**, pick this repo, then set:

| Setting | Value |
|---|---|
| Framework preset | None (or Vite) |
| Build command | `pnpm build` |
| Build output directory | `dist` |
| Root directory | `design` |
| Node version | 22 (from `design/.node-version`) |

**Root directory is the setting people miss.** This repo is a Python project
with a web app inside it; without it Cloudflare looks at the repo root, finds
no `package.json` worth building, and fails.

Production branch: pick `main` if you only want merged work published, or `dev`
if you want every push previewed. Every branch gets its own preview URL either
way.

## Deploying by hand

```bash
cd design
pnpm install
pnpm build
npx wrangler pages deploy      # reads design/wrangler.toml
```

`wrangler.toml` names the project `asl-tutor` and points at `dist`.

## What is already set up

- **`design/.figma/make/site.json`** — the browser tab says **ASL Tutor**; also
  carries the meta description, the Open Graph tags, and `robots.index: true`
  (it shipped as `false`, which would have kept the site out of search).
- **`design/public/_headers`** — long cache on hashed assets, revalidate on
  everything else, plus `nosniff`, `Referrer-Policy`, `X-Frame-Options`, and a
  `Permissions-Policy` that allows `camera=(self)`. That last one is what will
  let the browser port ask for a webcam at all.
- **`design/public/_redirects`** — SPA fallback, so any path renders the app.
- **`design/.node-version`** — pins the build image to Node 22.
- **`design/public/data/reference_poses.json`** — the 24 reference shapes,
  exported from `results/models/reference_poses.json` (8 KB; only the geometry,
  without the build-time QA fields). Regenerate it whenever the reference poses
  are rebuilt. This is also step 3 of the port checklist, already done.

## The favicon

`design/public/favicon.png`, `apple-touch-icon.png`, and `og.png` are
**placeholders**, drawn from the app's own theme (the graduation cap on the
yellow tile) so the site is not iconless before real artwork exists.

Drop your own files over them — same names, same folder — and rebuild. Nothing
regenerates them behind your back. To redraw the placeholders after a palette
or title change:

```bash
.venv311/bin/python -m scripts.make_web_icons
```

Recommended sizes: favicon 512×512 PNG, apple touch icon 180×180, social card
1200×630.

## Checklist for the real browser port

The port is the roadmap's highest-leverage post-MVP item, and `design/` is
already the right shell for it — the six screens are laid out, so the work is
replacing mocked values with live ones rather than starting from a blank page.

1. **Convert the classifier to TensorFlow.js.** The model is small (1.4 MB), so
   it will load fast over the wire:
   ```bash
   pip install tensorflowjs
   tensorflowjs_converter --input_format=keras \
     results/models/best_model.h5 design/public/model/
   ```
   Then `tf.loadLayersModel('/model/model.json')` in the browser.
2. **Swap in MediaPipe's JS HandLandmarker** (`@mediapipe/tasks-vision`) for
   `src/hand_tracking.py`. Same 21 landmarks, same normalized coordinates.
3. ~~**Copy the reference data across.**~~ Done — the demo already loads
   `design/public/data/reference_poses.json` and draws the real shapes.
   `class_names.json` still needs copying for the classifier's output order.
4. **Port the pure logic**, which is small and has no Python dependencies:
   `normalize_pose`, `per_joint_distances`, `similarity`, `worst_fingers`
   (`src/tutor/reference.py`), and the crop-to-content preprocessing
   (`src/preprocessing.py`). These must stay numerically identical to the
   Python versions or the scores will drift from the ones documented here.
5. **Render the skeleton, ghost, and joint tinting to a `<canvas>`** over the
   video element, replacing `src/skeleton.py`.
6. **Keep the camera copy honest.** The Python app promises frames are read and
   discarded. In the browser that is enforced by never sending them anywhere —
   no fetch, no upload. Say so on the page, since visitors cannot inspect it.
7. **Drop the sample values** as each screen goes live, and take down the
   Demo chip and the "standing in for your hand" notes with them, so the
   deployed site never mixes real readings with placeholder ones.

One thing to preserve when porting the rendering: the hand's bone topology is
MediaPipe's, where the palm is a chain across the knuckles (5-9-13-17) rather
than a fan of spokes from the wrist. Drawn as a fan, a closed fist reads as an
open hand — the letter A is the obvious tell. `BONES` in `design/src/App.tsx`
and `_PALM_CONNECTIONS` in `src/skeleton.py` must agree.

Everything in steps 3–4 is deliberately dependency-free Python — it was written
that way so this port would be a translation rather than a redesign.
