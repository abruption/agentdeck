"""불멍: 15칸 전체가 하나의 벽난로 (어항처럼 저해상도 도트 → 칸마다 키움).

불꽃은 고전 'Doom fire' 방식(아래 줄 열기가 위로 번지며 식어 감)으로 만든다.
칸을 짧게 누르면 그 자리에 장작을 던져 불길이 확 일고 불티가 튄다.
"""

from __future__ import annotations

import io
import math
import random

from PIL import Image, ImageDraw

CELL = 28
COLS, ROWS = 5, 3
W, H = COLS * CELL, ROWS * CELL  # 140 x 84
FIRE_TOP = 4  # 불꽃이 올라갈 수 있는 가장 높은 줄
FLOOR = H - 7  # 화로 바닥 높이
FIRE_BASE = FLOOR - 9  # 불꽃이 시작되는 줄 (장작 더미 속)
FH = FIRE_BASE - FIRE_TOP + 1  # 불꽃 격자 높이
CX = W // 2  # 장작 더미 가운데
# 장작: (x0, y0, x1, y1, 굵기) — 엇갈려 쌓은 모닥불 더미 (뒤 → 앞 순서로 그림)
LOGS = [(CX - 26, FLOOR - 9, CX + 26, FLOOR - 9, 7),       # 뒤에 가로로 놓인 장작
        (CX - 30, FLOOR - 1, CX + 12, FLOOR - 15, 7),      # 왼쪽에서 비스듬히
        (CX + 30, FLOOR - 1, CX - 12, FLOOR - 15, 7),      # 오른쪽에서 비스듬히
        (CX - 34, FLOOR - 1, CX + 34, FLOOR - 1, 8)]       # 맨 앞 가로 장작


def _palette() -> list[tuple[int, int, int]]:
    """검정 → 짙은 빨강 → 주황 → 노랑 → 흰빛 (37단계)."""
    keys = [(0, (0, 0, 0)), (6, (60, 8, 6)), (12, (140, 24, 8)), (18, (205, 60, 10)), (24, (240, 120, 20)),
            (30, (252, 190, 60)), (34, (255, 236, 150)), (36, (255, 252, 230))]
    pal = []
    for i in range(37):
        for (a, ca), (b, cb) in zip(keys, keys[1:]):
            if a <= i <= b:
                t = (i - a) / (b - a)
                pal.append(tuple(int(x + (y - x) * t) for x, y in zip(ca, cb)))  # type: ignore[arg-type]
                break
    return pal


PAL = _palette()


class Fireplace:
    def __init__(self, seed: int | None = None) -> None:
        self.rnd = random.Random(seed)
        self.fire = [[0] * W for _ in range(FH)]
        self.heat = [0.0] * W  # 바닥 줄 열기 (장작이 있는 곳이 뜨겁다)
        self.embers = [(CX + self.rnd.randint(-30, 30), FLOOR + self.rnd.randint(-2, 1)) for _ in range(70)]
        self.flare: list[tuple[int, float]] = []  # (x, 남은 시간) 장작을 던진 자리
        self.sparks: list[list[float]] = []  # [x, y, vx, vy, life]
        self.t = 0.0
        self._base()
        for _ in range(60):  # 처음부터 불이 붙어 있게
            self._spread()

    def _base(self) -> None:
        """바닥 열기: 장작 위는 은근하게, 천천히 움직이는 불기둥 몇 개는 뜨겁게 → 혀처럼 솟는 불꽃."""
        cores = [CX + (k - 1) * 13 + 4 * math.sin(self.t * (0.6 + 0.2 * k) + k * 1.9) for k in range(3)]
        for x in range(W):
            h = 0.0
            if abs(x - CX) < 30:  # 장작 더미 위만 탄다
                h = 16 * (1 - abs(x - CX) / 30)
                for k, c in enumerate(cores):
                    amp = 0.8 + 0.2 * math.sin(self.t * (1.3 + 0.4 * k) + k)
                    h = max(h, 36 * amp * math.exp(-((x - c) / (6.5 if k != 1 else 8)) ** 2))
            for fx, left in self.flare:
                if abs(x - fx) < 26:
                    h = max(h, 36 * min(1.0, left) * math.exp(-((x - fx) / 14) ** 2) + 6)
            self.heat[x] = min(36.0, h)

    def _spread(self) -> None:
        f, rnd = self.fire, self.rnd
        bottom = FH - 1
        for x in range(W):  # 바닥 줄 = 장작 열기 (살짝 일렁임)
            f[bottom][x] = int(max(0, min(36, self.heat[x] - rnd.random() * 3)))
        sway = math.sin(self.t * 0.6) * 0.35  # 아주 약한 바람 (좌우로 번갈아 살짝)
        for y in range(1, FH):
            row, up = f[y], f[y - 1]
            for x in range(W):
                v = row[x]
                if v == 0:
                    up[x] = 0
                    continue
                r = rnd.randint(0, 2)
                dst = min(W - 1, max(0, x - r + 1 + (1 if rnd.random() < abs(sway) else 0) * (1 if sway > 0 else -1)))
                up[dst] = max(0, v - (r & 1) * (1 if rnd.random() < 0.85 else 0) - (1 if rnd.random() < 0.08 else 0))

    def feed(self, tile: int) -> None:
        """그 칸 자리에 장작 던지기: 불길이 확 일고 불티가 튄다."""
        c = (tile % COLS) if tile < 13 else 3.5
        x = int(CX + max(-18, min(18, (c * CELL + CELL / 2 - CX) * 0.4)))  # 누른 쪽으로 살짝 치우친 장작 더미 위
        self.flare.append((x, 2.5))
        for _ in range(28):
            self.sparks.append([x + self.rnd.uniform(-12, 12), FIRE_BASE - 2, self.rnd.uniform(-1.2, 1.2),
                                self.rnd.uniform(-5.5, -2.5), self.rnd.uniform(1.0, 2.4)])
        try:
            from sfx import play
            play("whoosh", 0, 0.6)
        except Exception:
            pass

    def step(self, dt: float) -> None:
        self.t += dt
        self.flare = [(x, left - dt) for x, left in self.flare if left - dt > 0]
        self._base()
        for _ in range(2):
            self._spread()
        if self.rnd.random() < 0.5:  # 평소에도 가끔 불티
            x = self.rnd.uniform(CX - 20, CX + 20)
            self.sparks.append([x, FIRE_BASE - 4, self.rnd.uniform(-0.6, 0.6), self.rnd.uniform(-3.5, -1.5),
                                self.rnd.uniform(0.8, 1.8)])
        alive = []
        for s in self.sparks:
            s[0] += s[2] * dt * 6 + math.sin(self.t * 3 + s[1]) * 0.3
            s[1] += s[3] * dt * 6
            s[3] += 0.4 * dt  # 살짝 느려짐
            s[4] -= dt
            if s[4] > 0 and s[1] > 0:
                alive.append(s)
        self.sparks = alive[-120:]
        if self.rnd.random() < 0.12:  # 장작 타닥 소리
            try:
                from sfx import play
                play("crackle", 0.3, 0.35)
            except Exception:
                pass

    def canvas(self) -> Image.Image:
        glow = sum(self.heat) / (60 * 36)  # 불 세기만큼 벽난로 안이 밝아짐
        flick = 0.85 + 0.15 * math.sin(self.t * 9) * math.sin(self.t * 4.3)
        img = Image.new("RGB", (W, H), (10, 7, 6))
        d = ImageDraw.Draw(img)
        for y in range(0, FLOOR, 6):  # 안쪽 벽돌: 불 가까운 곳일수록 밝게
            off = 0 if (y // 6) % 2 else 7
            for x in range(-off, W, 14):
                dist = math.hypot((x + 7 - CX) / 70, (y - FIRE_BASE) / 60)
                k = max(0.0, (0.15 + 0.55 * glow * flick) * (1.1 - dist))
                d.rectangle((x + 1, y + 1, x + 12, y + 4), fill=(int(78 * k + 12), int(34 * k + 8), int(22 * k + 7)))
        px = img.load()
        f = self.fire
        for y in range(FH):  # 불꽃 (이웃과 평균 내서 자글거림 줄이기)
            yy = FIRE_TOP + y
            row = f[y]
            dn = f[min(FH - 1, y + 1)]
            for x in range(W):
                v = (2 * row[x] + row[x - 1 if x else x] + row[x + 1 if x < W - 1 else x] + dn[x]) / 5
                v = int(36 * (v / 36) ** 1.25 + 0.5)
                if v > 2:
                    r, g, b = PAL[v]
                    if v < 9:  # 끝자락은 배경과 섞이게
                        br, bg_, bb = px[x, yy]
                        a = v / 9
                        r, g, b = int(br + (r - br) * a), int(bg_ + (g - bg_) * a), int(bb + (b - bb) * a)
                    px[x, yy] = (r, g, b)
        glowimg = Image.new("RGBA", (W, H), (0, 0, 0, 0))  # 장작 더미 뒤 붉은 빛 (불꽃과 장작을 이어 줌)
        gd = ImageDraw.Draw(glowimg)
        for k in range(10, 0, -1):
            a = int(16 * flick * (11 - k) / 10)
            gd.ellipse((CX - 3 * k - 12, FIRE_BASE - 2 * k, CX + 3 * k + 12, FLOOR + 2 * k), fill=(255, 110, 30, a))
        img.paste(glowimg, (0, 0), glowimg)
        d = ImageDraw.Draw(img)
        d.rectangle((0, FLOOR + 2, W, H), fill=(26, 20, 18))  # 화로 바닥
        for x, y in self.embers:  # 숯불 더미
            heat = 0.5 + 0.5 * math.sin(self.t * 3 + x * 1.7 + y)
            d.point((x, y), fill=(int(150 + 105 * heat), int(40 + 90 * heat * heat), 20))
        for n, (x0, y0, x1, y1, w) in enumerate(LOGS):  # 장작: 껍질 · 위쪽 불빛 · 갈라진 틈 불씨 · 단면 나이테
            d.line((x0, y0, x1, y1), fill=(58, 34, 20), width=w)
            d.line((x0, y0 - w // 2 + 1, x1, y1 - w // 2 + 1), fill=(120, 62, 30), width=2)  # 불빛 받은 윗면
            steps = int(math.hypot(x1 - x0, y1 - y0) / 4)
            for k in range(1, steps):
                t = k / steps
                cx, cy = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
                if (k * 5 + n * 3 + int(self.t * 5)) % 7 < 2:  # 틈에서 깜빡이는 불씨
                    d.point((int(cx), int(cy)), fill=(255, 150 + (k % 3) * 30, 40))
                elif k % 3 == 0:
                    d.point((int(cx), int(cy) + 1), fill=(40, 22, 12))  # 껍질 결
            for ex, ey in ((x0, y0), (x1, y1)) if n in (0, 3) else ((x0, y0),):
                r = w // 2
                d.ellipse((ex - r, ey - r, ex + r, ey + r), fill=(176, 128, 82), outline=(70, 40, 22))  # 단면
                d.ellipse((ex - 1, ey - 1, ex + 1, ey + 1), fill=(120, 80, 48))
        for x, y, _, _, life in self.sparks:  # 불티
            if 0 <= x < W and 0 <= y < H:
                c = (255, 220, 120) if life > 1.0 else (255, 140, 50)
                px[int(x), int(y)] = c
        # 벽난로 돌 테두리 (어두운 아치)
        stone = (34, 30, 30)
        d.rectangle((0, 0, 9, H), fill=stone)
        d.rectangle((W - 10, 0, W, H), fill=stone)
        d.rectangle((0, 0, W, 3), fill=stone)
        for y in range(4, H, 9):
            d.line((0, y, 9, y), fill=(22, 19, 19))
            d.line((W - 10, y + 4, W, y + 4), fill=(22, 19, 19))
        return img

    def tiles(self, hint: str | None = None) -> tuple[dict[int, bytes], bytes]:
        img = self.canvas()
        out: dict[int, bytes] = {}
        for i in range(13):
            c, r = i % COLS, i // COLS
            out[i] = _png(img.crop((c * CELL, r * CELL, (c + 1) * CELL, (r + 1) * CELL)).resize((196, 196), Image.NEAREST))
        wide = img.crop((3 * CELL, 2 * CELL, 5 * CELL, 3 * CELL)).resize((458, 196), Image.NEAREST)
        if hint:
            from clock import _kr
            from i18n import tr

            dw = ImageDraw.Draw(wide)
            dw.rounded_rectangle((10, 150, 448, 188), 10, fill=(50, 20, 8))
            dw.text((229, 169), tr(hint), font=_kr(20, 4), fill=(255, 225, 190), anchor="mm")
        return out, _png(wide)


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=False, compress_level=3)
    return buf.getvalue()


if __name__ == "__main__":
    import sys

    fp = Fireplace(seed=3)
    frames = []
    for i in range(40):
        fp.step(0.2)
        if i == 15:
            fp.feed(7)
        frames.append(fp.canvas().resize((W * 6, H * 6), Image.NEAREST))
    frames[0].save(sys.argv[1], save_all=True, append_images=frames[1:], duration=200, loop=0)
