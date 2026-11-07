"""게임 페이지: 두더지 잡기 · 순서 기억.

판은 위 두 줄 10칸(0~9). 아래 줄은 페이지 넘김 버튼 그대로, 넓은 칸은 점수판.
입력은 누르는 순간(press)에 처리해 반응을 빠르게 한다. 화면은 상태가 바뀔 때만 다시 보낸다.
"""

from __future__ import annotations

import io
import json
import math
import random
import threading
import time
from functools import lru_cache
from pathlib import Path

from PIL import Image

from clock import _Draw, _kr

BOARD = 10
SIZE = 196
WIDE = (458, 196)
SAVE = Path.home() / ".cache" / "d200" / "games.json"

MOLE_KEYS = (0, 1, 5, 6)  # 메뉴에서 두더지 잡기를 시작하는 칸 (왼쪽 네 칸)
SIMON_KEYS = (3, 4, 8, 9)  # 순서 기억 (오른쪽 네 칸)
MOLE_SEC = 30  # 두더지 한 판 길이
SIMON_COLORS = ["#f7768e", "#ff9e64", "#e0af68", "#9ece6a", "#73daca",
                "#7dcfff", "#7aa2f7", "#bb9af7", "#c0caf5", "#f4b8e4"]


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG", compress_level=3)
    return buf.getvalue()


def _rgb(hex_: str, k: float = 1.0) -> tuple[int, int, int]:
    h = hex_.lstrip("#")
    return tuple(min(255, int(int(h[i:i + 2], 16) * k)) for i in (0, 2, 4))  # type: ignore[return-value]


# ---------- 칸 그림 (상태별로 캐시) ----------
@lru_cache(maxsize=64)
def mole_tile(state: str) -> bytes:
    """state: empty | mole | gold | bomb | hit | boom | miss"""
    img = Image.new("RGB", (SIZE, SIZE), (58, 92, 52))
    d = _Draw(img)
    for i in range(14):  # 잔디 점
        x, y = (i * 53) % SIZE, (i * 97) % 70 + 6
        d.line((x, y, x + 3, y - 7), fill=(84, 130, 70), width=3)
    d.ellipse((30, 128, 166, 176), fill=(70, 46, 30))  # 구멍
    if state in ("mole", "gold", "hit"):
        body = (232, 190, 70) if state == "gold" else (140, 98, 66)
        d.rounded_rectangle((52, 58, 144, 160), 40, fill=body)
        d.ellipse((30, 140, 166, 182), fill=(58, 92, 52))  # 구멍 앞 흙 둔덕
        d.ellipse((30, 146, 166, 188), fill=(96, 66, 42))
        if state == "hit":  # X 눈 + 별
            for cx in (80, 116):
                d.line((cx - 8, 86, cx + 8, 102), fill=(30, 20, 20), width=5)
                d.line((cx - 8, 102, cx + 8, 86), fill=(30, 20, 20), width=5)
            for sx, sy in ((40, 40), (150, 34), (98, 22)):
                d.regular_polygon((sx, sy, 13), 5, fill=(255, 225, 90))
        else:
            for cx in (80, 116):
                d.ellipse((cx - 8, 84, cx + 8, 100), fill=(20, 16, 16))
                d.ellipse((cx - 3, 87, cx + 2, 92), fill=(255, 255, 255))
        d.ellipse((88, 104, 108, 120), fill=(240, 130, 150))  # 코
        d.ellipse((60, 124, 84, 140), fill=(236, 226, 210))  # 앞발
        d.ellipse((112, 124, 136, 140), fill=(236, 226, 210))
        if state == "gold":
            d.text((98, 40), "+3", font=_kr(26, 6), fill=(255, 245, 190), anchor="mm")
    elif state in ("bomb", "boom"):
        if state == "boom":
            d.regular_polygon((98, 110, 78), 12, fill=(255, 150, 60))
            d.regular_polygon((98, 110, 50), 12, fill=(255, 230, 120))
            d.text((98, 110), "-3", font=_kr(40, 6), fill=(120, 30, 20), anchor="mm")
        else:
            d.ellipse((56, 70, 140, 154), fill=(30, 30, 38))
            d.ellipse((72, 84, 90, 102), fill=(90, 90, 110))
            d.line((118, 76, 134, 50), fill=(200, 170, 120), width=5)
            d.regular_polygon((136, 46, 12), 6, fill=(255, 190, 70))
    elif state == "miss":
        d.text((98, 80), "헛방", font=_kr(30, 6), fill=(220, 235, 210), anchor="mm")
    return _png(img)


@lru_cache(maxsize=64)
def simon_tile(idx: int, lit: bool, mark: str = "") -> bytes:
    color = SIMON_COLORS[idx]
    img = Image.new("RGB", (SIZE, SIZE), (13, 14, 20))
    d = _Draw(img)
    fill = _rgb(color) if lit else _rgb(color, 0.22)
    d.rounded_rectangle((14, 14, 182, 182), 30, fill=fill)
    if lit:
        d.rounded_rectangle((14, 14, 182, 182), 30, outline=(255, 255, 255), width=6)
    if mark == "✕":  # 틀린 칸: 굵은 X (글꼴에 ✕ 가 없어 직접 그림)
        d.line((60, 60, 136, 136), fill=(255, 90, 100), width=14)
        d.line((60, 136, 136, 60), fill=(255, 90, 100), width=14)
    elif mark:
        d.text((98, 98), mark, font=_kr(64, 6), fill=(255, 255, 255), anchor="mm")
    return _png(img)


@lru_cache(maxsize=16)
def menu_tile(kind: str, best: int) -> bytes:
    img = Image.new("RGB", (SIZE, SIZE), (24, 26, 38))
    d = _Draw(img)
    if kind == "mole":
        d.ellipse((48, 120, 148, 150), fill=(70, 46, 30))
        d.rounded_rectangle((66, 48, 130, 136), 30, fill=(140, 98, 66))
        for cx in (86, 110):
            d.ellipse((cx - 6, 70, cx + 6, 82), fill=(20, 16, 16))
        d.ellipse((90, 88, 106, 100), fill=(240, 130, 150))
        d.text((98, 22), "두더지 잡기", font=_kr(24, 6), fill=(230, 233, 245), anchor="mm")
    else:
        for i, c in enumerate(SIMON_COLORS[:4]):
            x, y = 54 + (i % 2) * 46, 52 + (i // 2) * 46
            d.rounded_rectangle((x, y, x + 40, y + 40), 10, fill=_rgb(c))
        d.text((98, 22), "순서 기억", font=_kr(24, 6), fill=(230, 233, 245), anchor="mm")
    d.text((98, 172), f"최고 {best}", font=_kr(20, 4), fill=(169, 177, 214), anchor="mm")
    return _png(img)


@lru_cache(maxsize=4)
def blank_tile() -> bytes:
    return _png(Image.new("RGB", (SIZE, SIZE), (13, 14, 20)))


def wide_panel(title: str, big: str, lines: list[str], color: str, bar: float | None = None) -> bytes:
    img = Image.new("RGB", WIDE, "#0d0e14")
    d = _Draw(img)
    d.text((24, 34), title, font=_kr(26, 6), fill=color, anchor="lm")
    d.text((434, 96), big, font=_kr(64, 6), fill="#e6e9f5", anchor="rm")
    for i, line in enumerate(lines[:3]):
        d.text((24, 82 + i * 30), line, font=_kr(21, 2), fill="#c0caf5", anchor="lm")
    if bar is not None:  # 남은 시간 막대
        d.rounded_rectangle((24, 170, 434, 180), 5, fill="#1f2335")
        w = int(410 * max(0.0, min(1.0, bar)))
        if w > 6:
            d.rounded_rectangle((24, 170, 24 + w, 180), 5, fill=color)
    return _png(img)


# ---------- 게임 상태 ----------
class Games:
    """mode: menu | mole | simon. phase: play | show | input | over"""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.rnd = random.Random()
        self.mode = "menu"
        self.phase = ""
        self.best = self._load()
        self.score = 0
        self.new_best = False
        # 두더지
        self.end_at = 0.0
        self.holes: dict[int, tuple[str, float]] = {}  # 칸 -> (상태, 사라지는 시각)
        self.next_pop = 0.0
        # 순서 기억
        self.seq: list[int] = []
        self.pos = 0
        self.show_at = 0.0
        self.lit: int | None = None
        self.lit_until = 0.0
        self.over_at = 0.0

    @property
    def active(self) -> bool:
        return self.mode != "menu" and self.phase != "over"

    # ---- 저장 ----
    def _load(self) -> dict:
        try:
            return {"mole": 0, "simon": 0, **json.loads(SAVE.read_text())}
        except Exception:
            return {"mole": 0, "simon": 0}

    def _finish(self) -> None:
        self.phase, self.over_at = "over", time.time()
        self.holes.clear()
        self.new_best = self.score > self.best.get(self.mode, 0)
        if self.new_best:
            self.best[self.mode] = self.score
            try:
                SAVE.parent.mkdir(parents=True, exist_ok=True)
                SAVE.write_text(json.dumps(self.best))
            except Exception:
                pass

    # ---- 입력 ----
    def menu(self) -> None:
        with self.lock:
            self.mode, self.phase, self.holes, self.lit = "menu", "", {}, None

    def press(self, idx: int) -> None:
        """판(0~9) 또는 넓은 칸(13 이상)을 누른 순간."""
        with self.lock:
            now = time.time()
            if self.mode == "menu":
                if idx in MOLE_KEYS:
                    self.start("mole")
                elif idx in SIMON_KEYS:
                    self.start("simon")
                return
            if self.phase == "over":
                if now - self.over_at > 0.8:  # 끝난 직후 실수로 누른 건 무시
                    self.start(self.mode) if idx < BOARD else self.menu()
                return
            if idx >= BOARD:
                return
            if self.mode == "mole":
                kind = self.holes.get(idx, ("empty", 0))[0]
                if kind == "mole":
                    self.score += 1
                    self.holes[idx] = ("hit", now + 0.35)
                elif kind == "gold":
                    self.score += 3
                    self.holes[idx] = ("hit", now + 0.35)
                elif kind == "bomb":
                    self.score = max(0, self.score - 3)
                    self.holes[idx] = ("boom", now + 0.5)
                elif kind == "empty":
                    self.holes[idx] = ("miss", now + 0.25)
            elif self.mode == "simon" and self.phase == "input":
                self.lit, self.lit_until = idx, now + 0.25
                if idx == self.seq[self.pos]:
                    self.pos += 1
                    if self.pos == len(self.seq):  # 한 판 통과
                        self.score = len(self.seq)
                        self._next_round(now + 0.9)
                else:
                    self.lit = None
                    self.wrong = idx
                    self._finish()

    def start(self, mode: str) -> None:
        with self.lock:
            now = time.time()
            self.mode, self.score, self.new_best = mode, 0, False
            self.holes, self.lit = {}, None
            self.wrong = None
            if mode == "mole":
                self.phase, self.end_at, self.next_pop = "play", now + MOLE_SEC, now + 0.6
            else:
                self.seq = []
                self._next_round(now + 0.8)

    def _next_round(self, at: float) -> None:
        self.seq.append(self.rnd.randrange(BOARD))
        self.phase, self.pos, self.show_at, self.lit = "show", 0, at, None

    # ---- 시간 진행 (게임 루프에서 호출) ----
    def tick(self) -> None:
        with self.lock:
            now = time.time()
            if self.mode == "mole" and self.phase == "play":
                for i, (k, until) in list(self.holes.items()):
                    if now >= until:
                        del self.holes[i]
                if now >= self.end_at:
                    self._finish()
                    return
                prog = 1 - (self.end_at - now) / MOLE_SEC  # 0 → 1 로 갈수록 빨라짐
                if now >= self.next_pop:
                    free = [i for i in range(BOARD) if i not in self.holes]
                    for _ in range(1 if prog < 0.4 or self.rnd.random() < 0.5 else 2):
                        if not free:
                            break
                        i = free.pop(self.rnd.randrange(len(free)))
                        r = self.rnd.random()
                        kind = "gold" if r < 0.08 else ("bomb" if r < 0.2 and prog > 0.15 else "mole")
                        stay = (1.3 - 0.65 * prog) * (0.75 if kind == "gold" else 1.0)
                        self.holes[i] = (kind, now + stay)
                    self.next_pop = now + self.rnd.uniform(0.45, 0.9) * (1 - 0.45 * prog)
            elif self.mode == "simon":
                if self.phase == "show" and now >= self.show_at:
                    # 순서 보여주기: 칸마다 켜짐(on) → 꺼짐(gap)
                    on = max(0.32, 0.6 - 0.02 * len(self.seq))
                    step = on + 0.22
                    k = int((now - self.show_at) / step)
                    if k >= len(self.seq):
                        self.phase, self.lit = "input", None
                    else:
                        self.lit = self.seq[k] if (now - self.show_at) - k * step < on else None
                elif self.phase == "input" and self.lit is not None and now >= self.lit_until:
                    self.lit = None

    # ---- 그리기 ----
    def tiles(self) -> dict[int, bytes]:
        with self.lock:
            if self.mode == "menu":
                out = {i: blank_tile() for i in range(BOARD)}
                out.update({0: menu_tile("mole", self.best.get("mole", 0)), 1: mole_tile("mole"),
                            5: mole_tile("gold"), 6: mole_tile("empty")})
                out.update({3: menu_tile("simon", self.best.get("simon", 0)), 4: simon_tile(4, True),
                            8: simon_tile(8, False), 9: simon_tile(9, True)})
                return out
            if self.mode == "mole":
                return {i: mole_tile(self.holes.get(i, ("empty", 0))[0]) for i in range(BOARD)}
            wrong = getattr(self, "wrong", None)
            out = {}
            for i in range(BOARD):
                if self.phase == "over":
                    answer = self.seq[self.pos] if self.pos < len(self.seq) else None
                    out[i] = simon_tile(i, i == answer, "✕" if i == wrong else ("!" if i == answer else ""))
                else:
                    out[i] = simon_tile(i, i == self.lit)
            return out

    def wide(self) -> bytes:
        with self.lock:
            best = self.best.get(self.mode, 0)
            if self.mode == "menu":
                return wide_panel("게임", "", ["왼쪽: 두더지 잡기 (30초)", "오른쪽: 순서 기억",
                                              f"최고 기록  두더지 {self.best.get('mole', 0)} · 순서 {self.best.get('simon', 0)}"],
                                  "#9ece6a")
            if self.phase == "over":
                head = "새 기록!" if self.new_best else "게임 끝"
                return wide_panel(head, str(self.score), [f"최고 {max(best, self.score)}", "판 누르기: 다시 하기",
                                                          "가운데: 메뉴"], "#e0af68" if self.new_best else "#f7768e")
            if self.mode == "mole":
                left = max(0.0, self.end_at - time.time())
                return wide_panel("두더지 잡기", str(self.score), [f"남은 시간 {math.ceil(left)}초", f"최고 {best}",
                                                                 "황금 +3 · 폭탄 -3"], "#9ece6a", left / MOLE_SEC)
            msg = "잘 보세요" if self.phase == "show" else f"따라 누르기 {self.pos}/{len(self.seq)}"
            return wide_panel("순서 기억", str(len(self.seq)), [msg, f"최고 {best}"], "#7aa2f7")

    def wide_key(self) -> tuple:
        """넓은 칸이 바뀌었는지 비교할 값 (불필요한 전송 줄이기)."""
        with self.lock:
            sec = math.ceil(self.end_at - time.time()) if self.mode == "mole" and self.phase == "play" else 0
            return self.mode, self.phase, self.score, self.pos, len(self.seq), sec, self.new_best
