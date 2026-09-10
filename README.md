# ASL Fingerspelling Tutor

A realtime American Sign Language fingerspelling tutor built on a webcam and a
small CNN. Sign a letter, get graded feedback on which fingers are off; spell a
word, hold each sign to commit it. Static alphabet only (J and Z are motion
signs and are excluded).

> Demo GIF goes here once recorded.

## What it does

Three modes, all running on the same webcam + MediaPipe + CNN pipeline:

- **Teach.** Shows a target letter with a ghost skeleton of the correct pose
  overlaid on your hand, and rings each joint mint/yellow/pink by how far off
  it is. A closeness bar and a progress grid across the alphabet track how you
  are doing. Advances to the next letter when you hold the correct sign.
- **Practice.** Free-signing with the classifier reading whatever you sign.
  Shows the CNN prediction and confidence, plus the geometric closeness to
  the nearest reference pose. A rolling history of recent letters at the
  bottom.
- **Spell a word.** Prompts you with a word, one letter at a time. Hold each
  sign for ~1.5 seconds to commit it. Progress bar across the top shows
  what's done and what's next.

## How it works

The recognizer is **skeleton-based**. Each webcam frame:

1. **OpenCV** captures the frame.
2. **MediaPipe Tasks HandLandmarker** detects the 21 hand landmarks
   (`src/hand_tracking.py`).
3. **`src/skeleton.py`** renders those landmarks as a colored skeleton on
   black, then normalizes it (crop-to-content + square-pad) so hand position
   and scale don't matter.
4. **A small Keras CNN** classifies the skeleton into one of the 24 letters.
5. A short prediction-history buffer smooths the label across frames.

The classifier throws away skin tone, lighting, and background before it ever
sees the hand, which is why it generalizes to a live webcam despite being
trained on drawn skeletons.

**The tutor** adds a second signal on top of the CNN: geometric distance
between the live hand landmarks and a stored per-letter reference pose. The
CNN acts as a pass/fail gate; the geometric distance drives the graded
closeness bar and the per-finger feedback ("your ring finger is off"). See
[docs/scoring.md](docs/scoring.md) for the two-signal design (coming).

## Quick start

```bash
# one-time setup (Python 3.11 required for MediaPipe/TensorFlow wheels)
python3.11 -m venv .venv311
.venv311/bin/pip install -r requirements.txt

# download the MediaPipe hand landmarker (~7 MB, gitignored)
curl -L -o models/hand_landmarker.task \
  https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task

# train the classifier if results/models/best_model.h5 is missing (see Training)

# run the app
.venv311/bin/python -m src.live_inference
```

**Everything is clickable, and everything has a key.** The icon rail switches
modes, the panel buttons do what their badge says, and the `?` at the foot of
the rail opens an explainer covering what the app does, why it needs the
camera, and how it grades you.

`1`, `2`, `3` switch between the three modes from anywhere, `H` returns to
home, `?` opens help, `Q` quits. Teach adds `N` (next letter) and `R` (random);
spell-a-word adds `S` (skip letter). Every clickable region maps to the key it
stands for, so a click and its keystroke run exactly the same code.

If the camera is unavailable — no webcam, or permission not granted — the app
opens anyway and says so, rather than failing to start. Press `R` once you have
allowed access.

## Training

The trained model (`results/models/best_model.h5`) is gitignored, so build it
once after cloning:

```bash
# 1. Download + preprocess the wireframe dataset into a local cache (one-time)
.venv311/bin/python -m scripts.prep_wireframes

# 2. Train the classifier -> results/models/best_model.h5 (+ class_names.json)
.venv311/bin/python -m scripts.train_asl

# 3. (optional) Check held-out accuracy through the inference preprocessing
.venv311/bin/python -m scripts.verify_inference
```

The model reaches **~97% validation accuracy** (~92% on the held-out
inference check). The most-confused letters are M/N/T, which differ only by
thumb placement. Key knobs live in `src/config.py` (`IMAGE_SIZE`,
`MAX_PER_CLASS`, `EPOCHS`, `BATCH_SIZE`).

## Reference poses

The tutor's graded feedback needs canonical 21-landmark poses per letter.
These are extracted once from the [grassknoted/asl-alphabet](https://www.kaggle.com/datasets/grassknoted/asl-alphabet)
real-photo dataset and robust-averaged into `results/models/reference_poses.json`
(committed to git, ~23 KB).

```bash
.venv311/bin/python -m scripts.build_reference_poses
.venv311/bin/python -m scripts.verify_reference_poses
```

The geometric metric alone classifies held-out photos at **81.8%** across 24
classes (chance 4%), and its confusions mirror human ones: R/U, K/V, M/N.
Known weak spot: M/N references are noisy because thumb-tucked fists occlude
landmarks (intra-class spread ~0.35 vs ~0.07 elsewhere).

## Dataset

The classifier trains on the [ASL Alphabet Wireframes dataset](https://www.kaggle.com/datasets/dylanpallickara129/asl-alphabet-wireframes)
(~99k MediaPipe hand-skeleton images across the 24 static letters). It
downloads automatically via `kagglehub`; no Kaggle login is needed for this
public dataset.

`notebooks/` explore the separate Sign-MNIST dataset (28x28 grayscale) for
static-image CNN baselines; that work is independent of the realtime
pipeline.

## Interface

The look comes from a wireframe design kept in [`design/`](design/) — a small
Figma Make React app that mocks the six screens (home, teach, teach-complete,
practice, spell, spell-complete). It is the visual source of truth, not a
runtime dependency; the Python app reproduces it with Pillow drawn over the
webcam frame.

Three columns at 1280x720: a dark icon rail (68 px), the live camera, and a
356 px panel of rounded cards. Nunito is vendored under `assets/fonts/`
(SIL OFL) so the typography matches on any machine. The home screen is an
opaque title screen; the camera only shows through in the modes that need it.

One deliberate departure: the design mocks the "how to sign" card with a stock
photo. The app renders the letter's actual reference pose there instead — the
exact shape the learner is scored against, and no network fetch in the webcam
loop.

## Project structure

```
ASL_tutor/
├── requirements.txt
├── assets/fonts/               # vendored Nunito (SIL OFL) for the UI
├── design/                     # Figma Make wireframe app — the visual spec
│   ├── public/                 # favicon, social card, Pages headers
│   ├── wrangler.toml           # Cloudflare Pages project config
│   └── src/imports/pasted_text/screen-specs.md   # the six screens, in prose
├── models/                     # hand_landmarker.task (downloaded, gitignored)
├── data/
│   └── words.txt               # word list for spell-a-word mode
├── docs/
│   ├── roadmap.md              # what's next, in build order
│   ├── deploy.md               # Cloudflare Pages setup + browser-port checklist
│   └── scoring.md              # two-signal design writeup (coming)
├── notebooks/                  # Sign-MNIST CNN experiments
├── src/
│   ├── config.py               # shared settings (image size, paths, layout)
│   ├── hand_tracking.py        # MediaPipe Tasks HandLandmarker wrapper
│   ├── skeleton.py             # skeleton render, ghost overlay, pose art
│   ├── preprocessing.py        # crop-to-content + resize for the classifier
│   ├── live_inference.py       # webcam loop: detect, classify, route to a mode
│   └── tutor/
│       ├── reference.py        # per-letter reference poses + similarity
│       ├── theme.py            # palette, Nunito, cards/bars/tiles drawing
│       ├── modes.py            # Home, Teach, Practice, SpellWord state machine
│       └── session.py          # scores, streaks, JSONL results log
├── scripts/
│   ├── prep_wireframes.py      # one-time: build the processed training cache
│   ├── train_asl.py            # train the skeleton CNN
│   ├── verify_inference.py     # held-out accuracy check
│   ├── build_reference_poses.py   # extract reference poses from real photos
│   ├── verify_reference_poses.py  # sanity-check the similarity metric
│   └── make_web_icons.py          # placeholder favicon + social card
└── results/
    ├── models/                 # best_model.h5, class_names.json, reference_poses.json
    ├── figures/                # confusion matrices, learning curves, reference grid
    └── sessions/               # per-day session logs (gitignored)
```

To open the design mock itself:

```bash
cd design && pnpm install && pnpm dev
```

It also builds to a static site and is set up to deploy to Cloudflare Pages as
an interactive demo — see [docs/deploy.md](docs/deploy.md). The screens and the
24 reference hand shapes are real; the confidence readings are sample values,
since a static page has no camera or model behind it. The demo says so on every
screen and has an About page explaining the project. The checklist for making
it fully live is in that document.

## Roadmap

See [docs/roadmap.md](docs/roadmap.md).

Currently at: reference-pose foundation is done; tutor modes are being wired
into the live loop.

## Tech stack

TensorFlow / Keras, OpenCV, MediaPipe, NumPy, scikit-learn, kagglehub.
