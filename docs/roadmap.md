# Roadmap: fingerspelling tutor MVP

## Where the project is now

The realtime pipeline works end to end: webcam, MediaPipe HandLandmarker,
skeleton render, CNN, smoothed letter prediction. The old debug sidebar (one
letter, confidence, model input) has been replaced by the per-mode sidebars.

Steps 1-8 of the build order below are now written. Step 1 — per-letter
reference poses and the geometric similarity metric — is done and committed
(`src/tutor/reference.py`,
`scripts/build_reference_poses.py`, `scripts/verify_reference_poses.py`). The
geometric metric alone classifies held-out photos at 81.8% across 24 classes
(chance 4%); correct letters score 0.88 on the graded bar vs 0.19 for wrong
letters; confusions are the genuinely-similar pairs (R/U, K/V, M/N).

Steps 2-8 (ghost overlay, per-joint feedback, the three modes, and the
session log) are written and pass a headless test of the geometry, the mode
state machine, and the session writer — but they have not yet been through a
real webcam session. That camera pass is the next thing to do.

The interface has since been rebuilt to the wireframe design in `design/` (a
Figma Make React mock of the six screens): dark icon rail, live camera, and a
panel of rounded cards in a warm flat palette, drawn with Pillow and Nunito
rather than OpenCV's Hershey fonts. `src/tutor/theme.py` holds the palette and
the drawing primitives. All six screens render; the panel costs ~7 ms/frame.

Known weak spot: M/N references are noisy (thumb-tucked fists occlude
landmarks; intra spread ~0.35 vs ~0.07 elsewhere).

## Direction

An ASL fingerspelling learner/tutor, not a dynamic word/sentence recognizer.
Dynamic and two-handed signs need temporal models over landmark sequences on
harder datasets (WLASL/MS-ASL); those stay in "future work" and would
require throwing away most of this pipeline.

## Scoring design

Two complementary signals:

```
pass  = cnn_pred == target AND cnn_conf > CNN_THRESHOLD    # gate (existing CNN)
bar   = 100 * (1 - clamp(mean_landmark_dist / D_MAX))      # graded feedback
```

- The CNN (`best_model.h5`) decides pass/fail.
- Landmark distance to a stored per-letter reference pose gives a graded
  0-100% closeness bar, plus per-joint feedback (color the worst-off joints
  red) so the learner sees which fingers are wrong.
- Reference poses are computed, not hand-crafted: robust-averaged normalized
  landmarks per letter (wrist-centered, scale-normalized, rotation preserved
  because orientation is part of a sign). Stored in
  `results/models/reference_poses.json`.
- Landmark source: the wireframe dataset is images of skeletons with no
  coordinates, and MediaPipe cannot detect drawn skeletons (verified 0/30).
  References are instead extracted by running MediaPipe over the real-photo
  `grassknoted/asl-alphabet` dataset.

## MVP scope

Three modes, shipped together with a home screen and a demo GIF. That is the
whole portfolio version. Timed quiz and a metrics dashboard are cut for now.

**In:**
- Home screen (mode select, alphabet coverage note)
- Teach mode (target letter, ghost overlay, per-joint feedback, closeness bar)
- Practice mode (free signing, CNN prediction, closeness to nearest reference)
- Spell-a-word mode (target word, dwell-to-commit, progress bar)
- README with hero GIF and one screenshot per mode
- `docs/scoring.md` writeup of the two-signal design with distribution figure
- Hand-curated M/N references or an in-UI caveat (pick one before shipping)
- 20-40 second demo recording

**Deferred:**
- Timed quiz
- Live metrics dashboard
- Session-improvement analytics view
- Manual reference-pose editor

**Post-MVP stretch:**
- Browser port (tf.js + MediaPipe JS). Turns "clone and run Python" into a
  link on the portfolio site. Highest-leverage single addition after MVP.
- Dynamic signs (J, Z) via short landmark sequences.
- True word-level recognition (WLASL/MS-ASL, temporal models).

## Module layout

```
src/tutor/
├── reference.py   # DONE: reference poses + similarity(live, target)
├── modes.py       # state machine: Home, Teach, Practice, SpellWord
└── session.py     # scores, streaks, JSONL results log
```

The tutor is a thin state/mode layer over the existing detect, render,
classify loop in `src/live_inference.py`. Each mode owns its own sidebar
rendering and key handling. The loop delegates to the current mode.

## Build order

Each step is demoable on its own.

1. **DONE.** Reference poses + similarity metric.
2. **DONE\*.** Ghost overlay + per-joint colored feedback. `render_skeleton`
   takes an optional per-joint error array and tints joints from it;
   `render_ghost` draws a reference pose over the live hand at low alpha,
   fitted in normalized landmark space so it lands on a correct sign.
3. **DONE\*.** `modes.py` and `session.py`. Base Mode class, HomeMode,
   TeachMode, PracticeMode, SpellWordMode. Session logger writes JSONL.
4. **DONE\*.** Modes wired into `live_inference.py`. The main loop holds a
   current mode, passes it the CNN output and landmarks each frame, and lets
   it draw its own sidebar and handle key presses. Sessions save on mode
   switch and on quit.
5. **DONE\*.** Teach mode end to end. Shuffled target queue, auto-advance on
   sustained pass, worst-fingers feedback line.
6. **DONE\*.** Practice mode. CNN readout plus the geometric closeness bar
   and a rolling recent-letters strip.
7. **DONE\*.** Spell-a-word mode. Word list from `data/words.txt`,
   dwell-to-commit timer, progress header, completion screen.
8. **DONE\*.** Session log. JSONL per day under `results/sessions/`.
9. **M/N decision.** Curate or caveat.
10. **Demo recording.** Screen record all three modes; GIF the best 25 seconds.
11. **README rewrite** (partly done — structure and interface sections now
    match the built app).
12. **`docs/scoring.md`.** Two-signal writeup with a distribution histogram
    from `verify_reference_poses`. This is the doc a recruiter reads after
    the README.
13. **Ship.**

\* Written and covered by a headless test of the geometry, the mode state
machine and the session writer; not yet run against a real webcam.

Steps 1-9 are the code. Steps 10-13 are the packaging; they are where
portfolio value lives.

Immediate next actions: run the app on a real webcam and tune `CNN_THRESHOLD`,
`GEO_THRESHOLD` and `DWELL_SECONDS` (all in `src/config.py`) against how it
actually feels, then take the M/N decision in step 9. The camera pass is also
the only way to judge the ghost overlay and the joint tinting against a real
hand and real lighting.

## Post-MVP: browser port

If MVP ships and there is time, this is the next thing to build.

- `design/` is already a React + Vite + Tailwind app with all six screens
  laid out. It is the natural shell for this: replace the mocked values with
  live ones rather than starting from a blank page.
- MediaPipe HandLandmarker has a JS build; drop-in for the current tracker.
- Convert `best_model.h5` to tf.js format with `tensorflowjs_converter`.
- Reference poses (`reference_poses.json`) load as-is.
- Skeleton render, similarity, mode state machine all port to plain JS.
- Host on `portfolio.mwlde.com` as a subpage.

Rough estimate: one focused weekend.
