"""멍때리기 화면 더: 비 오는 창가(비멍) · 노을 바닷가(바다). 어항·불멍과 같은 방식(140x84 도트 → 칸마다 키움).

비멍: 창밖 도시 불빛이 번지고 빗줄기가 내리며, 유리에 맺힌 물방울이 흘러내린다. 누르면 번개.
바다: 노을 하늘 아래 파도가 밀려왔다 빠지고 물결에 햇빛이 반짝인다. 누르면 큰 파도.
"""

from __future__ import annotations

import io
import math
import random

from PIL import Image, ImageDraw

CELL = 28
COLS, ROWS = 5, 3
W, H = COLS * CELL, ROWS * CELL  # 140 x 84


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=False, compress_level=3)
    return buf.getvalue()


def _mix(a, b, t):
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))


class _Scene:
    hint_bg = (20, 24, 40)
    hint_fg = (220, 230, 255)

    def canvas(self) -> Image.Image:  # pragma: no cover - 각 장면이 구현
        raise NotImplementedError

    def tiles(self, hint: str | None = None) -> tuple[dict[int, bytes], bytes]:
        img = self.canvas()
        out = {}
        for i in range(13):
            c, r = i % COLS, i // COLS
            out[i] = _png(img.crop((c * CELL, r * CELL, (c + 1) * CELL, (r + 1) * CELL)).resize((196, 196), Image.NEAREST))
        wide = img.crop((3 * CELL, 2 * CELL, 5 * CELL, 3 * CELL)).resize((458, 196), Image.NEAREST)
        if hint:
            from clock import _kr
            from i18n import tr

            dw = ImageDraw.Draw(wide)
            dw.rounded_rectangle((10, 150, 448, 188), 10, fill=self.hint_bg)
            dw.text((229, 169), tr(hint), font=_kr(20, 4), fill=self.hint_fg, anchor="mm")
        return out, _png(wide)


# ---------- 비 오는 창가 ----------
class Rain(_Scene):
    """창가에서 보는 비 오는 밤거리. 칸 사이 테두리가 창살처럼 보이게 창 전체를 하나로 그린다."""
    hint_bg = (16, 22, 36)
    SILL = H - 9  # 창틀(실내) 시작 줄
    ROAD = H - 18  # 길 시작 줄
    LAMP_X = 104

    def __init__(self, seed: int | None = None) -> None:
        self.rnd = random.Random(seed)
        r = self.rnd
        self.t = 0.0
        self.far, self.near = [], []
        x = -4
        while x < W:  # 먼 건물: 높고 흐릿
            w = r.randint(8, 16)
            self.far.append((x, r.randint(12, 34), w, [(r.random() < 0.3) for _ in range(40)]))
            x += w + r.randint(0, 2)
        x = -6
        while x < W:  # 가까운 건물: 낮고 진함, 창문 불빛이 따뜻함
            w = r.randint(14, 26)
            self.near.append((x, r.randint(34, 50), w, [(r.random() < 0.42) for _ in range(60)], r.uniform(0, 6)))
            x += w + r.randint(2, 6)
        # 빗줄기 3겹: [x, y, 속도, 길이, 밝기]
        self.drops = []
        for layer, (n, sp, ln, br) in enumerate(((60, 30, 2, 0.35), (40, 48, 3, 0.6), (18, 70, 5, 1.0))):
            for _ in range(n):
                self.drops.append([r.uniform(0, W), r.uniform(0, H), sp * r.uniform(0.9, 1.1), ln, br])
        self.beads = [[r.uniform(2, W - 2), r.uniform(0, self.SILL - 4), r.uniform(0, 1), r.choice((1, 1, 2))]
                      for _ in range(30)]
        self.splash: list[list[float]] = []  # 창틀에 튀는 물 [x, 남은 시간]
        self.flash = 0.0
        self.bolt: list[tuple[int, int]] = []

    def feed(self, tile: int) -> None:
        self._lightning((tile % COLS) * CELL + CELL // 2 if tile < 13 else 100)
        try:
            from sfx import play
            play("thunder", 0.5, 0.9)
        except Exception:
            pass

    def _lightning(self, x: int) -> None:
        self.flash = 1.0
        pts, y = [], 0
        while y < 30:  # 들쭉날쭉한 번개 줄기
            pts.append((x, y))
            x += self.rnd.randint(-4, 4)
            y += self.rnd.randint(3, 6)
        self.bolt = pts

    def step(self, dt: float) -> None:
        self.t += dt
        self.flash = max(0.0, self.flash - dt * 1.6)
        if self.flash < 0.5:
            self.bolt = []
        if self.rnd.random() < dt * 0.015:  # 아주 가끔 먼 번개
            self._lightning(self.rnd.randint(10, W - 10))
            self.flash = 0.55
        for d in self.drops:
            d[1] += d[2] * dt
            d[0] -= d[2] * dt * 0.18
            if d[1] > self.SILL:
                if d[4] > 0.9 and self.rnd.random() < 0.5:
                    self.splash.append([d[0], 0.25])
                d[0], d[1] = self.rnd.uniform(0, W + 12), self.rnd.uniform(-8, 0)
        self.splash = [[x, left - dt] for x, left in self.splash if left - dt > 0][-30:]
        for b in self.beads:  # 유리 물방울: 맺혀 있다가 무거워지면 주르륵
            if b[2] > 0.95:
                b[1] += dt * 20
                b[0] += math.sin(self.t * 5 + b[1]) * 0.05
                b[2] -= dt * 0.2
            else:
                b[2] += dt * self.rnd.uniform(0, 0.2)
            if b[1] > self.SILL - 2:
                b[:] = [self.rnd.uniform(2, W - 2), self.rnd.uniform(-4, self.SILL * 0.5), 0, self.rnd.choice((1, 1, 2))]

    def canvas(self) -> Image.Image:
        fl = self.flash
        img = Image.new("RGB", (W, H))
        d = ImageDraw.Draw(img)
        for y in range(self.ROAD):  # 하늘: 위는 짙은 남색, 아래는 도시 불빛에 물든 보라
            k = y / self.ROAD
            d.line((0, y, W, y), fill=_mix(_mix((8, 12, 30), (46, 34, 70), k ** 1.6), (200, 210, 240), fl * (0.75 - 0.5 * k)))
        for x, top, w, lit in self.far:  # 먼 건물
            d.rectangle((x, top, x + w, self.ROAD), fill=_mix((26, 28, 54), (90, 96, 130), fl * 0.5))
            k = 0
            for wy in range(top + 3, self.ROAD - 2, 4):
                for wx in range(x + 2, x + w - 1, 3):
                    if lit[k % len(lit)]:
                        d.point((wx, wy), fill=(120, 110, 90))
                    k += 1
        for x, top, w, lit, ph in self.near:  # 가까운 건물
            d.rectangle((x, top, x + w, self.ROAD), fill=_mix((12, 13, 24), (60, 64, 90), fl * 0.4))
            k = 0
            for wy in range(top + 3, self.ROAD - 3, 5):
                for wx in range(x + 2, x + w - 2, 4):
                    if lit[k % len(lit)]:
                        warm = 0.8 + 0.2 * math.sin(self.t * 0.5 + ph + k)
                        d.rectangle((wx, wy, wx + 1, wy + 1), fill=_mix((140, 90, 40), (255, 200, 120), warm))
                    k += 1
        for x, y in zip(self.bolt, self.bolt[1:]):  # 번개 줄기
            d.line((x[0], x[1], y[0], y[1]), fill=(235, 240, 255), width=1)
        d.rectangle((0, self.ROAD, W, self.SILL), fill=(16, 16, 24))  # 젖은 길
        lx = self.LAMP_X
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        for k, al in ((1.0, 22), (0.6, 26)):  # 가로등 빛 (가운데가 더 밝은 원뿔)
            ld.polygon([(lx - 2, 38), (lx - 2 - 15 * k, self.ROAD + 2), (lx - 2 + 15 * k, self.ROAD + 2)],
                       fill=(255, 196, 110, al))
        for x, top, w, lit, ph in self.near[::2]:  # 길에 비친 불빛 (세로로 일렁임)
            cx = x + w // 2
            for y in range(self.ROAD + 1, self.SILL):
                wob = int(math.sin(self.t * 3 + y * 0.9 + ph) * 1.5)
                ld.point((cx + wob, y), fill=(255, 190, 110, max(0, 120 - (y - self.ROAD) * 9)))
        for y in range(self.ROAD + 1, self.SILL):
            wob = int(math.sin(self.t * 4 + y) * 1.5)
            ld.line((lx - 2 + wob, y, lx + 2 + wob, y), fill=(255, 210, 140, max(0, 170 - (y - self.ROAD) * 14)))
        img.paste(layer, (0, 0), layer)
        d = ImageDraw.Draw(img)
        d.line((lx + 3, 38, lx + 3, self.ROAD), fill=(30, 30, 38))  # 가로등 기둥과 등
        d.line((lx - 2, 38, lx + 3, 38), fill=(30, 30, 38))
        d.rectangle((lx - 4, 37, lx, 39), fill=(255, 225, 160))
        for x, y, sp, ln, br in self.drops:  # 빗줄기 (가로등 빛 안에서는 반짝)
            if y >= self.SILL:
                continue
            in_cone = 38 < y < self.ROAD and abs(x - lx) < 2 + (y - 38) * 0.35
            c = _mix((70, 82, 120), (190, 205, 240), br)
            if in_cone:
                c = (255, 230, 180)
            d.line((x, y, x - ln * 0.18, y + ln), fill=c)
        px = img.load()
        for x, y, _, s in self.beads:  # 유리 물방울: 뒤 배경을 밝게 굴절 + 하이라이트 + 그늘 + 흘러내린 자국
            xi, yi = int(x), int(y)
            for k in range(2, 8):
                yy = yi - k
                if 0 <= yy < H and 0 <= xi < W:
                    r0, g0, b0 = px[xi, yy]
                    px[xi, yy] = (min(255, r0 + 10), min(255, g0 + 12), min(255, b0 + 18))
            for dx in range(-s, s + 1):
                for dy in range(-s, s + 1):
                    if dx * dx + dy * dy <= s * s + 1 and 0 <= xi + dx < W and 0 <= yi + dy < H:
                        r0, g0, b0 = px[xi + dx, yi + dy]
                        px[xi + dx, yi + dy] = (min(255, r0 + 62), min(255, g0 + 70), min(255, b0 + 90))
            if 0 <= xi - 1 < W and 0 <= yi - 1 < H:
                px[xi - 1 if s > 1 else xi, yi - 1] = (245, 248, 255)
            if 0 <= xi + 1 < W and 0 <= yi + s < H:
                px[xi + 1 if s > 1 else xi, yi + s] = (20, 24, 40)
        fog = Image.new("RGBA", (W, H), (0, 0, 0, 0))  # 아래쪽 김서림
        fd = ImageDraw.Draw(fog)
        for y in range(self.SILL - 16, self.SILL):
            fd.line((0, y, W, y), fill=(170, 185, 215, int(70 * (y - (self.SILL - 16)) / 16)))
        img.paste(fog, (0, 0), fog)
        d = ImageDraw.Draw(img)
        d.rectangle((0, self.SILL, W, H), fill=(54, 38, 28))  # 실내 창틀 (나무)
        d.line((0, self.SILL, W, self.SILL), fill=(92, 66, 44))
        for x in range(0, W, 9):
            d.line((x, self.SILL + 3, x + 5, self.SILL + 3), fill=(46, 32, 24))
        for x, left in self.splash:  # 창틀에 튀는 빗방울
            if 0 <= x < W:
                d.point((int(x) - 1, self.SILL - 1), fill=(180, 195, 230))
                d.point((int(x) + 1, self.SILL - 2), fill=(180, 195, 230))
        # 화분 (왼쪽) · 머그컵 (오른쪽) 실루엣 — 실내 조명에 살짝 따뜻하게
        d.rectangle((14, self.SILL - 7, 22, self.SILL), fill=(70, 44, 32))
        for k, (dx, dy) in enumerate(((-3, -12), (0, -15), (4, -13), (-5, -9), (6, -9))):
            d.ellipse((18 + dx - 2, self.SILL - 7 + dy, 18 + dx + 2, self.SILL - 7 + dy + 6), fill=(36, 64, 44))
        d.rectangle((118, self.SILL - 6, 124, self.SILL), fill=(196, 180, 160))
        d.arc((122, self.SILL - 5, 128, self.SILL - 1), 270, 90, fill=(196, 180, 160))
        steam = int(self.t * 3) % 3
        d.point((120 + steam % 2, self.SILL - 9 - steam), fill=(120, 120, 140))
        return img


# ---------- 노을 바닷가 ----------
class Beach(_Scene):
    hint_bg = (60, 30, 40)
    hint_fg = (255, 235, 220)
    HORIZON = 34
    SHORE = 60

    def __init__(self, seed: int | None = None) -> None:
        self.rnd = random.Random(seed)
        self.t = 0.0
        self.surge = 0.0  # 큰 파도 (누르면)
        self.birds = []  # [x, y, vx]
        self.clouds = [[self.rnd.uniform(0, W), self.rnd.uniform(4, 20), self.rnd.uniform(14, 30)] for _ in range(4)]

    def feed(self, tile: int) -> None:
        self.surge = 1.0
        self.birds.append([-6.0, self.rnd.uniform(8, 22), self.rnd.uniform(9, 14)])
        try:
            from sfx import play
            play("whoosh", 0.5, 0.8)
        except Exception:
            pass

    def step(self, dt: float) -> None:
        self.t += dt
        self.surge = max(0.0, self.surge - dt * 0.25)
        for c in self.clouds:
            c[0] = (c[0] + dt * 1.2) % (W + 30)
        if self.rnd.random() < dt * 0.05:
            self.birds.append([-6.0, self.rnd.uniform(8, 24), self.rnd.uniform(6, 11)])
        self.birds = [[x + vx * dt, y + math.sin(self.t * 2 + x) * 0.15, vx] for x, y, vx in self.birds if x < W + 8]

    def canvas(self) -> Image.Image:
        img = Image.new("RGB", (W, H))
        d = ImageDraw.Draw(img)
        hz, sh = self.HORIZON, self.SHORE
        for y in range(hz):  # 노을 하늘
            k = y / hz
            col = _mix((48, 40, 96), (236, 120, 96), k ** 1.4) if k < 0.85 else _mix((236, 120, 96), (255, 196, 120), (k - 0.85) / 0.15)
            d.line((0, y, W, y), fill=col)
        sx = W * 0.62
        d.ellipse((sx - 9, hz - 10, sx + 9, hz + 8), fill=(255, 214, 140))  # 해 (수평선에 걸침)
        for cx, cy, cw in self.clouds:
            d.rounded_rectangle((cx - cw, cy, cx, cy + 3), 2, fill=(250, 170, 150))
        for y in range(hz, sh + 6):  # 바다
            k = (y - hz) / (sh - hz)
            d.line((0, y, W, y), fill=_mix((96, 60, 110), (40, 90, 130), k))
        for k in range(14):  # 수면 위 햇빛 반짝임
            y = hz + 2 + k * 2
            wob = math.sin(self.t * 2.2 + k * 1.3) * (2 + k * 0.4)
            w = 10 - k * 0.5
            if w > 1:
                d.line((sx - w + wob, y, sx + w + wob, y), fill=(255, 210, 150))
        # 파도: 밀려왔다 빠짐 (주기 약 7초, 누르면 크게)
        phase = (self.t / 7.0) % 1.0
        reach = math.sin(phase * math.pi) ** 1.5 * (8 + 10 * self.surge)
        edge = sh + reach
        d.rectangle((0, sh + 6, W, H), fill=(226, 196, 150))  # 모래
        for x in range(0, W, 3):
            if (x * 7) % 5 == 0:
                d.point((x, sh + 12 + (x * 3) % 14), fill=(206, 176, 132))
        pts = [(x, edge + math.sin(x * 0.18 + self.t * 1.5) * 1.6) for x in range(0, W + 2, 2)]
        d.polygon([(0, sh)] + pts + [(W, sh)], fill=(70, 120, 150))  # 젖은 물
        d.line(pts, fill=(245, 245, 240), width=2)  # 하얀 거품
        for x, y in pts[::5]:
            if (x + int(self.t * 3)) % 4 == 0:
                d.point((x, y + 2), fill=(230, 235, 235))
        d.line([(x, y + 3) for x, y in pts], fill=(196, 170, 130))  # 젖은 모래 자국
        for k in range(3):  # 먼바다 물결 줄
            y = hz + 6 + k * 7 + int(math.sin(self.t + k) * 1.5)
            for x in range(-10, W, 18):
                xx = x + (self.t * (4 + k * 3)) % 18
                d.line((xx, y, xx + 6, y), fill=(150, 130, 170) if k == 0 else (110, 150, 180))
        for x, y, _ in self.birds:  # 갈매기
            flap = 1 if int(self.t * 6 + x) % 2 else -1
            d.line((x - 3, y + flap, x, y), fill=(40, 30, 50))
            d.line((x, y, x + 3, y + flap), fill=(40, 30, 50))
        return img
