Screen specs

Six screens total. Each has: purpose, layout, what fills it, what changes each frame, and what keys do what. Frame is 1280x720; sidebar is 360 px wide on the right so the camera area is roughly 920x720.

1. Home

Purpose. Land here on launch. Pick a mode. Show which letters are supported and which aren't.

Layout. Full-frame dim overlay over a live camera background (so the app feels alive, not frozen). Centered text stack, no sidebar.

Content.

Title: "ASL FINGERSPELLING TUTOR"
Subtitle: "Learn the 24 static letters"
Menu (each line is a keybinding + label):
[1] Teach a letter
[2] Practice free-signing
[3] Spell a word
[Q] Quit
Footnote at bottom: "J and Z are motion signs and not supported."

Dynamic. Camera behind is live but ignored. No CNN inference needs to run here.

Keys. 1 2 3 route to modes. Q quits.

2. Teach — letter view

Purpose. Teach one specific letter. Show the target, overlay the correct hand shape as a ghost, tell the learner which fingers are wrong, auto-advance when they hold the right sign long enough.

Layout. Camera area on the left (~920 wide), 360 px sidebar on the right.

Content — camera area.

Live webcam frame with the detected hand skeleton drawn over the hand (existing behavior).
Ghost skeleton of the target reference pose overlaid at roughly 30% alpha, scaled to sit where the hand is (or centered if no hand). This is the "here's what your hand should look like" image.
Per-joint tinting on the live skeleton: joints under D_PERFECT green, mid yellow, above D_MAX/2 red. Uses per_joint_distances() from reference.py.

Content — sidebar.

Header row: "TEACH"
Small label: "target letter"
Big centered glyph (the target letter, e.g., "B") in green
Closeness bar filled to score, label underneath: "match: 62%"
CNN readout line: "detected: F (91%)"
Feedback line (only when score < 0.9): "fix your ring and pinky"
Controls at bottom: [N] next letter, [R] random, [H] home

Dynamic. Every frame: recompute score, dists, mirrored = ref_lib.score(landmarks, target), update bar and feedback line. Track a rolling window of the last 8 frames; if every one of them passed the CNN+geometry check, auto-advance to the next letter.

Keys. N next, R random, H home.

3. Teach — alphabet complete

Purpose. End state after all 24 letters cycled through. Rare screen; needs to exist so the mode has a natural terminus.

Layout. Same sidebar frame as Teach, camera still live behind.

Content.

Sidebar shows: "ALPHABET COMPLETE" in green, [H] home line.

Keys. H home.

(You could fold this into the Teach spec as a state variant. I split it out because it needs its own copy and it's easy to forget when mocking up.)

4. Practice

Purpose. Free signing. Show what the CNN thinks and what the geometry thinks, side by side. This is the screen that quietly demonstrates the two-signal design.

Layout. Camera left, sidebar right (same shape as Teach).

Content — camera area.

Standard live skeleton on the hand. No ghost, no target.

Content — sidebar (top to bottom).

Header: "PRACTICE"
Label: "detected"
Big letter glyph — the CNN prediction, or - if no hand
CNN confidence bar with label "CNN: 91%"
A second block below with the geometric best-match:
"nearest: F"
Yellow-ish bar
"closeness: 84%"
Recent letters strip near the bottom: label "recent:", then last 5 committed letters separated by spaces
Controls: [H] home

Dynamic. Every frame: CNN prediction updates the glyph and bar. ref_lib.best_match(landmarks) fills the geometric block. When the CNN gives a high-confidence prediction that's different from the last one committed, append it to recent.

Keys. H home.

5. Spell a word — in progress

Purpose. Guide the learner through a word one letter at a time. Hold each sign to commit.

Layout. Top progress header (full width, 80 px tall), then the standard camera + sidebar split below.

Content — top header.

"Spell:" label on the left
Each letter of the target word rendered in sequence:
Committed letters in green
Current target in cyan/blue
Upcoming letters in gray

Content — camera area. Live webcam with skeleton. No ghost overlay in this mode (kept simple; the target letter is displayed in the sidebar as reference).

Content — sidebar.

Header: "SPELL"
Label: "next letter"
Big glyph of the current target in cyan
Dwell bar filling as the correct sign is held, label "hold for 1.5s"
CNN readout line: "detected: L (86%)"
Controls: [S] skip letter, [H] home

Dynamic. Every frame check whether the CNN prediction matches the target with conf >= CNN_THRESHOLD. If yes, start (or continue) a dwell timer. When the timer crosses DWELL_SECONDS, commit the letter, advance the index, reset the dwell. If the sign changes before the timer completes, reset it.

Keys. S skip (marks as failed and advances), H home.

6. Spell a word — complete

Purpose. Payoff screen. Shows the learner finished and how long they took.

Layout. Same top header (all letters now green), camera + sidebar below.

Content — sidebar.

Header: "SPELL"
"COMPLETE" in big green text
Time: "8.4 seconds"
Controls: [H] home

Dynamic. Static once entered.

Keys. H home.