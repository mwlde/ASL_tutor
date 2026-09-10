"""Generate the web build's favicon, touch icon, and social card.

These are placeholders drawn from the app's own theme — the same graduation
cap and palette the tutor's icon rail uses — so the deployed site is not
missing an icon before a designed one exists. Replace the files it writes with
real artwork whenever you have it; nothing regenerates them automatically.

    .venv311/bin/python -m scripts.make_web_icons
"""

from pathlib import Path

from src.tutor import theme as t

OUT_DIR = Path("design/public")

TITLE = "ASL Tutor"
TAGLINE = "Learn the fingerspelling alphabet with your webcam"


def _icon(size, radius_frac=0.22, pad_frac=0.12):
    """A rounded yellow tile with the graduation cap, at `size` px square."""
    ui = t.Canvas(size=(size, size), background=t.BG)
    radius = int(size * radius_frac)
    ui.rect((0, 0, size, size), t.YELLOW, radius=radius)
    pad = size * pad_frac
    t.mortarboard(ui, (pad, pad, size - pad * 2, size - pad * 2), t.INK)
    return ui.image


def _social_card(width=1200, height=630):
    """Open Graph card: the icon, the title, and one line of description."""
    ui = t.Canvas(size=(width, height), background=t.BG)

    for color, center, blob, alpha in (
        (t.YELLOW, (width - 120, 90), 420, 0.55),
        (t.MINT, (140, height - 90), 340, 0.45),
        (t.PINK, (width - 260, height - 120), 240, 0.30),
    ):
        ui.draw.polygon(t.blob_points(center, blob), fill=t.rgba(color, alpha))

    mark = 132
    x, y = 96, 150
    ui.rect((x, y, mark, mark), t.YELLOW, radius=30)
    t.mortarboard(ui, (x + 16, y + 16, mark - 32, mark - 32), t.INK)

    ui.text(TITLE, (x, y + mark + 44), 92, t.WEIGHT_BLACK, t.INK)
    ui.text(TAGLINE, (x, y + mark + 156), 30, t.WEIGHT_MEDIUM, t.INK_MID)
    ui.text("24 static letters  ·  runs on your own camera",
            (x, y + mark + 200), 22, t.WEIGHT_SEMI, t.TERRA)
    return ui.image


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for name, image in (
        ("favicon.png", _icon(512)),
        ("apple-touch-icon.png", _icon(180)),
        ("og.png", _social_card()),
    ):
        path = OUT_DIR / name
        image.save(path)
        written.append(f"{path} ({path.stat().st_size // 1024} KB)")
    print("wrote:\n  " + "\n  ".join(written))


if __name__ == "__main__":
    main()
