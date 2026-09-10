import { useEffect, useState } from "react";

type Screen = "home" | "teach" | "practice" | "spell" | "about";

const LETTERS = "ABCDEFGHIKLMNOPQRSTUVWXY".split("");
const SAMPLE_WORD = "HELLO";

// ── palette (blended: warm inspo #1 + Yama Graphics flat pastel system) ───────
const c = {
  // grounds
  bg:       "#F7F3EF",   // warm off-white from Yama
  surface:  "#EFEBE5",   // slightly deeper off-white for panels
  white:    "#FFFFFF",
  ink:      "#111111",   // near-black text — high contrast
  inkMid:   "#555550",
  inkSoft:  "#999990",
  inkFaint: "#CCCCC5",
  // pastel chips from Yama palette
  yellow:   "#FFE59A",
  yellowDk: "#C49A00",   // text on yellow
  pink:     "#FFBCC1",
  pinkDk:   "#A03040",
  mint:     "#B7E1D1",
  mintDk:   "#1A6B50",
  sky:      "#A9D3FF",
  skyDk:    "#1A4A80",
  // warm terra kept as a subtle accent
  terra:    "#D4784E",
  terraFaint: "#FAE8DC",
};

// The 24 reference hand shapes the tutor scores against, exported from
// results/models/reference_poses.json. Each is 21 landmarks, wrist-centred and
// scale-normalised, so they can be drawn at any size.
type Poses = Record<string, [number, number][]>;

// MediaPipe's hand topology, matching src/skeleton.py. The palm is a chain
// across the knuckles (5-9-13-17), not a fan of spokes from the wrist —
// drawing it as a fan makes a closed fist read as an open hand.
const BONES: [number, number][] = [
  [0,1],[0,5],[5,9],[9,13],[13,17],[0,17],          // palm
  [1,2],[2,3],[3,4],                                 // thumb
  [5,6],[6,7],[7,8],                                 // index
  [9,10],[10,11],[11,12],                            // middle
  [13,14],[14,15],[15,16],                           // ring
  [17,18],[18,19],[19,20],                           // pinky
];

function usePoses(): Poses | null {
  const [poses, setPoses] = useState<Poses | null>(null);
  useEffect(() => {
    let live = true;
    fetch("/data/reference_poses.json")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => live && setPoses(d))
      .catch(() => {});
    return () => {
      live = false;
    };
  }, []);
  return poses;
}

/** Fit a normalised pose into a box and draw it. */
function PoseArt({ pose, size = 132, stroke = c.ink }: {
  pose: [number, number][]; size?: number; stroke?: string;
}) {
  const xs = pose.map((p) => p[0]);
  const ys = pose.map((p) => p[1]);
  const lo = [Math.min(...xs), Math.min(...ys)];
  const hi = [Math.max(...xs), Math.max(...ys)];
  const span = Math.max(hi[0] - lo[0], hi[1] - lo[1], 1e-6);
  const usable = size * 0.86;
  const mid = [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2];
  const pt = (p: [number, number]) => [
    ((p[0] - mid[0]) / span) * usable + size / 2,
    ((p[1] - mid[1]) / span) * usable + size / 2,
  ];
  const px = pose.map(pt);

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {BONES.map(([a, b], i) => (
        <line key={i} x1={px[a][0]} y1={px[a][1]} x2={px[b][0]} y2={px[b][1]}
          stroke={stroke} strokeWidth="3" strokeLinecap="round" />
      ))}
      {px.map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r="3.6" fill={stroke} />
      ))}
    </svg>
  );
}

// ── decorative blob (organic shape from Yama) ─────────────────────────────────
function Blob({ color, style }: { color: string; style?: React.CSSProperties }) {
  return (
    <svg viewBox="0 0 200 200" style={{ position: "absolute", pointerEvents: "none", ...style }}>
      <path fill={color} d="M47,-65C59,-55,66,-39,70,-23C74,-6,74,11,68,27C62,43,50,57,36,65C21,73,4,75,-14,71C-32,67,-51,57,-63,42C-74,27,-79,7,-76,-12C-73,-31,-63,-49,-48,-60C-33,-72,-14,-77,3,-77C20,-78,35,-75,47,-65Z" transform="translate(100 100)" />
    </svg>
  );
}

// ── skeleton ──────────────────────────────────────────────────────────────────
function HandSkeleton({ colored }: { colored?: boolean }) {
  const cx = 460, cy = 370;
  const j: [number,number][] = [
    [cx,cy+110],
    [cx-80,cy+55],[cx-108,cy+5],[cx-122,cy-32],[cx-128,cy-62],
    [cx-38,cy+18],[cx-42,cy-42],[cx-45,cy-92],[cx-47,cy-132],
    [cx+2,cy+12],[cx+2,cy-52],[cx+2,cy-102],[cx+2,cy-147],
    [cx+42,cy+18],[cx+46,cy-36],[cx+49,cy-86],[cx+51,cy-126],
    [cx+78,cy+28],[cx+88,cy-14],[cx+92,cy-54],[cx+94,cy-88],
  ];
  const bones = BONES;
  const dots = colored
    ? [c.mint,c.mint,c.mint,c.yellow,c.yellow,c.mint,c.mint,c.mint,c.mint,c.mint,c.mint,c.yellow,c.pink,c.mint,c.mint,c.yellow,c.pink,c.mint,c.mint,c.mint,c.mint]
    : Array(21).fill("rgba(180,140,110,0.25)");
  const boneColor = colored ? "rgba(180,140,110,0.2)" : "rgba(180,140,110,0.12)";

  return (
    <svg className="absolute inset-0 w-full h-full" viewBox="0 0 920 720">
      {bones.map(([a,b],i) => (
        <line key={i} x1={j[a][0]} y1={j[a][1]} x2={j[b][0]} y2={j[b][1]}
          stroke={boneColor} strokeWidth="2.5" strokeLinecap="round" />
      ))}
      {j.map(([x,y],i) => (
        <circle key={i} cx={x} cy={y} r={colored ? 6 : 4} fill={dots[i]} />
      ))}
    </svg>
  );
}

function CameraArea({ ghost, poses, note }: {
  ghost?: string; poses?: Poses | null; note?: string;
}) {
  const pose = ghost && poses ? poses[ghost] : undefined;
  return (
    <div className="relative flex-1 overflow-hidden" style={{ background: "#EDE5DC" }}>
      <HandSkeleton colored />
      {pose && (
        // The ghost of the target shape, the way the desktop app overlays it.
        <div className="absolute pointer-events-none"
          style={{ left: "50%", top: "50%", transform: "translate(-50%,-50%)", opacity: 0.14 }}>
          <PoseArt pose={pose} size={380} />
        </div>
      )}
      <div className="absolute left-5 top-5 flex items-center gap-2">
        <span className="px-2.5 py-1 rounded-full"
          style={{ background: c.ink, color: "#fff", fontSize: 10, fontWeight: 800, letterSpacing: "0.08em" }}>
          DEMO
        </span>
        <span style={{ fontSize: 11, fontWeight: 600, color: c.inkSoft }}>
          {note ?? "Sample frame — the real app draws your webcam here"}
        </span>
      </div>
    </div>
  );
}

// ── left nav — dark, Yama-style ───────────────────────────────────────────────
const NAV: { id: Screen | "home"; label: string }[] = [
  { id: "home",     label: "Home"     },
  { id: "teach",    label: "Teach"    },
  { id: "practice", label: "Practice" },
  { id: "spell",    label: "Spell"    },
  { id: "about",    label: "About"    },
];

function NavIcon({ id, col }: { id: string; col: string }) {
  if (id === "home") return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <path d="M9 2L2 8v8h5v-4h4v4h5V8L9 2z" fill={col} />
    </svg>
  );
  if (id === "teach") return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <rect x="2" y="3" width="14" height="9" rx="2" fill={col} />
      <rect x="7" y="13" width="4" height="2" rx="1" fill={col} />
    </svg>
  );
  if (id === "practice") return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <circle cx="9" cy="9" r="6.5" stroke={col} strokeWidth="1.8" fill="none" />
      <circle cx="9" cy="9" r="2.5" fill={col} />
    </svg>
  );
  if (id === "spell") return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <path d="M3 5h12M3 9h7M3 13h9" stroke={col} strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <circle cx="9" cy="9" r="7.2" stroke={col} strokeWidth="1.8" fill="none" />
      <circle cx="9" cy="5.4" r="1.05" fill={col} />
      <path d="M9 8v5" stroke={col} strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function LeftNav({ screen, onNav }: { screen: Screen | "home"; onNav: (s: Screen | "home") => void }) {
  return (
    <div className="w-[68px] shrink-0 flex flex-col items-center py-5 gap-1"
      style={{ background: c.ink }}>
      {/* logo mark */}
      <div className="w-9 h-9 rounded-2xl flex items-center justify-center mb-5"
        style={{ background: c.yellow }}>
        {/* graduation cap, matching the desktop app's rail mark */}
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
          <path d="M10 3.4 18 7l-8 3.6L2 7l8-3.6z" fill={c.ink} />
          <path d="M6 9.2v3.4c0 1.1 1.8 2 4 2s4-.9 4-2V9.2l-4 1.8-4-1.8z" fill={c.ink} />
          <path d="M16.6 7.7v4.1" stroke={c.ink} strokeWidth="1.1" strokeLinecap="round" />
          <circle cx="16.6" cy="12.6" r="1.25" fill={c.ink} />
        </svg>
      </div>

      {NAV.map(({ id, label }) => {
        const active = screen === id;
        return (
          <button key={id} onClick={() => onNav(id)} title={label}
            className="w-11 h-11 rounded-2xl flex items-center justify-center transition-all"
            style={{ background: active ? "rgba(255,255,255,0.12)" : "transparent" }}>
            <NavIcon id={id} col={active ? "#fff" : "rgba(255,255,255,0.35)"} />
          </button>
        );
      })}
    </div>
  );
}

// ── panel ─────────────────────────────────────────────────────────────────────
function Panel({ children }: { children: React.ReactNode }) {
  return (
    <div className="w-[356px] shrink-0 flex flex-col h-full overflow-y-auto py-4 px-4 gap-2.5"
      style={{ background: c.surface }}>
      {children}
    </div>
  );
}

// Flat card — no shadow, just background color
function Card({ children, bg, style }: { children: React.ReactNode; bg?: string; style?: React.CSSProperties }) {
  return (
    <div className="rounded-2xl p-4" style={{ background: bg ?? c.white, ...style }}>
      {children}
    </div>
  );
}

function MixedLabel({ normal, bold }: { normal: string; bold: string }) {
  return (
    <p className="text-sm mb-2" style={{ color: c.inkSoft }}>
      <span style={{ fontWeight: 500 }}>{normal} </span>
      <span style={{ fontWeight: 800, color: c.ink }}>{bold}</span>
    </p>
  );
}

function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
    <p style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.15em", textTransform: "uppercase", color: c.inkFaint, marginBottom: 6 }}>
      {children}
    </p>
  );
}

function Bar({ value, color, label }: { value: number; color: string; label: string }) {
  return (
    <div>
      <div className="h-2.5 rounded-full overflow-hidden" style={{ background: c.surface }}>
        <div className="h-full rounded-full transition-all duration-500"
          style={{ width: `${value}%`, background: color }} />
      </div>
      <p className="mt-1.5" style={{ fontSize: 11, color: c.inkSoft, fontWeight: 600 }}>{label}</p>
    </div>
  );
}

// Yama-style pill button: dark filled primary, outlined secondary
function Btn({ label, badge, onClick, variant = "default" }: {
  label: string; badge?: string; onClick: () => void;
  variant?: "primary" | "default" | "ghost";
}) {
  const s: React.CSSProperties =
    variant === "primary" ? { background: c.ink, color: "#fff" } :
    variant === "ghost"   ? { background: "transparent", color: c.inkSoft } :
                            { background: c.white, color: c.ink, outline: `1.5px solid ${c.inkFaint}` };
  return (
    <button onClick={onClick}
      className="flex items-center gap-3 w-full px-4 py-3 rounded-2xl text-sm transition-all active:scale-[0.98] hover:opacity-85 focus-visible:outline-none"
      style={{ fontWeight: 700, ...s }}>
      {badge && (
        <span className="shrink-0 w-6 h-6 rounded-lg text-[10px] flex items-center justify-center"
          style={{ fontWeight: 800, background: variant === "primary" ? "rgba(255,255,255,0.15)" : c.surface, color: variant === "primary" ? "rgba(255,255,255,0.7)" : c.inkSoft }}>
          {badge}
        </span>
      )}
      <span className="flex-1 text-left">{label}</span>
    </button>
  );
}

function PhotoCard({ letter, poses }: { letter: string; poses: Poses | null }) {
  const pose = poses?.[letter];
  return (
    <Card>
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <div style={{ flex: 1 }}>
          <Eyebrow>How to sign</Eyebrow>
          <p style={{ fontSize: 12, color: c.inkMid, fontWeight: 500, lineHeight: 1.55 }}>
            The exact hand shape <strong style={{ color: c.ink }}>{letter}</strong> is
            scored against — the real reference pose, not an illustration.
          </p>
        </div>
        <div className="rounded-2xl shrink-0" style={{ background: c.surface, padding: 6 }}>
          {pose
            ? <PoseArt pose={pose} size={116} />
            : <div style={{ width: 116, height: 116 }} />}
        </div>
      </div>
    </Card>
  );
}

/** Short "what you are looking at" note for a mode's side panel. */
function Note({ title, children, bg = c.surface, col = c.inkMid }: {
  title: string; children: React.ReactNode; bg?: string; col?: string;
}) {
  return (
    <div className="rounded-2xl p-4" style={{ background: bg }}>
      <p style={{ fontSize: 10, fontWeight: 800, letterSpacing: "0.12em", textTransform: "uppercase", color: col, opacity: 0.7, marginBottom: 6 }}>
        {title}
      </p>
      <p style={{ fontSize: 12, fontWeight: 500, color: col, lineHeight: 1.6 }}>
        {children}
      </p>
    </div>
  );
}

// Pastel chip — Yama tag style
function Chip({ label, bg, col }: { label: string; bg: string; col: string }) {
  return (
    <span className="inline-block px-3 py-1 rounded-full text-xs font-700"
      style={{ background: bg, color: col }}>
      {label}
    </span>
  );
}

// ── home ──────────────────────────────────────────────────────────────────────
function HomeScreen({ onMode }: { onMode: (s: Screen) => void }) {
  return (
    <div className="flex-1 relative flex flex-col items-center justify-center gap-8 px-8 overflow-hidden"
      style={{ background: c.bg }}>

      {/* organic blob decorations — Yama style */}
      <Blob color={c.yellow} style={{ width: 260, height: 260, top: -60, right: -40, opacity: 0.55 }} />
      <Blob color={c.mint}   style={{ width: 200, height: 200, bottom: -40, left: 40, opacity: 0.45 }} />
      <Blob color={c.pink}   style={{ width: 140, height: 140, bottom: 80, right: 80, opacity: 0.3 }} />

      <div className="relative z-10 text-center max-w-[340px]">
        <p style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.2em", textTransform: "uppercase", color: c.inkFaint, marginBottom: 10 }}>
          Welcome
        </p>
        <h1 style={{ fontSize: 38, fontWeight: 900, lineHeight: 1.1, color: c.ink, marginBottom: 12 }}>
          ASL Fingerspelling<br />
          <span style={{ color: c.terra }}>Tutor</span>
        </h1>
        <p style={{ fontSize: 13, color: c.inkMid, fontWeight: 500, lineHeight: 1.7 }}>
          Learn the 24 static letters at your own pace.
          Every sign gets clearer with a little practice.
        </p>
      </div>

      <div className="relative z-10 w-full max-w-[380px] space-y-2.5">
        {[
          { s: "teach"    as Screen, title: "Teach",    sub: "a letter",     desc: "Step through each letter with live feedback and a hand reference photo.", chip: { bg: c.yellow, col: c.yellowDk } },
          { s: "practice" as Screen, title: "Practice", sub: "free signing", desc: "Sign freely and see how the model reads your hand in real time.",           chip: { bg: c.mint,   col: c.mintDk   } },
          { s: "spell"    as Screen, title: "Spell",    sub: "a word",       desc: "Hold each letter sign until it commits, then move to the next one.",        chip: { bg: c.sky,    col: c.skyDk    } },
        ].map(({ s, title, sub, desc, chip }) => (
          <button key={s} onClick={() => onMode(s)}
            className="w-full text-left px-5 py-4 rounded-2xl transition-all active:scale-[0.99] hover:opacity-90 focus-visible:outline-none"
            style={{ background: c.white }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
              <Chip label={title} bg={chip.bg} col={chip.col} />
              <span style={{ fontWeight: 600, color: c.inkMid, fontSize: 13 }}>{sub}</span>
            </div>
            <p style={{ fontSize: 12, color: c.inkSoft, fontWeight: 500, lineHeight: 1.55 }}>{desc}</p>
          </button>
        ))}
      </div>

      <button onClick={() => onMode("about")}
        className="relative z-10 px-5 py-2.5 rounded-2xl transition-all active:scale-[0.98] hover:opacity-85"
        style={{ background: c.white, outline: `1.5px solid ${c.inkFaint}`, fontSize: 12, fontWeight: 700, color: c.inkMid }}>
        What is this?  ·  How it works
      </button>

      <p className="relative z-10" style={{ fontSize: 11, color: c.inkFaint, fontWeight: 500 }}>
        J and Z are motion signs and are not included in this version.
      </p>
    </div>
  );
}

// ── teach ─────────────────────────────────────────────────────────────────────
function TeachScreen({ onHome, poses }: { onHome: () => void; poses: Poses | null }) {
  const [idx, setIdx] = useState(0);
  const done = idx >= LETTERS.length;
  const letter = done ? "" : LETTERS[idx];

  return (
    <div className="flex-1 flex min-w-0 h-full">
      <CameraArea ghost={letter} poses={poses} />
      <Panel>
        {done ? (
          <>
            <MixedLabel normal="Alphabet" bold="complete" />
            <Card bg={c.mint} style={{ textAlign: "center", padding: "2rem 1rem" }}>
              <p style={{ fontSize: 26, fontWeight: 900, color: c.mintDk, marginBottom: 8 }}>Well done.</p>
              <p style={{ fontSize: 12, color: c.inkMid, fontWeight: 500, lineHeight: 1.65 }}>
                You worked through all 24 letters. That kind of persistence is exactly how signs become second nature.
              </p>
            </Card>
            <Btn label="Return home" badge="H" onClick={onHome} variant="primary" />
          </>
        ) : (
          <>
            <MixedLabel normal="Teach" bold="a letter" />

            <Card>
              <Eyebrow>Target letter</Eyebrow>
              <div style={{ fontSize: 88, fontWeight: 900, textAlign: "center", lineHeight: 1, paddingBlock: 6, color: c.ink }}>
                {letter}
              </div>
            </Card>

            <PhotoCard letter={letter} poses={poses} />

            <Card>
              <Bar value={62} color={c.mint} label="Match — 62%" />
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 12, paddingTop: 12, borderTop: `1px solid ${c.surface}` }}>
                <span style={{ fontSize: 11, color: c.inkSoft, fontWeight: 600 }}>CNN read</span>
                <span style={{ fontSize: 14, fontWeight: 800, color: c.ink }}>
                  F <span style={{ fontSize: 11, fontWeight: 600, color: c.inkSoft }}>91%</span>
                </span>
              </div>
            </Card>

            <Card bg={c.yellow}>
              <p style={{ fontSize: 12, fontWeight: 700, color: c.yellowDk, lineHeight: 1.6 }}>
                Try curling your ring and pinky fingers in a little more — you are really close.
              </p>
            </Card>

            <Card>
              <Eyebrow>Progress · {idx} / {LETTERS.length}</Eyebrow>
              <div className="flex flex-wrap gap-1">
                {LETTERS.map((l, i) => (
                  <span key={l} style={{
                    width: 24, height: 24, borderRadius: 8, fontSize: 10, fontWeight: 800,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    background: i < idx ? c.mint : i === idx ? c.ink : c.surface,
                    color: i < idx ? c.mintDk : i === idx ? "#fff" : c.inkFaint,
                    transition: "all 0.2s",
                  }}>{l}</span>
                ))}
              </div>
            </Card>

            <Note title="What you are seeing">
              The bar is how close your hand is to the reference shape, and the
              CNN read is what the classifier thinks you are signing. Both run
              at once — one grades, one decides. In this demo they hold sample
              values.
            </Note>

            <div className="space-y-2 mt-auto pt-1">
              <Btn label="Next letter" badge="N" onClick={() => setIdx(i => i + 1)} variant="primary" />
              <Btn label="Random letter" badge="R" onClick={() => setIdx(Math.floor(Math.random() * LETTERS.length))} />
              <Btn label="Go home" badge="H" onClick={onHome} variant="ghost" />
            </div>
          </>
        )}
      </Panel>
    </div>
  );
}

// ── practice ──────────────────────────────────────────────────────────────────
function PracticeScreen({ onHome }: { onHome: () => void }) {
  const recent = ["A", "F", "B", "L", "K"];
  return (
    <div className="flex-1 flex min-w-0 h-full">
      <CameraArea note="Sample frame — the real app reads your hand here" />
      <Panel>
        <MixedLabel normal="Practice" bold="free signing" />

        <Card>
          <Eyebrow>CNN sees</Eyebrow>
          <div style={{ fontSize: 80, fontWeight: 900, textAlign: "center", lineHeight: 1, paddingBlock: 6, color: c.ink }}>F</div>
          <div className="mt-3">
            <Bar value={91} color={c.mint} label="Confidence — 91%" />
          </div>
        </Card>

        <Card bg={c.yellow}>
          <Eyebrow>Geometry match</Eyebrow>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 10 }}>
            <span style={{ fontSize: 40, fontWeight: 900, color: c.ink }}>F</span>
            <span style={{ fontSize: 11, color: c.inkMid, fontWeight: 500 }}>nearest shape</span>
          </div>
          <Bar value={84} color={c.yellowDk} label="Closeness — 84%" />
        </Card>

        <Card>
          <Eyebrow>Recent letters</Eyebrow>
          <div style={{ display: "flex", gap: 8 }}>
            {recent.map((l, i) => (
              <div key={i} style={{
                width: 40, height: 40, borderRadius: 12,
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 16, fontWeight: 900, color: c.ink,
                background: c.surface,
              }}>{l}</div>
            ))}
          </div>
        </Card>

        <Card bg={c.mint}>
          <p style={{ fontSize: 12, fontWeight: 700, color: c.mintDk, lineHeight: 1.6 }}>
            Looking good — keep going and watch your confidence scores climb.
          </p>
        </Card>

        <Note title="What you are seeing">
          This screen shows the two signals side by side: what the trained
          classifier reads, and which stored hand shape your pose is
          geometrically nearest. They usually agree — when they disagree, the
          disagreement is the interesting part.
        </Note>

        <div className="mt-auto pt-1">
          <Btn label="Go home" badge="H" onClick={onHome} />
        </div>
      </Panel>
    </div>
  );
}

// ── spell ─────────────────────────────────────────────────────────────────────
function SpellScreen({ onHome, poses }: { onHome: () => void; poses: Poses | null }) {
  const word = SAMPLE_WORD.split("");
  const [committed, setCommitted] = useState(1);
  const [complete, setComplete] = useState(false);
  const current = complete ? word.length : committed;

  const advance = () => {
    if (committed + 1 >= word.length) setComplete(true);
    else setCommitted(n => n + 1);
  };

  return (
    <div className="flex-1 flex flex-col min-w-0 h-full">
      {/* word strip */}
      <div className="h-[64px] shrink-0 flex items-center px-5 gap-2"
        style={{ background: c.white }}>
        <p style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.15em", textTransform: "uppercase", color: c.inkFaint, marginRight: 8 }}>
          Spell
        </p>
        {word.map((l, i) => (
          <div key={i} style={{
            width: 40, height: 40, borderRadius: 12,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 20, fontWeight: 900, transition: "all 0.3s",
            background: i < current ? c.mint : i === current ? c.yellow : c.surface,
            color: i < current ? c.mintDk : i === current ? c.yellowDk : c.inkFaint,
          }}>{l}</div>
        ))}
        {complete && (
          <span style={{ marginLeft: "auto", fontSize: 12, fontWeight: 800, color: c.mintDk }}>
            All done — great work.
          </span>
        )}
      </div>

      <div className="flex flex-1 min-h-0">
        <CameraArea ghost={complete ? undefined : word[current]} poses={poses} />
        <Panel>
          {complete ? (
            <>
              <MixedLabel normal="Spell" bold="complete" />
              <Card bg={c.mint} style={{ textAlign: "center", padding: "2rem 1rem" }}>
                <p style={{ fontSize: 26, fontWeight: 900, color: c.mintDk, marginBottom: 8 }}>Brilliant.</p>
                <p style={{ fontSize: 44, fontWeight: 900, color: c.ink, marginBottom: 8 }}>8.4s</p>
                <p style={{ fontSize: 12, color: c.inkMid, fontWeight: 500, lineHeight: 1.65 }}>
                  You spelled the whole word without stopping. That is real progress.
                </p>
              </Card>
              <Btn label="Return home" badge="H" onClick={onHome} variant="primary" />
            </>
          ) : (
            <>
              <MixedLabel normal="Spell" bold="a word" />

              <Card>
                <Eyebrow>Sign this next</Eyebrow>
                <div style={{ fontSize: 80, fontWeight: 900, textAlign: "center", lineHeight: 1, paddingBlock: 6, color: c.ink }}>
                  {word[current]}
                </div>
              </Card>

              <PhotoCard letter={word[current]} poses={poses} />

              <Card>
                <Bar value={38} color={c.sky} label="Keep holding — 1.5s to commit" />
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 12, paddingTop: 12, borderTop: `1px solid ${c.surface}` }}>
                  <span style={{ fontSize: 11, color: c.inkSoft, fontWeight: 600 }}>CNN read</span>
                  <span style={{ fontSize: 14, fontWeight: 800, color: c.ink }}>
                    L <span style={{ fontSize: 11, fontWeight: 600, color: c.inkSoft }}>86%</span>
                  </span>
                </div>
              </Card>

              <Card bg={c.sky}>
                <p style={{ fontSize: 12, fontWeight: 700, color: c.skyDk, lineHeight: 1.6 }}>
                  Hold steady and the letter will commit on its own. Take your time.
                </p>
              </Card>

              <Note title="What you are seeing" bg={c.surface}>
                In the real app the bar fills only while you hold the correct
                sign, and the letter commits when it reaches the end. Here the
                buttons stand in for your hand.
              </Note>

              <div className="space-y-2 mt-auto pt-1">
                <Btn label="Commit letter" badge="N" onClick={advance} variant="primary" />
                <Btn label="Skip this letter" badge="S" onClick={advance} />
                <Btn label="Go home" badge="H" onClick={onHome} variant="ghost" />
              </div>
            </>
          )}
        </Panel>
      </div>
    </div>
  );
}

// ── about ─────────────────────────────────────────────────────────────────────
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 26 }}>
      <p style={{ fontSize: 13, fontWeight: 800, color: c.terra, marginBottom: 8 }}>{title}</p>
      <p style={{ fontSize: 13, fontWeight: 500, color: c.inkMid, lineHeight: 1.75 }}>{children}</p>
    </div>
  );
}

function AboutScreen({ onMode, poses }: {
  onMode: (s: Screen) => void; poses: Poses | null;
}) {
  const letters = poses ? Object.keys(poses) : [];
  return (
    <div className="flex-1 min-w-0 h-full overflow-y-auto" style={{ background: c.bg }}>
      <div className="mx-auto px-10 py-12" style={{ maxWidth: 940 }}>

        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
          <Chip label="Demo" bg={c.ink} col="#fff" />
          <span style={{ fontSize: 12, fontWeight: 600, color: c.inkSoft }}>
            An interactive walkthrough of a desktop app
          </span>
        </div>

        <h1 style={{ fontSize: 40, fontWeight: 900, color: c.ink, lineHeight: 1.15, marginBottom: 14 }}>
          A tutor for the ASL<br />fingerspelling alphabet
        </h1>
        <p style={{ fontSize: 15, fontWeight: 500, color: c.inkMid, lineHeight: 1.7, marginBottom: 36, maxWidth: 640 }}>
          Sign a letter at your webcam and it tells you which fingers are off,
          one letter at a time, until the shape is right.
        </p>

        <div className="grid gap-5" style={{ gridTemplateColumns: "1fr 1fr" }}>
          <div>
            <Section title="What this page is">
              What you are clicking through is the interface, with sample
              readings in place of live ones. There is no camera and no model
              behind a static web page, so the numbers hold still. Everything
              else — the screens, the flow, the reference hand shapes — is the
              real thing.
            </Section>

            <Section title="Why it needs a camera">
              The tutor works by watching the shape of your hand, so the real
              app needs the webcam to see it. Frames are read one at a time on
              your own machine and discarded immediately: nothing is recorded,
              saved, or uploaded, and no network connection is involved.
            </Section>
          </div>

          <div>
            <Section title="How it grades a sign">
              Two things look at your hand at once. A small convolutional
              network, trained on about 99,000 hand-skeleton images, decides
              whether the sign is right at all. Separately, your hand is
              compared geometrically against a stored reference pose — that
              comparison fills the match bar and colours each knuckle by how
              far off it is. The classifier decides; the geometry explains.
            </Section>

            <Section title="What it leaves out">
              J and Z are the two letters made with movement rather than a held
              shape, so they are not included. Being honest about that is
              cheaper than pretending a still-image model can read motion.
            </Section>
          </div>
        </div>

        <div className="rounded-2xl p-6" style={{ background: c.white, marginBottom: 28 }}>
          <Eyebrow>The 24 reference shapes</Eyebrow>
          <p style={{ fontSize: 12, fontWeight: 500, color: c.inkSoft, lineHeight: 1.6, marginBottom: 16 }}>
            Not drawings. Each one is averaged from real photographs of that
            letter being signed, and is exactly what your hand is scored
            against.
          </p>
          <div className="flex flex-wrap" style={{ gap: 10 }}>
            {letters.map((l) => (
              <div key={l} className="rounded-xl" style={{ background: c.surface, padding: "6px 6px 4px", textAlign: "center" }}>
                <PoseArt pose={poses![l]} size={66} stroke={c.inkMid} />
                <p style={{ fontSize: 11, fontWeight: 800, color: c.ink, lineHeight: 1.2 }}>{l}</p>
              </div>
            ))}
            {letters.length === 0 && (
              <p style={{ fontSize: 12, color: c.inkFaint }}>Loading reference poses…</p>
            )}
          </div>
        </div>

        <div className="rounded-2xl p-6" style={{ background: c.yellow, marginBottom: 32 }}>
          <p style={{ fontSize: 13, fontWeight: 800, color: c.yellowDk, marginBottom: 6 }}>
            Want the working version?
          </p>
          <p style={{ fontSize: 13, fontWeight: 500, color: c.yellowDk, lineHeight: 1.65 }}>
            The tutor itself runs locally in Python — OpenCV for the camera,
            MediaPipe for the hand landmarks, Keras for the classifier. The
            repository has the setup steps, the training scripts, and the
            reasoning behind the scoring design.
          </p>
        </div>

        <p style={{ fontSize: 12, fontWeight: 700, color: c.inkSoft, marginBottom: 12 }}>Try the screens</p>
        <div className="flex gap-3" style={{ maxWidth: 560 }}>
          <Btn label="Teach" badge="1" onClick={() => onMode("teach")} variant="primary" />
          <Btn label="Practice" badge="2" onClick={() => onMode("practice")} />
          <Btn label="Spell" badge="3" onClick={() => onMode("spell")} />
        </div>
      </div>
    </div>
  );
}

// ── root ──────────────────────────────────────────────────────────────────────
export default function App() {
  const [screen, setScreen] = useState<Screen | "home">("home");
  const poses = usePoses();
  return (
    <div className="w-full h-full flex overflow-hidden" style={{ background: c.bg }}>
      <LeftNav screen={screen} onNav={setScreen} />
      <div className="flex flex-1 min-w-0 h-full">
        {screen === "home"     && <HomeScreen onMode={setScreen} />}
        {screen === "teach"    && <TeachScreen onHome={() => setScreen("home")} poses={poses} />}
        {screen === "practice" && <PracticeScreen onHome={() => setScreen("home")} />}
        {screen === "spell"    && <SpellScreen onHome={() => setScreen("home")} poses={poses} />}
        {screen === "about"    && <AboutScreen onMode={setScreen} poses={poses} />}
      </div>
    </div>
  );
}
