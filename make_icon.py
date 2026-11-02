"""Draws the jobslop icon: 'js' with a little drip, on a dark rounded square.
Makes jf.ico, jf.icns and jf.png for the app, and the Chrome extension's icons.
Run once after changing it:  python make_icon.py  (needs Pillow)."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
S = 1024                                   # draw big, shrink for crisp small sizes
BG, BG2, INK, ACCENT = (29, 27, 24), (46, 41, 34), (244, 239, 230), (176, 138, 95)


def draw():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    # soft diagonal gradient inside a rounded square
    grad = Image.new("RGBA", (S, S))
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        t = y / S
        gd.line([(0, y), (S, y)], fill=tuple(int(BG2[i] * (1 - t) + BG[i] * t) for i in range(3)) + (255,))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=230, fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([28, 28, S - 29, S - 29], radius=205, outline=ACCENT + (150,), width=10)   # thin accent ring

    font_path = next((p for p in [r"C:\Windows\Fonts\BOD_R.TTF", r"C:\Windows\Fonts\BASKVILL.TTF",
                                  r"C:\Windows\Fonts\georgia.ttf"] if Path(p).exists()), None)
    font = ImageFont.truetype(font_path, 620) if font_path else ImageFont.load_default()
    text = "js"
    box = d.textbbox((0, 0), text, font=font)
    w, h = box[2] - box[0], box[3] - box[1]
    d.text(((S - w) / 2 - box[0] - 40, (S - h) / 2 - box[1] + 10), text, font=font, fill=INK)

    # the drip (top right): a round drop with a pointed top
    cx, cy, r = 790, 300, 78
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ACCENT)
    d.polygon([(cx - r * 0.92, cy - r * 0.38), (cx, cy - r * 2.3), (cx + r * 0.92, cy - r * 0.38)], fill=ACCENT)
    return img, font_path


img, font_path = draw()
img.resize((512, 512), Image.LANCZOS).save(HERE / "jf.png")
img.save(HERE / "jf.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
img.save(HERE / "jf.icns")                    # Mac app icon
(HERE / "static").mkdir(exist_ok=True)
img.resize((512, 512), Image.LANCZOS).save(HERE / "static" / "jf.png")
icons = HERE / "chrome-extension" / "icons"
icons.mkdir(parents=True, exist_ok=True)
for n in (16, 32, 48, 128):
    img.resize((n, n), Image.LANCZOS).save(icons / f"jf{n}.png")
print("made jf.ico, jf.icns, jf.png and the extension icons with", font_path)
