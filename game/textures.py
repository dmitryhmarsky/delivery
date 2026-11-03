"""Процедурные текстуры: ничего скачивать не нужно.

`python tools/make_textures.py` кладёт PNG в assets/textures/.
Игра сама их создаёт при первом запуске, если папка пустая.
"""
from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 128


def _clamp(v: int) -> int:
    return max(0, min(255, v))


def _noise(base, spread, seed) -> Image.Image:
    rnd = random.Random(seed)
    img = Image.new("RGB", (SIZE, SIZE))
    px = []
    for _ in range(SIZE * SIZE):
        d = rnd.randint(-spread, spread)
        px.append(tuple(_clamp(c + d) for c in base))
    img.putdata(px)
    return img


def asphalt() -> Image.Image:
    img = _noise((68, 70, 76), 12, 1)
    d = ImageDraw.Draw(img)
    rnd = random.Random(11)
    for _ in range(60):
        x, y = rnd.randrange(SIZE), rnd.randrange(SIZE)
        v = rnd.choice((40, 110))
        d.point((x, y), fill=(v, v, v + 4))
    return img


def grass() -> Image.Image:
    img = _noise((74, 140, 66), 16, 2)
    d = ImageDraw.Draw(img)
    rnd = random.Random(22)
    for _ in range(140):
        x, y = rnd.randrange(SIZE), rnd.randrange(SIZE - 4)
        shade = rnd.choice(((52, 110, 48), (98, 170, 84)))
        d.line((x, y, x, y + rnd.randint(2, 4)), fill=shade)
    return img


def _bricks(brick_rgb, mortar_rgb, rows, seed) -> Image.Image:
    rnd = random.Random(seed)
    img = Image.new("RGB", (SIZE, SIZE), mortar_rgb)
    d = ImageDraw.Draw(img)
    bh = SIZE // rows
    bw = bh * 2
    for r in range(rows):
        offset = (bw // 2) if r % 2 else 0
        for x in range(-bw, SIZE + bw, bw):
            jitter = rnd.randint(-14, 14)
            col = tuple(_clamp(c + jitter) for c in brick_rgb)
            x0 = x + offset
            d.rectangle((x0 + 1, r * bh + 1, x0 + bw - 2, r * bh + bh - 2), fill=col)
    return img


def brick() -> Image.Image:
    return _bricks((172, 82, 62), (196, 190, 178), 8, 3)


def roof() -> Image.Image:
    return _bricks((120, 48, 42), (70, 30, 28), 16, 4)


def wood() -> Image.Image:
    img = _noise((150, 104, 60), 8, 5)
    d = ImageDraw.Draw(img)
    rnd = random.Random(55)
    plank = SIZE // 4
    for i in range(4):
        d.line((i * plank, 0, i * plank, SIZE), fill=(70, 46, 26), width=2)
        for _ in range(10):
            x = i * plank + rnd.randint(3, plank - 3)
            y = rnd.randrange(SIZE - 16)
            d.line((x, y, x, y + rnd.randint(6, 16)), fill=(128, 86, 48))
    return img


def concrete() -> Image.Image:
    img = _noise((176, 176, 172), 8, 6)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, SIZE - 1, SIZE - 1), outline=(120, 120, 116), width=2)
    d.line((SIZE // 2, 0, SIZE // 2, SIZE), fill=(130, 130, 126), width=1)
    d.line((0, SIZE // 2, SIZE, SIZE // 2), fill=(130, 130, 126), width=1)
    return img


def door() -> Image.Image:
    img = _noise((110, 70, 38), 7, 7)
    d = ImageDraw.Draw(img)
    d.rectangle((14, 12, SIZE - 15, 56), outline=(70, 42, 20), width=3)
    d.rectangle((14, 70, SIZE - 15, SIZE - 14), outline=(70, 42, 20), width=3)
    d.ellipse((SIZE - 34, 62, SIZE - 24, 72), fill=(220, 190, 70))
    return img


def cardboard() -> Image.Image:
    img = _noise((196, 150, 92), 9, 8)
    d = ImageDraw.Draw(img)
    d.rectangle((SIZE // 2 - 8, 0, SIZE // 2 + 8, SIZE), fill=(214, 190, 130))
    return img


ALL = {
    "asphalt": asphalt,
    "grass": grass,
    "brick": brick,
    "roof": roof,
    "wood": wood,
    "concrete": concrete,
    "door": door,
    "cardboard": cardboard,
}


def generate_all(out_dir: Path) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, fn in ALL.items():
        fn().save(out_dir / f"{name}.png")


def ensure_textures(out_dir: Path) -> None:
    out_dir = Path(out_dir)
    if any(not (out_dir / f"{n}.png").exists() for n in ALL):
        generate_all(out_dir)
