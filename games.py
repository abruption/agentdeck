"""게임 페이지: 두더지 잡기 · 순서 기억 · 짝 맞추기 · 슬롯머신 · 블랙잭 · 포커 대결.

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

from PIL import Image, ImageDraw, ImageFont

from clock import _Draw, _kr

BOARD = 10
SIZE = 196
WIDE = (458, 196)
SAVE = Path.home() / ".cache" / "d200" / "games.json"

GAMES = ["mole", "simon", "pairs", "slot", "bj", "poker"]  # 메뉴 칸 순서 (0번 칸부터)
LOWER_IS_BETTER = {"pairs"}  # 짝 맞추기는 시도 횟수가 적을수록 좋은 기록
EMOJI_FONT = "/System/Library/Fonts/Apple Color Emoji.ttc"
PAIR_CARDS = ["🐟", "🐙", "🦀", "🐢", "🦈"]  # 어항 친구들 5쌍
SLOT_SYMBOLS = ["🍒", "🍋", "🔔", "⭐", "💎", "7"]
SLOT_PAY = {"7": 50, "💎": 30, "⭐": 15, "🔔": 10, "🍋": 6, "🍒": 5}  # 세 개가 같을 때
SLOT_REELS = (1, 2, 3)  # 릴이 보이는 칸 (윗줄 가운데)
SLOT_STOPS = (6, 7, 8)  # 각 릴을 멈추는 버튼 (바로 아래 칸)
SLOT_LEVERS = (0, 4, 5, 9)  # 돌리기 (양쪽 끝 칸)
SLOT_START = 20  # 슬롯·블랙잭이 같이 쓰는 코인
BJ_HIT, BJ_STAND = 4, 9  # 블랙잭: 윗줄 끝 = 한 장 더, 아랫줄 끝 = 그만 (베팅 중엔 딜 / 베팅액)
BJ_BETS = [1, 2, 5, 10]
SUITS = "♠♥♦♣"
POKER_NAMES = ["하이카드", "원페어", "투페어", "트리플", "스트레이트", "플러시", "풀하우스", "포카드",
               "스트레이트 플러시", "로열 플러시"]
POKER_BONUS = {4: 4, 5: 6, 6: 9, 7: 25, 8: 50, 9: 250}  # 이겼을 때 스트레이트 이상이면 배당이 커진다 (그 밖엔 1배)
POKER_OPEN = (0, 1)  # 상대 카드 중 처음부터 보이는 칸
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
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


@lru_cache(maxsize=32)
def menu_tile(kind: str, best: str) -> bytes:
    img = Image.new("RGB", (SIZE, SIZE), (24, 26, 38))
    d = _Draw(img)
    title = {"mole": "두더지 잡기", "simon": "순서 기억", "pairs": "짝 맞추기", "slot": "슬롯머신", "bj": "블랙잭",
             "poker": "포커 대결"}[kind]
    if kind == "mole":
        d.ellipse((48, 120, 148, 150), fill=(70, 46, 30))
        d.rounded_rectangle((66, 48, 130, 136), 30, fill=(140, 98, 66))
        for cx in (86, 110):
            d.ellipse((cx - 6, 70, cx + 6, 82), fill=(20, 16, 16))
        d.ellipse((90, 88, 106, 100), fill=(240, 130, 150))
    elif kind == "simon":
        for i, c in enumerate(SIMON_COLORS[:4]):
            x, y = 54 + (i % 2) * 46, 52 + (i // 2) * 46
            d.rounded_rectangle((x, y, x + 40, y + 40), 10, fill=_rgb(c))
    elif kind == "pairs":
        for k, (x, face) in enumerate(((44, "🐙"), (102, "🐙"))):
            d.rounded_rectangle((x, 50, x + 50, 140), 10, fill=(236, 238, 248) if k else (60, 72, 130))
            if k:
                _paste_center(img, _emoji(face, 40), x + 25, 95)
            else:
                d.text((x + 25, 95), "?", font=_kr(34, 6), fill=(170, 182, 235), anchor="mm")
    elif kind == "poker":
        for k, c in enumerate((("10", "♠"), ("J", "♠"), ("Q", "♠"))):
            img.paste(Image.open(io.BytesIO(play_card(c, "", 0.46))), (34 + k * 44, 50))
    elif kind == "bj":
        img.paste(Image.open(io.BytesIO(play_card(("A", "♠"), "", 0.55))), (36, 46))
        img.paste(Image.open(io.BytesIO(play_card(("K", "♥"), "", 0.55))), (64, 54))
    else:
        for k in range(3):
            x = 40 + k * 40
            d.rounded_rectangle((x, 60, x + 36, 130), 8, fill=(250, 246, 236))
            _seven(d, x + 18, 95, 44)
    d.text((98, 22), title, font=_kr(24, 6), fill=(230, 233, 245), anchor="mm")
    d.text((98, 172), best, font=_kr(20, 4), fill=(169, 177, 214), anchor="mm")
    return _png(img)


@lru_cache(maxsize=32)
def _emoji(ch: str, size: int) -> Image.Image:
    """애플 컬러 이모지를 160px 로 그린 뒤 size 로 줄인다 (글꼴이 160 크기만 지원)."""
    img = Image.new("RGBA", (220, 220), (0, 0, 0, 0))
    try:
        ImageDraw.Draw(img).text((110, 110), ch, font=ImageFont.truetype(EMOJI_FONT, 160), embedded_color=True,
                                 anchor="mm")
        img = img.crop(img.getbbox())
    except Exception:  # 이모지 글꼴이 없으면 글자로
        img = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
        ImageDraw.Draw(img).text((80, 80), ch, font=_kr(110, 6), fill=(240, 240, 240), anchor="mm")
    img.thumbnail((size, size), Image.LANCZOS)
    return img


def _paste_center(base: Image.Image, icon: Image.Image, cx: int, cy: int) -> None:
    base.paste(icon, (cx - icon.width // 2, cy - icon.height // 2), icon)


def _seven(d, cx: int, cy: int, size: int) -> None:
    d.text((cx, cy), "7", font=_kr(size, 6), fill=(235, 60, 70), anchor="mm", stroke_width=max(2, size // 16),
           stroke_fill=(255, 220, 120))


@lru_cache(maxsize=64)
def card_tile(face: str | None, state: str = "down") -> bytes:
    """짝 맞추기 카드. state: down(뒷면) | up(뒤집음) | done(맞춤) | wrong(틀린 한 쌍)"""
    img = Image.new("RGB", (SIZE, SIZE), (13, 14, 20))
    d = _Draw(img)
    if state == "down":
        d.rounded_rectangle((16, 10, 180, 186), 22, fill=(60, 72, 130))
        d.rounded_rectangle((28, 22, 168, 174), 16, outline=(120, 135, 200), width=4)
        d.text((98, 98), "?", font=_kr(70, 6), fill=(170, 182, 235), anchor="mm")
        return _png(img)
    bg = {"up": (236, 238, 248), "done": (205, 240, 210), "wrong": (250, 210, 215)}[state]
    d.rounded_rectangle((16, 10, 180, 186), 22, fill=bg)
    if state == "done":
        d.rounded_rectangle((16, 10, 180, 186), 22, outline=(90, 190, 110), width=6)
    _paste_center(img, _emoji(face or "?", 110), 98, 98)
    return _png(img)


@lru_cache(maxsize=96)
def reel_tile(sym: str, glow: bool = False, spinning: bool = False) -> bytes:
    img = Image.new("RGB", (SIZE, SIZE), (40, 18, 30) if not glow else (120, 70, 20))
    d = _Draw(img)
    d.rounded_rectangle((12, 12, 184, 184), 20, fill=(250, 246, 236), outline=(255, 205, 90) if glow else (150, 110, 70),
                        width=8 if glow else 5)
    if spinning:  # 돌아가는 느낌: 위아래 잔상 줄
        for y in (34, 162):
            d.line((40, y, 156, y), fill=(210, 200, 185), width=6)
    if sym == "7":
        _seven(d, 98, 98, 120)
    else:
        _paste_center(img, _emoji(sym, 112), 98, 98)
    return _png(img)


@lru_cache(maxsize=16)
def slot_button(kind: str, active: bool = True) -> bytes:
    """kind: stop | stopped | lever | wait"""
    img = Image.new("RGB", (SIZE, SIZE), (13, 14, 20))
    d = _Draw(img)
    if kind in ("stop", "stopped"):
        col = (230, 70, 80) if kind == "stop" else (70, 60, 70)
        d.ellipse((38, 38, 158, 158), fill=col, outline=(255, 255, 255) if kind == "stop" else (100, 90, 100), width=6)
        d.text((98, 98), "STOP", font=_kr(30, 6), fill=(255, 255, 255) if kind == "stop" else (150, 140, 150),
               anchor="mm")
    else:
        on = kind == "lever"
        d.rounded_rectangle((86, 50, 110, 160), 10, fill=(170, 170, 185) if on else (70, 70, 80))
        d.ellipse((66, 18, 130, 82), fill=(235, 60, 70) if on else (90, 60, 65))
        d.text((98, 178), "돌리기", font=_kr(22, 6), fill=(230, 233, 245) if on else (100, 100, 115), anchor="mm")
    return _png(img)


@lru_cache(maxsize=256)
def play_card(card: tuple[str, str] | None, glow: str = "", scale: float = 1.0) -> bytes:
    """트럼프 한 장. card=None 이면 뒷면. glow: win | lose | ''"""
    w, h = int(118 * scale), int(166 * scale)
    img = Image.new("RGB", (w, h), (13, 14, 20)) if scale != 1.0 else Image.new("RGB", (SIZE, SIZE), (22, 70, 48))
    d = _Draw(img)
    x0, y0 = (0, 0) if scale != 1.0 else ((SIZE - w) // 2, (SIZE - h) // 2)
    box = (x0, y0, x0 + w - 1, y0 + h - 1)
    if card is None:  # 뒷면: 사선 무늬를 카드 모양 안에만
        back = Image.new("RGB", (w, h), (50, 70, 150))
        bd = ImageDraw.Draw(back)
        for k in range(-h, w, max(4, int(16 * scale))):
            bd.line((k, 0, k + h, h), fill=(75, 95, 175), width=max(1, int(3 * scale)))
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), int(14 * scale), fill=255)
        img.paste(back, (x0, y0), mask)
        d.rounded_rectangle(box, int(14 * scale), outline=(235, 235, 245), width=max(2, int(5 * scale)))
        return _png(img)
    rank, suit = card
    red = suit in "♥♦"
    col = (210, 40, 50) if red else (25, 25, 35)
    edge = {"win": (90, 200, 110), "lose": (230, 80, 90), "hold": (250, 200, 60)}.get(glow, (200, 200, 210))
    d.rounded_rectangle(box, int(14 * scale), fill=(252, 252, 248), outline=edge, width=max(2, int((7 if glow else 3) * scale)))
    d.text((x0 + int(12 * scale), y0 + int(8 * scale)), rank, font=_kr(int(40 * scale), 6), fill=col, anchor="lt")
    d.text((x0 + w // 2, y0 + int(h * 0.62)), suit, font=_kr(int(78 * scale), 6), fill=col, anchor="mm")
    return _png(img)


@lru_cache(maxsize=128)
def hand_tile(cards: tuple, glow: str = "") -> bytes:
    """카드 0~2장을 한 칸에. 두 장이면 겹쳐서 작게."""
    if len(cards) <= 1:
        if not cards:
            return _png(Image.new("RGB", (SIZE, SIZE), (22, 70, 48)))
        return play_card(cards[0], glow)
    img = Image.new("RGB", (SIZE, SIZE), (22, 70, 48))
    for k, c in enumerate(cards[:2]):
        im = Image.open(io.BytesIO(play_card(c, glow, 0.78)))
        img.paste(im, (14 + k * 72, 22 + k * 16))
    return _png(img)


@lru_cache(maxsize=32)
def bj_button(label: str, sub: str, color: str, enabled: bool = True) -> bytes:
    img = Image.new("RGB", (SIZE, SIZE), (13, 14, 20))
    d = _Draw(img)
    fill = _rgb(color) if enabled else (55, 58, 70)
    d.rounded_rectangle((14, 14, 182, 182), 26, fill=fill)
    tc = (20, 20, 28) if enabled else (120, 122, 135)
    d.text((98, 88), label, font=_kr(40 if len(label) <= 3 else 32, 6), fill=tc, anchor="mm")
    if sub:
        d.text((98, 140), sub, font=_kr(22, 4), fill=tc, anchor="mm")
    return _png(img)


def _layout(cards: list, slots: int = 4) -> list[tuple]:
    """카드 목록을 칸 slots 개에 나눈다. 넘치면 뒤쪽 칸부터 두 장씩."""
    sizes = [1] * min(len(cards), slots) + [0] * max(0, slots - len(cards))
    extra = len(cards) - slots
    k = slots - 1
    while extra > 0 and k >= 0:
        sizes[k] += 1
        extra -= 1
        k -= 1
    out, i = [], 0
    for n in sizes:
        out.append(tuple(cards[i:i + n]))
        i += n
    return out


def poker_rank(cards: list) -> tuple[int, tuple]:
    """5장 족보 → (족보 번호 0~9, 같은 족보끼리 비교할 숫자들). 번호는 POKER_NAMES 순서."""
    order = {r: i + 2 for i, r in enumerate(["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"])}
    vals = [order[r] for r, _ in cards]
    groups = sorted(((vals.count(v), v) for v in set(vals)), reverse=True)  # (장수, 숫자) 많은 순
    tie = tuple(v for _, v in groups)
    flush = len({s for _, s in cards}) == 1
    uniq = sorted(set(vals))
    straight = len(uniq) == 5 and uniq[-1] - uniq[0] == 4
    if uniq == [2, 3, 4, 5, 14]:  # A-2-3-4-5
        straight, tie = True, (5,)
    elif straight:
        tie = (uniq[-1],)
    if straight and flush:
        return (9 if tie == (14,) else 8), tie
    if groups[0][0] == 4:
        return 7, tie
    if groups[0][0] == 3 and groups[1][0] == 2:
        return 6, tie
    if flush:
        return 5, tuple(sorted(vals, reverse=True))
    if straight:
        return 4, tie
    if groups[0][0] == 3:
        return 3, tie
    if groups[0][0] == 2 and groups[1][0] == 2:
        return 2, tie
    if groups[0][0] == 2:
        return 1, tie
    return 0, tuple(sorted(vals, reverse=True))


def poker_ai_holds(cards: list) -> list[bool]:
    """상대(컴퓨터)가 남길 카드: 족보가 있으면 그대로, 같은 무늬 4장이면 그 4장, 아니면 Q 이상 한 장."""
    cat, _ = poker_rank(cards)
    if cat >= 4:
        return [True] * 5
    ranks = [r for r, _ in cards]
    if cat >= 1:
        return [ranks.count(r) >= 2 for r in ranks]
    suits = [s for _, s in cards]
    for s in set(suits):
        if suits.count(s) == 4:
            return [x == s for x in suits]
    best = max(range(5), key=lambda i: RANKS.index(ranks[i]) if ranks[i] != "A" else 99)
    return [i == best and ranks[i] in ("Q", "K", "A") for i in range(5)]


@lru_cache(maxsize=128)
def held_card(card: tuple[str, str]) -> bytes:
    """킵한 카드: 노란 테두리 + 아래 띠."""
    img = Image.open(io.BytesIO(play_card(card, "hold")))
    d = _Draw(img)
    d.rounded_rectangle((52, 160, 144, 190), 10, fill=(250, 200, 60))
    d.text((98, 175), "킵", font=_kr(22, 6), fill=(30, 25, 10), anchor="mm")
    return _png(img)


def hand_value(cards: list) -> tuple[int, bool]:
    """(합계, 소프트 여부). A 는 1 또는 11."""
    total = sum(10 if r in "JQK" or r == "10" else (1 if r == "A" else int(r)) for r, _ in cards)
    soft = any(r == "A" for r, _ in cards) and total + 10 <= 21
    return (total + 10 if soft else total), soft


@lru_cache(maxsize=4)
def blank_tile() -> bytes:
    return _png(Image.new("RGB", (SIZE, SIZE), (13, 14, 20)))


def wide_panel(title: str, big: str, lines: list[str], color: str, bar: float | None = None) -> bytes:
    img = Image.new("RGB", WIDE, "#0d0e14")
    d = _Draw(img)
    d.text((24, 34), title, font=_kr(26, 6), fill=color, anchor="lm")
    d.text((434, 96), big, font=_kr(64, 6), fill="#e6e9f5", anchor="rm")
    from i18n import tr

    room = 434 - 24 - 16 - (d.textlength(tr(big) or "", font=_kr(64, 6)) if big else 0)  # 큰 숫자와 겹치지 않게
    for i, line in enumerate(lines[:3]):
        size = 21
        while size > 14 and d.textlength(tr(line) or "", font=_kr(size, 2)) > (room if 66 <= 82 + i * 30 <= 126 else 410):
            size -= 1
        d.text((24, 82 + i * 30), line, font=_kr(size, 2), fill="#c0caf5", anchor="lm")
    if bar is not None:  # 남은 시간 막대
        d.rounded_rectangle((24, 170, 434, 180), 5, fill="#1f2335")
        w = int(410 * max(0.0, min(1.0, bar)))
        if w > 6:
            d.rounded_rectangle((24, 170, 24 + w, 180), 5, fill=color)
    return _png(img)


# ---------- 게임 상태 ----------
class Games:
    """mode: menu | mole | simon | pairs | slot. phase: play | show | input | over"""

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
        self.wrong: int | None = None
        # 짝 맞추기
        self.cards: list[str] = []
        self.matched: set[int] = set()
        self.open: list[int] = []  # 지금 뒤집혀 있는 (아직 안 맞춘) 카드
        self.flip_back = 0.0  # 틀린 한 쌍을 다시 덮는 시각
        self.peek_until = 0.0  # 시작할 때 잠깐 전부 보여주기
        self.started = 0.0
        # 슬롯머신
        self.coins = int(self.best.get("slot_coins", SLOT_START)) or SLOT_START
        self.reels = [self.rnd.choice(SLOT_SYMBOLS) for _ in SLOT_REELS]
        self.spinning = [False, False, False]
        self.spin_next = 0.0
        self.spin_auto = 0.0  # 이 시각이 지나면 남은 릴 자동 정지
        self.win = 0
        self.win_until = 0.0
        # 블랙잭
        self.bet = 2
        self.bet_now = 0  # 이번 판에 실제로 건 코인 (더블이면 두 배)
        self.shoe: list[tuple[str, str]] = []
        self.dealer: list[tuple[str, str]] = []
        self.player: list[tuple[str, str]] = []
        self.hole = True  # 딜러 두 번째 카드를 가렸는지
        self.result = ""  # win | lose | push | bj
        self.next_draw = 0.0
        # 비디오 포커
        self.hand: list[tuple[str, str]] = []
        self.opp: list[tuple[str, str]] = []  # 상대(컴퓨터) 패
        self.opp_swapped = 0
        self.held = [False] * 5
        self.poker_cmp = 0  # 1 이김, 0 비김, -1 짐

    @property
    def active(self) -> bool:
        """시간이 흐르는 중인지 (게임 루프·화면보호기 판단용). 슬롯은 돌거나 당첨 연출 중일 때만."""
        if self.mode == "slot":
            return any(self.spinning) or time.time() < self.win_until
        if self.mode == "bj":
            return self.phase == "dealer" or time.time() < self.win_until
        if self.mode == "poker":
            return self.phase == "opp" or time.time() < self.win_until
        return self.mode != "menu" and self.phase != "over"

    # ---- 저장 ----
    def _load(self) -> dict:
        try:
            return {"mole": 0, "simon": 0, "pairs": 0, "slot": 0, **json.loads(SAVE.read_text())}
        except Exception:
            return {"mole": 0, "simon": 0, "pairs": 0, "slot": 0}

    def _save(self) -> None:
        try:
            SAVE.parent.mkdir(parents=True, exist_ok=True)
            SAVE.write_text(json.dumps(self.best))
        except Exception:
            pass

    def best_text(self, mode: str) -> str:
        v = self.best.get(mode, 0)
        if mode == "pairs":
            return f"최고 {v}번" if v else "기록 없음"
        if mode in ("slot", "bj", "poker"):
            return f"코인 {self.coins}"
        return f"최고 {v}"

    def _finish(self) -> None:
        self.phase, self.over_at = "over", time.time()
        self.holes.clear()
        if self.mode == "slot":  # 슬롯은 코인 기록을 따로 저장
            self.new_best = False
            return
        old = self.best.get(self.mode, 0)
        if self.mode in LOWER_IS_BETTER:
            self.new_best = self.score > 0 and (old == 0 or self.score < old)
        else:
            self.new_best = self.score > old
        if self.new_best:
            self.best[self.mode] = self.score
            self._save()

    # ---- 입력 ----
    def menu(self) -> None:
        with self.lock:
            self.mode, self.phase, self.holes, self.lit = "menu", "", {}, None

    def press(self, idx: int) -> None:
        """판(0~9) 또는 넓은 칸(13 이상)을 누른 순간."""
        with self.lock:
            now = time.time()
            if self.mode == "menu":
                if idx < len(GAMES):
                    self.start(GAMES[idx])
                return
            if self.phase == "over":
                if now - self.over_at > 0.8:  # 끝난 직후 실수로 누른 건 무시
                    self.start(self.mode) if idx < BOARD else self.menu()
                return
            if self.mode == "bj":
                self._press_bj(idx, now)
                return
            if self.mode == "poker":
                self._press_poker(idx, now)
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
            elif self.mode == "pairs":
                self._press_card(idx, now)
            elif self.mode == "slot":
                self._press_slot(idx, now)
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

    def _press_card(self, idx: int, now: float) -> None:
        if now < self.peek_until or idx in self.matched:
            return
        if len(self.open) == 2:  # 틀린 한 쌍이 아직 보이는 중이면 바로 덮고 진행
            self.open = []
        if idx in self.open:
            return
        self.open.append(idx)
        if len(self.open) == 2:
            self.score += 1  # 시도 횟수
            a, b = self.open
            if self.cards[a] == self.cards[b]:
                self.matched |= {a, b}
                self.open = []
                if len(self.matched) == BOARD:
                    self._finish()
            else:
                self.flip_back = now + 0.9

    def _press_slot(self, idx: int, now: float) -> None:
        if idx in SLOT_LEVERS and not any(self.spinning):
            if self.coins <= 0:
                return
            self.coins -= 1
            self.score += 1  # 돌린 횟수
            self.spinning = [True, True, True]
            self.spin_next, self.spin_auto, self.win = now, now + 6, 0
            self._save_coins()
        elif idx in SLOT_STOPS or idx in SLOT_REELS:
            k = (SLOT_STOPS.index(idx) if idx in SLOT_STOPS else SLOT_REELS.index(idx))
            if self.spinning[k]:
                self.spinning[k] = False
                self._after_stop(now)

    def _after_stop(self, now: float) -> None:
        if any(self.spinning):
            return
        a, b, c = self.reels
        if a == b == c:
            self.win = SLOT_PAY[a]
        elif a == b or b == c or a == c:
            self.win = 2
        else:
            self.win = 0
        if self.win:
            self.coins += self.win
            self.win_until = now + (2.4 if self.win >= 30 else 1.4)
        self._save_coins()
        if self.coins <= 0:
            self._finish()

    # ---- 블랙잭 ----
    def _draw(self) -> tuple[str, str]:
        if len(self.shoe) < 15:  # 카드 2벌을 섞어 쓴다
            self.shoe = [(r, s) for r in RANKS for s in SUITS] * 2
            self.rnd.shuffle(self.shoe)
        return self.shoe.pop()

    def _press_bj(self, idx: int, now: float) -> None:
        if self.phase in ("bet", "done"):
            if idx == BJ_STAND and self.phase == "bet":
                self.bet = BJ_BETS[(BJ_BETS.index(self.bet) + 1) % len(BJ_BETS)] if self.bet in BJ_BETS else 1
            elif idx == BJ_HIT or (self.phase == "done" and idx < BOARD):
                self._deal(now)
            elif idx == BJ_STAND:
                self.phase = "bet"
            return
        if self.phase != "play":
            return
        if idx == BJ_HIT:
            self.player.append(self._draw())
            if hand_value(self.player)[0] >= 21:
                self._dealer_turn(now)
        elif idx == BJ_STAND:
            self._dealer_turn(now)
        elif idx >= 13 and len(self.player) == 2 and self.coins >= self.bet:  # 넓은 칸 = 더블
            self.coins -= self.bet
            self.bet_now *= 2
            self.player.append(self._draw())
            self._dealer_turn(now)

    def _deal(self, now: float) -> None:
        if self.coins <= 0:  # 다 잃었으면 다시 채워 주기
            self.coins = SLOT_START
        bet = min(self.bet, self.coins)
        self.coins -= bet
        self.bet_now = bet
        self.player = [self._draw(), self._draw()]
        self.dealer = [self._draw(), self._draw()]
        self.hole, self.result, self.phase = True, "", "play"
        self._save_coins()
        if hand_value(self.player)[0] == 21 or hand_value(self.dealer)[0] == 21:  # 블랙잭이면 바로 결판
            self.hole = False
            self._settle(now)

    def _dealer_turn(self, now: float) -> None:
        self.hole, self.phase, self.next_draw = False, "dealer", now + 0.7
        if hand_value(self.player)[0] > 21:  # 버스트: 딜러는 더 안 뽑는다
            self._settle(now)

    def _settle(self, now: float) -> None:
        p, d = hand_value(self.player)[0], hand_value(self.dealer)[0]
        natural = p == 21 and len(self.player) == 2
        dealer_natural = d == 21 and len(self.dealer) == 2
        if p > 21:
            self.result, pay = "lose", 0
        elif natural and not dealer_natural:
            self.result, pay = "bj", self.bet_now + (self.bet_now * 3) // 2  # 3:2
        elif dealer_natural and not natural:
            self.result, pay = "lose", 0
        elif d > 21 or p > d:
            self.result, pay = "win", self.bet_now * 2
        elif p == d:
            self.result, pay = "push", self.bet_now
        else:
            self.result, pay = "lose", 0
        self.coins += pay
        self.win = pay - self.bet_now
        self.phase = "done"
        if self.result in ("win", "bj"):
            self.win_until = now + 1.6
        self._save_coins()

    # ---- 포커 대결 (5장 드로우, 컴퓨터와 1:1) ----
    def _press_poker(self, idx: int, now: float) -> None:
        """윗줄 = 상대 카드, 아랫줄 = 내 카드(눌러서 킵). 넓은 칸 = 교체.
        대기 중엔 아랫줄이 베팅액(1·2·5·10)과 딜, 끝난 뒤엔 아무 칸 = 같은 베팅으로 다음 판, 넓은 칸 = 베팅 바꾸기."""
        if self.phase == "play":
            if 5 <= idx < BOARD:
                self.held[idx - 5] = not self.held[idx - 5]
            elif idx >= 13:
                self._poker_draw(now)
            return
        if self.phase == "done":
            if idx >= 13:
                self.phase = "bet"
            elif idx < BOARD:
                self._poker_deal()
            return
        if self.phase == "bet":
            if 5 <= idx <= 8:
                self.bet = BJ_BETS[idx - 5]
            elif idx == 9 or idx >= 13:
                self._poker_deal()

    def _poker_deal(self) -> None:
        if self.coins <= 0:
            self.coins = SLOT_START
        self.shoe = [(r, s) for r in RANKS for s in SUITS]  # 매 판 새 카드 한 벌
        self.rnd.shuffle(self.shoe)
        self.bet_now = min(self.bet, self.coins)
        self.coins -= self.bet_now
        self.hand = [self.shoe.pop() for _ in range(5)]
        self.opp = [self.shoe.pop() for _ in range(5)]
        self.held, self.phase, self.opp_swapped, self.poker_cmp = [False] * 5, "play", 0, 0
        self._save_coins()

    def _poker_draw(self, now: float) -> None:
        self.hand = [c if h else self.shoe.pop() for c, h in zip(self.hand, self.held)]
        keep = poker_ai_holds(self.opp)
        self.opp_swapped = keep.count(False)
        self.opp = [c if k else self.shoe.pop() for c, k in zip(self.opp, keep)]
        self.phase, self.next_draw = "opp", now + 0.9  # 상대가 바꾸는 동안 잠깐 뜸 들이기

    def _poker_showdown(self, now: float) -> None:
        me, op = poker_rank(self.hand), poker_rank(self.opp)
        self.poker_cmp = (me > op) - (me < op)
        if self.poker_cmp > 0:
            mult = POKER_BONUS.get(me[0], 1)
            pay = self.bet_now * (1 + mult)
            self.win_until = now + (2.4 if mult >= 25 else 1.4)
        elif self.poker_cmp == 0:
            pay = self.bet_now
        else:
            pay = 0
        self.coins += pay
        self.win = pay - self.bet_now
        self.phase = "done"
        self._save_coins()

    def _save_coins(self) -> None:
        self.best["slot_coins"] = self.coins
        self.best["slot"] = max(self.best.get("slot", 0), self.coins)
        self._save()

    def start(self, mode: str) -> None:
        with self.lock:
            now = time.time()
            self.mode, self.score, self.new_best = mode, 0, False
            self.holes, self.lit = {}, None
            self.wrong = None
            if mode == "mole":
                self.phase, self.end_at, self.next_pop = "play", now + MOLE_SEC, now + 0.6
            elif mode == "pairs":
                self.cards = PAIR_CARDS * 2
                self.rnd.shuffle(self.cards)
                self.matched, self.open = set(), []
                self.phase, self.peek_until, self.started = "play", now + 1.5, now
            elif mode == "poker":
                self.phase, self.hand, self.opp, self.held = "bet", [], [], [False] * 5
            elif mode == "bj":
                self.phase, self.player, self.dealer, self.result = "bet", [], [], ""
                self.bet = min(self.bet, max(1, self.coins)) if self.coins else 2
            elif mode == "slot":
                if self.coins <= 0:  # 다 잃었으면 다시 채워 주기
                    self.coins = SLOT_START
                    self._save_coins()
                self.phase, self.spinning, self.win = "play", [False, False, False], 0
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
            elif self.mode == "pairs":
                if len(self.open) == 2 and now >= self.flip_back:
                    self.open = []
            elif self.mode == "poker":
                if self.phase == "opp" and now >= self.next_draw:
                    self._poker_showdown(now)
            elif self.mode == "bj":
                if self.phase == "dealer" and now >= self.next_draw:
                    if hand_value(self.dealer)[0] < 17:  # 딜러는 16 이하면 뽑고 17 이상이면 멈춘다
                        self.dealer.append(self._draw())
                        self.next_draw = now + 0.7
                    else:
                        self._settle(now)
            elif self.mode == "slot":
                if any(self.spinning) and now >= self.spin_next:
                    for k, on in enumerate(self.spinning):
                        if on:
                            i = SLOT_SYMBOLS.index(self.reels[k])
                            self.reels[k] = SLOT_SYMBOLS[(i + 1 + k) % len(SLOT_SYMBOLS)]
                    self.spin_next = now + 0.13
                    if now >= self.spin_auto:  # 너무 오래 안 누르면 자동 정지
                        self.spinning = [False, False, False]
                        self._after_stop(now)
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
                for c, g in enumerate(GAMES):
                    out[c] = menu_tile(g, self.best_text(g))
                return out
            now = time.time()
            if self.mode == "pairs":
                out = {}
                for i in range(BOARD):
                    face = self.cards[i]
                    if i in self.matched:
                        out[i] = card_tile(face, "done")
                    elif now < self.peek_until or i in self.open:
                        out[i] = card_tile(face, "wrong" if len(self.open) == 2 and i in self.open else "up")
                    else:
                        out[i] = card_tile(None, "down")
                return out
            if self.mode == "poker":
                out = {}
                glow_on = now < self.win_until and int(now * 5) % 2 == 0
                done = self.phase == "done"
                me_g = "win" if done and self.poker_cmp > 0 and (glow_on or now >= self.win_until) else \
                    ("lose" if done and self.poker_cmp < 0 else "")
                op_g = "win" if done and self.poker_cmp < 0 else ("lose" if done and self.poker_cmp > 0 else "")
                for k in range(5):  # 윗줄: 상대
                    show = self.opp and (done or k in POKER_OPEN)
                    out[k] = play_card(self.opp[k], op_g) if show else play_card(None)
                if self.phase == "bet" or not self.hand:
                    for k in range(4):
                        out[5 + k] = bj_button(str(BJ_BETS[k]), "코인 걸기", "#7dcfff", self.bet == BJ_BETS[k])
                    out[9] = bj_button("딜", f"{min(self.bet, max(self.coins, 1))}코인", "#9ece6a")
                    return out
                for k in range(5):  # 아랫줄: 나
                    c = self.hand[k]
                    out[5 + k] = held_card(c) if self.phase == "play" and self.held[k] else play_card(c, me_g)
                return out
            if self.mode == "bj":
                pg = {"win": "win", "bj": "win", "lose": "lose"}.get(self.result, "")
                dg = {"win": "lose", "bj": "lose", "lose": "win"}.get(self.result, "")
                dealer = [self.dealer[0], None] + self.dealer[2:] if self.hole and self.dealer else self.dealer
                out = {}
                for k, cards in enumerate(_layout(dealer)):
                    out[k] = hand_tile(cards, dg)
                for k, cards in enumerate(_layout(self.player)):
                    out[5 + k] = hand_tile(cards, pg)
                if self.phase == "play":
                    out[BJ_HIT] = bj_button("HIT", "한 장 더", "#9ece6a")
                    out[BJ_STAND] = bj_button("STAND", "그만", "#f7768e")
                elif self.phase == "dealer":
                    out[BJ_HIT] = bj_button("HIT", "딜러 차례", "#9ece6a", False)
                    out[BJ_STAND] = bj_button("STAND", "", "#f7768e", False)
                else:
                    out[BJ_HIT] = bj_button("딜", f"{min(self.bet, max(self.coins, 1))}코인 걸기", "#e0af68")
                    out[BJ_STAND] = bj_button(f"{self.bet}", "베팅 바꾸기", "#7dcfff") if self.phase == "bet" \
                        else bj_button("베팅", "바꾸기", "#7dcfff")
                return out
            if self.mode == "slot":
                glow = now < self.win_until and int(now * 5) % 2 == 0
                spinning = any(self.spinning)
                out = {i: blank_tile() for i in range(BOARD)}
                for k, (r, st) in enumerate(zip(SLOT_REELS, SLOT_STOPS)):
                    out[r] = reel_tile(self.reels[k], glow, self.spinning[k])
                    out[st] = slot_button("stop" if self.spinning[k] else "stopped")
                for i in SLOT_LEVERS:
                    out[i] = slot_button("wait" if spinning or self.coins <= 0 else "lever")
                return out
            if self.mode == "mole":
                return {i: mole_tile(self.holes.get(i, ("empty", 0))[0]) for i in range(BOARD)}
            wrong = self.wrong
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
                return wide_panel("게임", "", ["하고 싶은 게임 칸을 누르세요",
                                              "두더지 · 순서 · 짝 · 슬롯 · 블랙잭 · 포커",
                                              "가운데 버튼: 게임 중 메뉴로"], "#9ece6a")
            if self.mode == "poker":
                if self.phase in ("play", "opp"):
                    me = POKER_NAMES[poker_rank(self.hand)[0]]
                    if self.phase == "opp":
                        return wide_panel("상대가 바꾸는 중", "…", [f"상대 {self.opp_swapped}장 교체", f"내 패: {me}"],
                                          "#bb9af7")
                    return wide_panel("포커 대결", "교체", ["내 카드를 눌러 킵", "킵 다 고르면 여기 누르기",
                                                        f"내 패: {me} · 베팅 {self.bet_now}코인"], "#e0af68")
                if self.phase == "done":
                    me, op = POKER_NAMES[poker_rank(self.hand)[0]], POKER_NAMES[poker_rank(self.opp)[0]]
                    head = {1: "이겼어요", 0: "비겼어요", -1: "졌어요"}[self.poker_cmp]
                    if self.poker_cmp > 0 and poker_rank(self.hand)[0] >= 4:
                        head = me + "!"
                    big = f"+{self.win}" if self.win > 0 else ("0" if self.win == 0 else str(self.win))
                    color = "#9ece6a" if self.poker_cmp > 0 else ("#7dcfff" if self.poker_cmp == 0 else "#f7768e")
                    return wide_panel(head, big, [f"나 {me} vs 상대 {op}", f"코인 {self.coins}",
                                                  "아무 칸: 다음 판 · 여기: 베팅"], color)
                return wide_panel("포커 대결", str(self.coins), ["컴퓨터와 5장 드로우 포커",
                                                             "이기면 2배 · 스트레이트 이상은 보너스",
                                                             "베팅 고르고 딜"], "#e0af68")
            if self.mode == "bj":
                p = hand_value(self.player)[0] if self.player else 0
                if self.phase == "bet":
                    return wide_panel("블랙잭", str(self.coins), ["오른쪽 위: 딜 · 오른쪽 아래: 베팅 바꾸기",
                                                              f"베팅 {self.bet}코인", "21에 가깝게, 넘으면 짐"], "#bb9af7")
                if self.phase in ("play", "dealer"):
                    shown = hand_value(self.dealer[:1])[0] if self.hole else hand_value(self.dealer)[0]
                    dbl = "넓은 칸: 더블" if self.phase == "play" and len(self.player) == 2 and self.coins >= self.bet_now \
                        else f"코인 {self.coins}"
                    return wide_panel("블랙잭", str(p), [f"딜러 {shown}{'+?' if self.hole else ''} · 나 {p}",
                                                        f"베팅 {self.bet_now}코인", dbl], "#bb9af7")
                d = hand_value(self.dealer)[0]
                head = {"bj": "블랙잭!", "win": "이겼어요", "push": "비겼어요", "lose": "졌어요"}[self.result]
                big = f"+{self.win}" if self.win > 0 else ("0" if self.win == 0 else str(self.win))
                why = "버스트" if p > 21 else ("딜러 버스트" if d > 21 else f"딜러 {d} · 나 {p}")
                return wide_panel(head, big, [why, f"코인 {self.coins}", "아무 칸: 다음 판"],
                                  "#e0af68" if self.result in ("win", "bj") else ("#7dcfff" if self.result == "push" else "#f7768e"))
            if self.mode == "slot":
                if self.phase == "over":
                    return wide_panel("코인을 다 썼어요", "0", ["판 누르기: 20코인으로 다시", "가운데: 메뉴"], "#f7768e")
                if time.time() < self.win_until:
                    head = "잭팟!" if self.win >= 30 else ("당첨!" if self.win > 2 else "두 개 같음")
                    return wide_panel(head, f"+{self.win}", [f"코인 {self.coins}", f"최고 {self.best.get('slot', 0)}"],
                                      "#e0af68")
                hint = "STOP 으로 하나씩 멈추기" if any(self.spinning) else "양쪽 끝 칸: 돌리기 (1코인)"
                return wide_panel("슬롯머신", str(self.coins), [hint, "7 7 7 = 50 · 다이아 30 · 별 15", "두 개 같으면 +2"],
                                  "#ff9e64")
            if self.mode == "pairs" and self.phase != "over":
                secs = int(time.time() - self.started)
                msg = "잘 봐 두세요" if time.time() < self.peek_until else f"맞춘 짝 {len(self.matched) // 2}/5"
                return wide_panel("짝 맞추기", str(self.score), [msg, f"시도 {self.score}번 · {secs}초",
                                                                self.best_text("pairs")], "#73daca")
            if self.phase == "over":
                head = "새 기록!" if self.new_best else ("다 맞췄어요" if self.mode == "pairs" else "게임 끝")
                best_line = self.best_text(self.mode) if self.mode == "pairs" else f"최고 {max(best, self.score)}"
                return wide_panel(head, str(self.score), [best_line, "판 누르기: 다시 하기",
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
            if self.mode == "pairs" and self.phase == "play":
                sec = int(time.time() - self.started)
            now = time.time()
            return (self.mode, self.phase, self.score, self.pos, len(self.seq), sec, self.new_best, self.coins,
                    any(self.spinning), now < self.win_until, now < self.peek_until, len(self.matched),
                    len(self.player), len(self.dealer), self.hole, self.result, self.bet, tuple(self.held),
                    tuple(self.hand), tuple(self.opp))
