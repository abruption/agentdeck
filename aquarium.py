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
PUFFER = ["...BBBB...",  # 복어 (왼쪽을 봄)
          ".BBBBBBB.F",
          "BEBBSBSBFF",
          "BBBBBBBBBF",
          ".BBBSBBB.F",
          "...BBBB..."]
PUFFER_BIG = ["...P.P.P...",  # 부푼 복어
              "..BBBBBBB..",
              "PBBBBBBBBBP",
              ".BEBSBSBBBF",
              "PBBBBBBBBFF",
              ".BBBSBSBBBF",
              "PBBBBBBBBBP",
              "..BBBBBBB..",
              "...P.P.P..."]
PUFFER_COLORS = ((240, 200, 90), (250, 225, 140), (150, 110, 40))
JELLY = [["..JJJJJ..",  # 해파리: 갓을 편 모양 / 오므린 모양
          ".JKJJJJJ.",
          "JKJJJJJJJ",
          "JJJJJJJJJ",
          ".T.T.T.T.",
          ".T..T.T..",
          "..T.T..T.",
          ".T..T.T.."],
         ["...JJJ...",
          "..JKJJJ..",
          ".JJJJJJJ.",
          "..JJJJJ..",
          "..T.T.T..",
          ".T..T..T.",
          "..T.T.T..",
          "..T...T..",
          "...T.T..."]]
JELLY_COLORS = [{"J": (225, 150, 235), "K": (255, 215, 250), "T": (200, 120, 215)},
                {"J": (150, 200, 255), "K": (220, 240, 255), "T": (120, 170, 235)}]
CRAB = [["..E...E..",  # 게: 걷는 두 장면
         "RR.E.E.RR",
         "RRRRRRRRR",
         ".RDRRRDR.",
         "..RRRRR..",
         ".R.R.R.R."],
        ["..E...E..",
         "RR.E.E.RR",
         "RRRRRRRRR",
         ".RDRRRDR.",
         "..RRRRR..",
         "R.R...R.R"]]
CRAB_COLORS = {"R": (230, 85, 60), "D": (165, 50, 40), "E": (20, 20, 30)}
TURTLE = [[".......GGGGGG.......",  # 거북이 (왼쪽을 봄): 지느러미 두 장면. G=등딱지, D=무늬, L=테두리, S=피부
           ".....GGDDGGDDGG.....",
           "....GDDGGDDGGDDG....",
           "SS.GGGGDDGGDDGGGG...",
           "SSSGDDGGGGGGGGDDGG..",
           "SESLLLLLLLLLLLLLLLSS",
           "SSS.SS.......SSS....",
           "...SSS........SSS...",
           "..SSS..........SS..."],
          [".......GGGGGG.......",
           ".....GGDDGGDDGG.....",
           "..SS.GDDGGDDGGDDG...",
           "SSSSGGGGDDGGDDGGGG..",
           "SSSGDDGGGGGGGGDDGG..",
           "SESLLLLLLLLLLLLLLLSS",
           "SSSSSS......SSSSS...",
           "....................",
           "...................."]]
TURTLE_COLORS = {"G": (95, 125, 60), "D": (150, 165, 80), "L": (210, 200, 140), "S": (140, 195, 150), "E": (20, 20, 30)}
OCTOPUS = [["...OOOOO...",  # 문어: 다리 두 장면 (모래 위 / 헤엄칠 때)
            "..OOLOOOO..",
            ".OOOOOOOOO.",
            ".OWEOOOWEO.",
            ".OOOOOOOOO.",
            "..OOOOOOO..",
            ".O.O.O.O.O.",
            "O..O.O.O..O",
            ".O.O...O.O."],
           ["...OOOOO...",
            "..OOLOOOO..",
            ".OOOOOOOOO.",
            ".OWEOOOWEO.",
            ".OOOOOOOOO.",
            "..OOOOOOO..",
            "..O.O.O.O..",
            "..O.O.O.O..",
            ".O..O.O..O.",
            ".O..O.O..O."]]
OCTO_COLORS = [(220, 90, 80), (240, 150, 70), (175, 105, 205)]  # 기분 따라 몸 색이 바뀐다

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
    kind: str = "fish"  # fish | puffer | turtle
    puff: float = 0.0  # 복어가 부푼 채로 남은 시간


@dataclass
class Jelly:
    x: float
    y: float
    colors: dict
    phase: float = field(default_factory=lambda: random.uniform(0, 6.28))


@dataclass
class Crab:
    x: float
    vx: float
    walk: float = 0.0
    rest: float = 0.0  # 멈춰 있는 남은 시간


@dataclass
class Octopus:
    x: float
    y: float
    vx: float = 3.0
    vy: float = 0.0
    walk: float = 0.0
    rest: float = 0.0
    color: int = 0
    shade: tuple = OCTO_COLORS[0]


@dataclass
class Particle:
    x: float
    y: float
    vy: float
    kind: str  # bubble | food | heart | ink
    life: float = 99.0


def _sprite(img: Image.Image, rows: list[str], x: int, y: int, pal: dict, flip: bool = False) -> None:
    for ry, row in enumerate(rows):
        for rx, ch in enumerate(row[::-1] if flip else row):
            c = pal.get(ch)
            if c:
                px, py = x + rx, y + ry
                if 0 <= px < W and 0 <= py < H:
                    img.putpixel((px, py), c)


class Aquarium:
    def __init__(self, n_fish: int = 14, seed: int | None = None) -> None:
        rnd = random.Random(seed)
        self.rnd = rnd
        self.t = 0.0
        self.fish = [Fish(rnd.uniform(5, W - 15), rnd.uniform(8, SAND_Y - 12), rnd.choice([-1, 1]) * rnd.uniform(5, 11),
                          rnd.choice(FISH_SPRITES), rnd.choice(FISH_COLORS)) for _ in range(n_fish)]
        for _ in range(2):  # 복어
            self.fish.append(Fish(rnd.uniform(5, W - 15), rnd.uniform(10, SAND_Y - 14), rnd.choice([-1, 1]) * rnd.uniform(3, 5),
                                  PUFFER, PUFFER_COLORS, kind="puffer"))
        self.jellies = [Jelly(rnd.uniform(10, W - 20), rnd.uniform(8, 40), JELLY_COLORS[i % 2]) for i in range(2)]
        self.crabs = [Crab(rnd.uniform(5, W - 15), rnd.choice([-1, 1]) * rnd.uniform(4, 7)) for _ in range(2)]
        self.fish.append(Fish(rnd.uniform(10, W - 30), rnd.uniform(12, 40), rnd.choice([-1, 1]) * rnd.uniform(2.5, 3.5),
                              TURTLE[0], TURTLE_COLORS, kind="turtle"))  # 거북이는 느긋하게
        self.octopus = Octopus(rnd.uniform(10, W - 25), SAND_Y - len(OCTOPUS[0]) + 1)
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
                slow = 0.45 if f.kind == "turtle" else 1.0
                if f.kind != "turtle":
                    f.vx = math.copysign(max(abs(f.vx), 14), dx)
                elif abs(dx) > 2:
                    f.vx = math.copysign(abs(f.vx), dx)
                f.x += dx / d * 16 * slow * dt
                f.y += dy / d * 12 * slow * dt
                if d < (6 if f.kind == "turtle" else 3):  # 냠
                    near.life = 0
                    self.parts.append(Particle(f.x, f.y - 3, -6, "heart", 1.2))
            else:
                f.x += f.vx * dt
                f.y += math.sin(self.t * 1.6 + f.phase) * 2.2 * dt
                if self.rnd.random() < (0.0015 if f.kind == "turtle" else 0.004):  # 가끔 방향 전환
                    f.vx = -f.vx
            w = len(f.sprite[0])
            if f.x < 1 or f.x > W - w - 1:
                f.vx = -f.vx
                f.x = min(max(f.x, 1), W - w - 1)
            f.y = min(max(f.y, 4), SAND_Y - len(f.sprite) - 1)
        for f in self.fish:  # 복어: 가끔 부풀었다가 가라앉기
            if f.kind == "puffer":
                if f.puff > 0:
                    f.puff -= dt
                    f.sprite = PUFFER_BIG if f.puff > 0 else PUFFER
                elif self.rnd.random() < 0.01:
                    f.puff = self.rnd.uniform(2.5, 4.0)
        for j in self.jellies:  # 해파리: 오므릴 때 위로, 나머지는 천천히 가라앉기
            j.phase += dt
            pulse = math.sin(j.phase * 2.4)
            j.y += (-9 if pulse > 0.6 else 1.6) * dt
            j.x += math.sin(j.phase * 0.5) * 1.2 * dt
            j.y = min(max(j.y, 2), SAND_Y - 16)
            j.x = min(max(j.x, 1), W - 10)
        sand_food = [p for p in self.parts if p.kind == "food" and p.y >= SAND_Y - 2]
        for c in self.crabs:  # 게: 모래 위 옆걸음, 바닥 먹이로 이동
            near = min(sand_food, key=lambda p: abs(p.x - c.x - 4), default=None)
            if near and abs(near.x - c.x - 4) < 45:
                c.rest = 0
                c.vx = math.copysign(abs(c.vx) or 5, near.x - c.x - 4)
                if abs(near.x - c.x - 4) < 2:
                    near.life = 0
                    self.parts.append(Particle(c.x + 4, SAND_Y - 8, -5, "heart", 1.0))
            if c.rest > 0:
                c.rest -= dt
                continue
            c.x += c.vx * dt
            c.walk += dt
            if c.x < 1 or c.x > W - 10:
                c.vx = -c.vx
                c.x = min(max(c.x, 1), W - 10)
            if self.rnd.random() < 0.01:
                c.rest = self.rnd.uniform(1, 3)
                if self.rnd.random() < 0.5:
                    c.vx = -c.vx
        self._step_octopus(dt)
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
            elif p.kind == "ink":  # 먹물: 조금 퍼지며 옅어짐
                p.x += math.sin(p.y * 0.7 + self.t) * 0.2
                p.y += p.vy * dt
                p.life -= dt
            else:  # heart
                p.y += p.vy * dt
                p.life -= dt
        self.parts = [p for p in self.parts if p.life > 0]

    def _step_octopus(self, dt: float) -> None:
        """문어: 모래 위를 기다가 가끔 위로 쭉 솟구치고(가끔 먹물), 천천히 내려앉는다. 몸 색도 바뀐다."""
        o = self.octopus
        floor = SAND_Y - len(OCTOPUS[0]) + 1
        target = OCTO_COLORS[o.color]  # 색은 천천히 섞여서 바뀐다
        o.shade = tuple(int(a + (b - a) * min(1.0, dt * 1.5)) for a, b in zip(o.shade, target))
        if self.rnd.random() < 0.006:
            o.color = (o.color + 1) % len(OCTO_COLORS)
        if o.y < floor or o.vy < 0:  # 헤엄치는 중
            o.vy = min(o.vy + 18 * dt, 5)
            o.y += o.vy * dt
            o.x += o.vx * 1.5 * dt
            o.walk += dt
            if o.y >= floor:
                o.y, o.vy = floor, 0
        else:
            sand_food = [p for p in self.parts if p.kind == "food" and p.y >= SAND_Y - 2]
            near = min(sand_food, key=lambda p: abs(p.x - o.x - 5), default=None)
            if near and abs(near.x - o.x - 5) < 35:
                o.rest = 0
                o.vx = math.copysign(4, near.x - o.x - 5)
                if abs(near.x - o.x - 5) < 2:
                    near.life = 0
                    self.parts.append(Particle(o.x + 5, o.y - 2, -5, "heart", 1.0))
            if o.rest > 0:
                o.rest -= dt
            else:
                o.x += o.vx * dt
                o.walk += dt
                r = self.rnd.random()
                if r < 0.004:  # 솟구치기
                    o.vy = -self.rnd.uniform(22, 30)
                    o.vx = self.rnd.choice([-1, 1]) * self.rnd.uniform(3, 6)
                    if self.rnd.random() < 0.4:  # 가끔 먹물
                        for _ in range(6):
                            self.parts.append(Particle(o.x + 5 + self.rnd.uniform(-3, 3), o.y + 8 + self.rnd.uniform(0, 3),
                                                       self.rnd.uniform(-1, 2), "ink", self.rnd.uniform(1.5, 2.5)))
                elif r < 0.012:
                    o.rest = self.rnd.uniform(1.5, 4)
                    if self.rnd.random() < 0.5:
                        o.vx = -o.vx
        if o.x < 1 or o.x > W - 12:
            o.vx = -o.vx
            o.x = min(max(o.x, 1), W - 12)
        o.y = max(o.y, 4)

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
        for c in self.crabs:  # 게는 수초 앞, 모래 위
            frame = CRAB[int(c.walk * 6) % 2] if c.rest <= 0 else CRAB[0]
            _sprite(img, frame, int(c.x), SAND_Y - len(frame) + 2, CRAB_COLORS)
        o = self.octopus
        swimming = o.y < SAND_Y - len(OCTOPUS[0]) + 1
        frame = OCTOPUS[1] if swimming or (o.rest <= 0 and int(o.walk * 4) % 2) else OCTOPUS[0]
        light = tuple(min(255, v + 50) for v in o.shade)
        _sprite(img, frame, int(o.x), int(o.y) - (len(frame) - len(OCTOPUS[0])) * (0 if swimming else 1),
                {"O": o.shade, "L": light, "W": (240, 240, 240), "E": (20, 20, 30)})
        for j in self.jellies:  # 해파리는 물고기 뒤
            frame = JELLY[1] if math.sin(j.phase * 2.4) > 0.6 else JELLY[0]
            _sprite(img, frame, int(j.x), int(j.y), j.colors)
        for p in self.parts:
            x, y = int(p.x), int(p.y)
            if not (0 <= x < W and 0 <= y < H):
                continue
            if p.kind == "bubble":
                img.putpixel((x, y), (200, 235, 255))
            elif p.kind == "food":
                img.putpixel((x, y), (150, 90, 40))
            elif p.kind == "ink":
                a = max(0.0, min(1.0, p.life / 2)) * 1.2
                a = min(a, 1.0)
                for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)):
                    if 0 <= x + dx < W and 0 <= y + dy < H:
                        r, g, b = img.getpixel((x + dx, y + dy))
                        img.putpixel((x + dx, y + dy), (int(r * (1 - 0.7 * a) + 25 * 0.7 * a), int(g * (1 - 0.7 * a) + 20 * 0.7 * a),
                                                        int(b * (1 - 0.7 * a) + 40 * 0.7 * a)))
            else:
                for dx, dy in ((0, 0), (-1, -1), (1, -1)):
                    if 0 <= x + dx < W and 0 <= y + dy < H:
                        img.putpixel((x + dx, y + dy), (255, 120, 150))
        for f in self.fish:
            if f.kind == "turtle":
                f.sprite = TURTLE[int(self.t * 2.5) % 2]
                _sprite(img, f.sprite, int(f.x), int(f.y), f.colors, flip=f.vx > 0)
                continue
            if f.kind == "puffer":
                body, fin, mark = f.colors
                _sprite(img, f.sprite, int(f.x), int(f.y),
                        {"B": body, "F": fin, "S": mark, "E": (20, 20, 30), "P": (255, 240, 200)}, flip=f.vx > 0)
                continue
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
