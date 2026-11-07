"""어항 화면보호기: 덱 전체(버튼 13칸 + 넓은 칸)를 하나의 픽셀아트 화면으로 쓴다.

낮은 해상도 캔버스(140x84, 칸 하나 = 28x28)에 그린 뒤 칸 크기로 잘라 NEAREST 로 키워
도트 느낌을 살린다. 물고기는 칸 경계를 넘나들며 헤엄치고, 칸을 누르면 그 자리에 먹이가 떨어진다.
"""

from __future__ import annotations

import io
import math
import random
from dataclasses import dataclass, field

from PIL import Image, ImageDraw

CELL = 28  # 칸 하나의 저해상도 픽셀 수
COLS, ROWS = 5, 3
W, H = COLS * CELL, ROWS * CELL  # 140 x 84
SAND_Y = H - 7

# 물고기 도트 (왼쪽을 보는 모양, 오른쪽으로 갈 때 좌우 반전). B=몸, F=지느러미/꼬리, E=눈, S=무늬
FISH_SPRITES = [  # 칸(28px)의 절반 정도 크기
    ["....BBBBB.....",
     "..BBBBBBBBB..FF",
     ".BBEEBBSBBBBFFF",
     "BBBEEBBSBBBBFF.",
     ".BBBBBBSBBBBFFF",
     "..BBBBBBBBB..FF",
     "....BBBBB.....",
     ],
    ["...BBBB....",
     ".BBBBBBB.FF",
     "BBEBBBBBBFF",
     "BBBBBBBBFF.",
     ".BBBBBBB.FF",
     "...BBBB....",
     ],
    ["......BB.......",
     "....BBBBBB...FF",
     "..BBBBSSBBB.FFF",
     ".BEBBBSSBBBBFF.",
     "..BBBBSSBBB.FFF",
     "....BBBBBB...FF",
     "......BB.......",
     ],
]
FISH_COLORS = [  # (몸, 지느러미, 무늬)
    ((255, 140, 66), (255, 196, 120), (255, 255, 255)),   # 주황
    ((255, 214, 64), (255, 236, 150), (240, 150, 40)),    # 노랑
    ((90, 200, 250), (170, 230, 255), (40, 120, 200)),    # 하늘
    ((255, 110, 140), (255, 180, 200), (255, 255, 255)),  # 분홍
    ((150, 230, 120), (200, 250, 170), (70, 150, 60)),    # 연두
]


@dataclass
class Fish:
    x: float
    y: float
    vx: float
    sprite: list[str]
    colors: tuple
    phase: float = field(default_factory=lambda: random.uniform(0, 6.28))
    target: tuple[float, float] | None = None


@dataclass
class Particle:
    x: float
    y: float
    vy: float
    kind: str  # bubble | food | heart
    life: float = 99.0


class Aquarium:
    def __init__(self, n_fish: int = 6, seed: int | None = None) -> None:
        rnd = random.Random(seed)
        self.rnd = rnd
        self.t = 0.0
        self.fish = [Fish(rnd.uniform(5, W - 15), rnd.uniform(8, SAND_Y - 12), rnd.choice([-1, 1]) * rnd.uniform(5, 11),
                          rnd.choice(FISH_SPRITES), rnd.choice(FISH_COLORS)) for _ in range(n_fish)]
        self.parts: list[Particle] = []
        self.weeds = [(x, rnd.randint(10, 26), rnd.choice([(46, 160, 90), (70, 190, 110), (30, 130, 80)]))
                      for x in sorted(rnd.sample(range(3, W - 3), 14))]
        self.pebbles = [(rnd.randint(0, W - 1), rnd.randint(SAND_Y + 1, H - 1), rnd.choice([(170, 140, 95), (215, 190, 140), (150, 120, 85)]))
                        for _ in range(45)]

    # ---- 상호작용 ----
    def feed(self, tile: int) -> None:
        """칸 번호(0~12, 넓은 칸 13)에 먹이를 떨어뜨린다."""
        if tile >= 13:
            cx, top = 4 * CELL, 2 * CELL
        else:
            cx, top = (tile % COLS) * CELL + CELL // 2, (tile // COLS) * CELL
        for _ in range(4):
            self.parts.append(Particle(cx + self.rnd.uniform(-5, 5), top + self.rnd.uniform(0, 4),
                                       self.rnd.uniform(4, 7), "food"))

    # ---- 시뮬레이션 ----
    def step(self, dt: float) -> None:
        self.t += dt
        foods = [p for p in self.parts if p.kind == "food"]
        for f in self.fish:
            near = min(foods, key=lambda p: (p.x - f.x) ** 2 + (p.y - f.y) ** 2, default=None)
            if near and (near.x - f.x) ** 2 + (near.y - f.y) ** 2 < 60 ** 2:  # 먹이 쫓기
                dx, dy = near.x - f.x, near.y - f.y
                d = math.hypot(dx, dy) or 1
                f.vx = math.copysign(max(abs(f.vx), 14), dx)
                f.x += dx / d * 16 * dt
                f.y += dy / d * 12 * dt
                if d < 3:  # 냠
                    near.life = 0
                    self.parts.append(Particle(f.x, f.y - 3, -6, "heart", 1.2))
            else:
                f.x += f.vx * dt
                f.y += math.sin(self.t * 1.6 + f.phase) * 2.2 * dt
                if self.rnd.random() < 0.004:  # 가끔 방향 전환
                    f.vx = -f.vx
            w = len(f.sprite[0])
            if f.x < 1 or f.x > W - w - 1:
                f.vx = -f.vx
                f.x = min(max(f.x, 1), W - w - 1)
            f.y = min(max(f.y, 4), SAND_Y - len(f.sprite) - 1)
        # 거품: 수초 아래·무작위에서 생성
        if self.rnd.random() < 0.35:
            self.parts.append(Particle(self.rnd.uniform(2, W - 2), SAND_Y - 1, -self.rnd.uniform(6, 12), "bubble"))
        for p in self.parts:
            if p.kind == "bubble":
                p.y += p.vy * dt
                p.x += math.sin(self.t * 3 + p.y * 0.3) * 0.15
                if p.y < 1:
                    p.life = 0
            elif p.kind == "food":
                p.y = min(p.y + p.vy * dt, SAND_Y - 1)
                p.life -= dt * (0.08 if p.y < SAND_Y - 1 else 0.4)
            else:  # heart
                p.y += p.vy * dt
                p.life -= dt
        self.parts = [p for p in self.parts if p.life > 0]

    # ---- 그리기 ----
    def canvas(self) -> Image.Image:
        img = Image.new("RGB", (W, H))
        d = ImageDraw.Draw(img)
        for y in range(H):  # 물 그라데이션 (위 밝게)
            t = y / H
            d.line([(0, y), (W, y)], fill=(int(30 - 14 * t), int(110 - 50 * t), int(190 - 70 * t)))
        for i in range(3):  # 천천히 움직이는 빛줄기
            x0 = int((self.t * 3 + i * 55) % (W + 40)) - 20
            for y in range(SAND_Y):
                for k, add in ((0, 10), (1, 14), (2, 10)):  # 3px 폭, 가운데가 조금 더 밝게
                    x = x0 + y // 3 + k
                    if 0 <= x < W:
                        r, g, b = img.getpixel((x, y))
                        img.putpixel((x, y), (min(r + add, 255), min(g + add + 4, 255), min(b + add + 4, 255)))
        d.rectangle((0, SAND_Y, W, H), fill=(196, 168, 112))
        for x, y, c in self.pebbles:
            img.putpixel((x, y), c)
        for x, h, c in self.weeds:  # 수초: 위로 갈수록 흔들림
            for k in range(h):
                sway = int(round(math.sin(self.t * 1.3 + x * 0.7 + k * 0.25) * (k / h) * 2.2))
                px = x + sway
                if 0 <= px < W:
                    img.putpixel((px, SAND_Y - k), c)
                    if k % 4 == 2 and 0 <= px + 1 < W:
                        img.putpixel((px + 1, SAND_Y - k), c)
        for p in self.parts:
            x, y = int(p.x), int(p.y)
            if not (0 <= x < W and 0 <= y < H):
                continue
            if p.kind == "bubble":
                img.putpixel((x, y), (200, 235, 255))
            elif p.kind == "food":
                img.putpixel((x, y), (150, 90, 40))
            else:
                for dx, dy in ((0, 0), (-1, -1), (1, -1)):
                    if 0 <= x + dx < W and 0 <= y + dy < H:
                        img.putpixel((x + dx, y + dy), (255, 120, 150))
        for f in self.fish:
            body, fin, mark = f.colors
            right = f.vx > 0
            for ry, row in enumerate(f.sprite):
                for rx, ch in enumerate(row[::-1] if right else row):  # 도트는 왼쪽을 보는 모양
                    c = {"B": body, "F": fin, "S": mark, "E": (20, 20, 30)}.get(ch)
                    if c:
                        px, py = int(f.x) + rx, int(f.y) + ry
                        if 0 <= px < W and 0 <= py < H:
                            img.putpixel((px, py), c)
        return img

    def tiles(self, hint: str | None = None) -> tuple[dict[int, bytes], bytes]:
        """(칸 0~12 PNG, 넓은 칸 PNG). 저해상도 캔버스를 잘라 NEAREST 로 키운다."""
        img = self.canvas()
        out: dict[int, bytes] = {}
        for i in range(13):
            c, r = i % COLS, i // COLS
            out[i] = _png(img.crop((c * CELL, r * CELL, (c + 1) * CELL, (r + 1) * CELL)).resize((196, 196), Image.NEAREST))
        wide = img.crop((3 * CELL, 2 * CELL, 5 * CELL, 3 * CELL)).resize((458, 196), Image.NEAREST)
        if hint:
            from clock import _kr  # 첫 몇 초 안내
            dw = ImageDraw.Draw(wide)
            dw.rounded_rectangle((10, 150, 448, 188), 10, fill=(10, 30, 60))
            from i18n import tr

            dw.text((229, 169), tr(hint), font=_kr(20, 4), fill=(220, 235, 255), anchor="mm")
        return out, _png(wide)


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=False, compress_level=3)
    return buf.getvalue()


if __name__ == "__main__":
    import sys

    aq = Aquarium(seed=3)
    frames = []
    for i in range(40):
        aq.step(0.2)
        if i == 10:
            aq.feed(7)
        frames.append(aq.canvas().resize((W * 6, H * 6), Image.NEAREST))
    frames[0].save(sys.argv[1], save_all=True, append_images=frames[1:], duration=200, loop=0)
