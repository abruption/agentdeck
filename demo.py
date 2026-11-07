"""README 이미지를 가짜 데이터로 만든다 (장치·네트워크 불필요).

사용: .venv/bin/python demo.py [출력 폴더, 기본 docs/images]
만드는 것: banner.png / banner.en.png, hero.gif, 페이지별 기기 목업 PNG
"""

from __future__ import annotations

import io
import os
import sys
import time
from datetime import datetime, timedelta, timezone

from PIL import Image, ImageDraw, ImageFilter

import i18n
import pages
import remote_herdr
from clock import _kr, _sf, render_clock, render_market, render_timer, render_worktree_summary
from d200 import render_icon
from machines import MachineStat, Volume
from mole import MoleStatus
from pages import (LLM, Limit, nav, nav_device, nav_worktrees, page_device, page_grid, page_machines, page_pomodoro,
                   page_market, page_studio, page_summary, page_worktrees)
from pomodoro import Pomodoro
from remote_herdr import StudioState, TowerMeta, Workspace
from worktrees import Worktree

NOW = datetime.now(timezone.utc)
H5, WEEK = timedelta(hours=5), timedelta(days=7)
TOWER = "CONTROL_TOWER"
remote_herdr.TOWER_SPACE = pages.TOWER_SPACE = TOWER  # 데모용 리드 스페이스 이름
import machines as _machines  # noqa: E402

# 데모는 개인 config.json 값을 쓰지 않는다 (외장 드라이브 이름·컴퓨터 이름이 이미지에 새지 않게)
_machines.EXTERNAL_DRIVES = [("My Book", "Studio"), ("Backup", "Mini 2")]


# ---------- 가짜 데이터 ----------
def mock_llms() -> list[LLM]:
    return [
        LLM("CLAUDE", "#d97757", five=Limit(0.72, NOW + timedelta(hours=2), H5), week=Limit(0.48, NOW + timedelta(days=4), WEEK)),
        LLM("CODEX", "#10a37f", week=Limit(0.86, NOW + timedelta(days=6), WEEK)),
        LLM("AGY", "#7aa2f7", five=Limit(1.0, NOW + H5, H5), week=Limit(0.93, NOW + timedelta(days=5), WEEK)),
    ]


def mock_studio() -> tuple[StudioState, TowerMeta]:
    tower = Workspace(TOWER, space_id="s/tower", tabs=["s/lead", "s/misc"], tab_names={"s/lead": "lead", "s/misc": "misc"})
    for term, st in (("s/t1", "working"), ("s/t2", "blocked"), ("s/t3", "idle"), ("s/t4", "done")):
        tower.term_tab[term] = "s/lead"
        tower.add(term, "claude-code", st, True, ["s/t9", "s/t10"] if term == "s/t1" else [])
    tower.term_tab["s/t5"] = "s/misc"
    tower.add("s/t5", "claude-code", "idle", True)

    def ws(name, *agents):
        w = Workspace(name, space_id="s/" + name)
        for i, (app, st, top) in enumerate(agents):
            w.add(f"s/{name}{i}", app, st, top)
        return w

    spaces = [tower,
              ws("Web App", ("claude-code", "working", True), ("codex", "working", False), ("codex", "idle", False)),
              ws("Content", ("codex", "done", True), ("antigravity", "idle", True)),
              ws("Data Pipeline", ("claude-code", "idle", True), ("codex", "working", False)),
              ws("Marketing", ("claude-code", "idle", True)),
              ws("Mobile", ("codex", "idle", True))]
    meta = TowerMeta({"s/t1": "Planning lead", "s/t2": "Release lead", "s/t3": "Sales lead", "s/t4": "Docs lead"},
                     {"s/t1": [("X", "working"), ("A", "working")]})
    return StudioState(True, spaces, "demo"), meta


def mock_machines() -> list[MachineStat]:
    return [
        MachineStat("MacBook", True, 18, 41, 32, 25, 1400, 12),
        MachineStat("Studio", True, 22, 35, 128, 19, 1500, 3, [Volume("My Book", "Studio", True, 7450, 5900)]),
        MachineStat("Mini", True, 31, 58, 16, 89, 26, 17),
        MachineStat("Mini 2", True, 12, 47, 16, 46, 123, 30, [Volume("Backup", "Mini 2", True, 476, 280)]),
    ]


def mock_worktrees() -> list[Worktree]:
    def wt(repo, name, dirty, ahead, age, agents=()):
        return Worktree(f"~/wt/{repo}/{name}", repo, name, "feat/" + name, dirty, age, "origin/main", ahead, list(agents))
    return [wt("web-app", "checkout-redesign", 42, 7, 20), wt("web-app", "old-experiment", 0, 12, 400),
            wt("content", "ep12-render", 0, 0, 5), wt("pipeline", "etl-fix", 3, 2, 1, [{"address": "t7", "status": "working"}]),
            wt("mobile", "push-settings", 0, 1, 10)]


def mock_market():
    from market import Index, Quote
    names = [("삼성전자", 2.41, "93,500"), ("SK하이닉스", 4.87, "212,000"), ("LG에너지솔루션", -1.32, "381,500"),
             ("삼성바이오로직스", 0.42, "1,021,000"), ("현대차", -2.75, "243,000"), ("기아", -0.61, "104,800"),
             ("셀트리온", 1.18, "187,400"), ("KB금융", 0.05, "96,200"), ("NAVER", -4.12, "203,500"),
             ("한화에어로스페이스", 6.20, "512,000")]
    quotes = [Quote(n, c, p) for n, c, p in names]
    return quotes, [Index("KOSPI", "2,846.12", 1.24, "OPEN"), Index("KOSDAQ", "871.35", -0.38, "OPEN")], (612, 358)


def mock_market_views():
    """히트맵 6가지 보기 (가짜 데이터)."""
    from market import Quote
    q = lambda rows: [Quote(n, c, p) for n, c, p in rows]  # noqa: E731
    kosdaq = q([("알테오젠", 3.1, "412,000"), ("에코프로비엠", -2.4, "128,500"), ("에코프로", -1.8, "71,200"),
                ("HLB", 5.6, "88,400"), ("리가켐바이오", 1.2, "132,900"), ("레인보우로보틱스", -3.9, "246,000"),
                ("삼천당제약", 0.8, "158,300"), ("휴젤", -0.4, "301,500"), ("클래시스", 2.2, "58,700"), ("펩트론", 7.4, "96,100")])
    movers = q([("조선", 4.8, "▲9 ▼2"), ("우주항공과국방", 3.9, "▲11 ▼3"), ("반도체와반도체장비", 2.7, "▲64 ▼31"),
                ("전기장비", 2.1, "▲28 ▼12"), ("생물공학", 1.6, "▲70 ▼45"), ("은행", -1.2, "▲3 ▼8"),
                ("화장품", -1.9, "▲12 ▼30"), ("해운사", -2.3, "▲2 ▼7"), ("게임엔터테인먼트", -2.8, "▲6 ▼25"),
                ("항공사", -3.6, "▲1 ▼6")])
    port = q([("삼성전자", 2.41, "93,500"), ("SK하이닉스", 4.87, "212,000"), ("NAVER", -4.12, "203,500"),
              ("카카오", -1.05, "47,250"), ("현대차", -2.75, "243,000")])
    secs = q([("반도체와반도체장비", 2.7, "▲64 ▼31"), ("전기제품", -0.9, "▲10 ▼14"), ("자동차", -1.4, "▲4 ▼9"),
              ("조선", 4.8, "▲9 ▼2"), ("우주항공과국방", 3.9, "▲11 ▼3"), ("생물공학", 1.6, "▲70 ▼45"),
              ("제약", 0.6, "▲60 ▼52"), ("은행", -1.2, "▲3 ▼8"), ("증권", 1.1, "▲18 ▼9"), ("소프트웨어", -0.3, "▲40 ▼44")])
    macro = [Quote("USD/KRW", 0.42, "", "", "1,382.5", "+0.42%"), Quote("100JPY/KRW", -0.31, "", "", "912.3", "-0.31%"),
             Quote("EUR/KRW", 0.12, "", "", "1,498.2", "+0.12%"), Quote("DXY", 0.35, "", "", "104.12", "+0.35%"),
             Quote("WTI", -1.84, "", "", "$76.40", "-1.84%"), Quote("Brent", -1.52, "", "", "$80.95", "-1.52%"),
             Quote("Gold", 0.95, "", "", "$2,412.80", "+0.95%"), Quote("Silver", 1.62, "", "", "$31.25", "+1.62%"),
             Quote("US 10Y", 0.6, "", "", "4.231%", "+2.5bp"), Quote("US 2Y", -0.4, "", "", "4.612%", "-1.8bp")]
    return {"top": mock_market()[0], "kosdaq": kosdaq, "movers": movers, "portfolio": port, "sectors": secs, "macro": macro}


def heatmap_gif(path: str) -> None:
    from market import VIEW_LABEL, VIEWS
    views, (_, idx, br) = mock_market_views(), mock_market()
    frames = []
    for i, v in enumerate(VIEWS):
        nxt = VIEW_LABEL[VIEWS[(i + 1) % len(VIEWS)]]
        frames.append(device_mockup({**page_market(v, views[v]), **nav(6, 7, 80, ("보기", f"→ {nxt}"))},
                                    render_market(idx, br, VIEW_LABEL[v]), 0.6))
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=1600, loop=0, optimize=True)


def aquarium_gif(path: str) -> None:
    from aquarium import Aquarium

    aq, frames = Aquarium(14, seed=7), []
    for i in range(36):
        aq.step(0.2)
        if i == 12:
            aq.feed(6)
        if i == 4:  # 문어가 솟구치는 장면도 담기
            aq.octopus.vy, aq.octopus.vx = -26, 4
        tiles, wide = aq.tiles()
        frames.append(device_mockup({k: _img_button(v) for k, v in tiles.items()}, wide, 0.5))
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=200, loop=0, optimize=True)


def game_gif(path: str) -> None:
    """7페이지 게임: 두더지 잡기 몇 장면 + 순서 기억 몇 장면 (각본대로)."""
    import time as _t

    import games
    from d200 import Button

    g = games.Games()
    g.best = {"mole": 31, "simon": 9, "pairs": 7, "slot": 64}
    g.coins = 23
    frames, ms = [], []

    def snap(dur: int, middle=("메뉴", "게임 그만")) -> None:
        body = {i: Button(image=p) for i, p in g.tiles().items()}
        frames.append(device_mockup({**body, **nav(7, 8, 80, middle)}, g.wide(), 0.5))
        ms.append(dur)

    g.menu()
    snap(1400, None)
    g.mode, g.phase, g.score = "mole", "play", 0
    script = [({2: "mole", 6: "mole"}, 0), ({2: "hit", 6: "mole", 8: "bomb"}, 1), ({6: "hit", 8: "bomb", 4: "gold"}, 2),
              ({4: "hit", 0: "mole"}, 5), ({0: "mole", 7: "mole", 9: "bomb"}, 5), ({0: "hit", 7: "mole", 9: "boom"}, 3),
              ({7: "hit", 3: "mole"}, 4), ({3: "hit", 5: "gold"}, 5)]
    for k, (holes, score) in enumerate(script):
        g.holes = {i: (s, 1e12) for i, s in holes.items()}
        g.score, g.end_at = score, _t.time() + 22 - k * 1.5
        snap(450)
    g.mode, g.seq, g.score = "simon", [2, 7, 4, 9], 3
    for lit in (2, None, 7, None, 4, None, 9, None):
        g.phase, g.lit = "show", lit
        snap(380 if lit is not None else 160)
    for k, lit in enumerate((2, 7, 4, 9)):
        g.phase, g.pos, g.lit = "input", k + 1, lit
        snap(380)
    # 짝 맞추기: 몇 장 뒤집고 한 쌍 맞추기
    g.mode, g.phase, g.started, g.peek_until = "pairs", "play", _t.time() - 14, 0
    g.cards = ["🐟", "🐙", "🦀", "🐢", "🦈", "🐢", "🦈", "🐟", "🐙", "🦀"]
    g.score, g.matched, g.open = 3, {0, 7}, [1, 4]
    snap(700)
    g.score, g.open = 4, [3]
    snap(450)
    g.score, g.matched, g.open = 4, {0, 7, 3, 5}, []
    snap(800)
    # 슬롯머신: 돌다가 하나씩 멈춰 777
    g.mode, g.phase, g.win, g.win_until = "slot", "play", 0, 0
    seq = [(["🍒", "⭐", "🔔"], [1, 1, 1]), (["🍋", "💎", "7"], [1, 1, 1]), (["7", "🍒", "🍒"], [0, 1, 1]),
           (["7", "7", "⭐"], [0, 0, 1]), (["7", "7", "7"], [0, 0, 0])]
    for reels, spin in seq:
        g.reels, g.spinning = reels, [bool(x) for x in spin]
        snap(350)
    g.coins, g.win, g.win_until = 72, 50, _t.time() + 99
    snap(1400)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=ms, loop=0, optimize=True)


def _img_button(png: bytes):
    from d200 import Button
    return Button(image=png)


def clock_png() -> bytes:
    return render_clock(status=[("작업 2", "#7aa2f7"), ("결정 1", "#e0af68"), ("추천 AGY", "#9ece6a")])


# ---------- 기기 목업 렌더 ----------
def _rounded(img: Image.Image, r: int) -> Image.Image:
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, img.width - 1, img.height - 1), r, fill=255)
    out = Image.new("RGBA", img.size)
    out.paste(img.convert("RGBA"), (0, 0), mask)
    return out


def device_mockup(buttons: dict, small: bytes, scale: float = 1.0, transparent: bool = False,
                  photo: bool = False) -> Image.Image:
    """D200 실물 느낌: (그라데이션 배경) + 그림자 + 본체 + 둥근 버튼 + 넓은 칸."""
    cell, gap, r, pad = 196, 22, 26, 46
    grid_w, grid_h = 5 * cell + 4 * gap, 3 * cell + 2 * gap
    body_w, body_h = grid_w + 2 * pad, grid_h + 2 * pad
    W, H = body_w + 220, body_h + 200
    if transparent:
        bg = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    else:  # 배너와 같은 리넨 사진 배경의 빈 부분을 잘라 씀 (보라 그라데이션 대신)
        photo = True
        src = Image.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs/images/banner-bg.jpg"))
        crop_w = int(src.height * W / H)
        left = (src.width - crop_w) // 2
        bg = src.crop((left, 0, left + crop_w, src.height)).resize((W, H), Image.LANCZOS).convert("RGBA")
    bx, by = (W - body_w) // 2, (H - body_h) // 2
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if photo:  # 사진 배경용: 왼쪽 위 자연광 → 오른쪽 아래로 길고 옅은 그림자 + 바닥 접지 그림자
        sd = ImageDraw.Draw(shadow)
        sd.rounded_rectangle((bx + 60, by + 70, bx + body_w + 60, by + body_h + 70), 60, fill=(60, 45, 30, 80))
        shadow = shadow.filter(ImageFilter.GaussianBlur(55))
        contact = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(contact).rounded_rectangle((bx + 6, by + 12, bx + body_w + 8, by + body_h + 12), 58, fill=(40, 30, 20, 120))
        shadow = Image.alpha_composite(shadow, contact.filter(ImageFilter.GaussianBlur(10)))
    else:
        ImageDraw.Draw(shadow).rounded_rectangle((bx + 10, by + 40, bx + body_w - 10, by + body_h + 40), 60, fill=(0, 0, 0, 170))
        shadow = shadow.filter(ImageFilter.GaussianBlur(40))
    bg = Image.alpha_composite(bg, shadow)
    body = Image.new("RGBA", (body_w, body_h), (0, 0, 0, 0))
    bd = ImageDraw.Draw(body)
    if photo:  # 무광 블랙 알루미늄 느낌: 위쪽 가장자리에 옅은 하이라이트
        bd.rounded_rectangle((0, 0, body_w - 1, body_h - 1), 56, fill=(28, 28, 30), outline=(70, 70, 72), width=2)
        bd.rounded_rectangle((3, 3, body_w - 4, body_h - 4), 53, outline=(44, 44, 46), width=2)
    else:
        bd.rounded_rectangle((0, 0, body_w - 1, body_h - 1), 56, fill=(24, 25, 32), outline=(58, 60, 76), width=3)
        bd.rounded_rectangle((8, 8, body_w - 9, body_h - 9), 50, outline=(36, 37, 48), width=2)
    bg.alpha_composite(body, (bx, by))
    gx, gy = bx + pad, by + pad
    for i in range(13):
        if i in buttons:
            tile = _rounded(Image.open(io.BytesIO(render_icon(buttons[i]))), r)
            bg.alpha_composite(tile, (gx + (i % 5) * (cell + gap), gy + (i // 5) * (cell + gap)))
    wide = _rounded(Image.open(io.BytesIO(small)).resize((2 * cell + gap, cell)), r)
    bg.alpha_composite(wide, (gx + 3 * (cell + gap), gy + 2 * (cell + gap)))
    out = bg if transparent else bg.convert("RGB")
    if scale != 1.0:
        out = out.resize((int(out.width * scale), int(out.height * scale)), Image.LANCZOS)
    return out


# ---------- 화면 모음 ----------
def screens() -> dict[str, tuple[dict, bytes]]:
    llms, (studio, meta), machines, wts = mock_llms(), mock_studio(), mock_machines(), mock_worktrees()
    clock = clock_png()
    row = [w for w in studio.workspaces if w.name != TOWER][:5]
    mole = {m.name: MoleStatus(95 if m.name != "Mini" else 83, "Excellent", 1.2) for m in machines}
    dry = {"Studio": {"clean_gb": 15.2}, "Mini": {"clean_gb": 13.1}}
    pomo = Pomodoro(state="running", duration=25 * 60, end_at=time.time() + 25 * 60 * 0.63)
    ms = MoleStatus(83, "Good: Restart Recommended", 0.6, [("node", 48.0), ("Xcode", 26.0), ("mds", 25.0)])
    return {
        "page1-summary": ({**page_summary(llms, studio, NOW, False), **nav(1, 5, 80)}, clock),
        "page2-limits": ({**page_grid(llms, NOW), **nav(2, 5, 80)}, clock),
        "page3-studio": ({**page_studio(studio, True, row, meta), **nav(3, 5, 80)}, render_worktree_summary(wts)),
        "page4-machines": ({**page_machines(machines, NOW, mole, dry), **nav(4, 5, 80)}, clock),
        "page5-pomodoro": ({**page_pomodoro(pomo, False), **nav(5, 5, 80)}, render_timer(pomo.remaining(), "running", pomo.end_at)),
        "worktrees": ({**page_worktrees(wts, None, None), **nav_worktrees(80)}, clock),
        "device": ({**page_device(machines[2], ms, {"purge_gb": 3.1, "purge_items": 82, "clean_gb": 13.1}, (4, 0.6), None),
                    **nav_device(80)}, clock),
    }


def hero_gif(out: str, name: str = "hero.gif") -> None:
    """페이지를 넘기며 깜빡임·타이머까지 보여주는 애니메이션."""
    llms, (studio, meta) = mock_llms(), mock_studio()
    s = screens()
    row = [w for w in studio.workspaces if w.name != TOWER][:5]
    seq: list[tuple[dict, bytes, int]] = [
        (*s["page1-summary"], 1400),
        ({**page_summary(llms, studio, NOW, True), **nav(1, 5, 80)}, clock_png(), 450),
        (*s["page2-limits"], 1500),
    ]
    for i in range(4):  # 결정·완료 칸 깜빡임
        seq.append(({**page_studio(studio, i % 2 == 0, row, meta), **nav(3, 5, 80)}, s["page3-studio"][1], 420))
    seq += [(*s["worktrees"], 1400), (*s["page4-machines"], 1400), (*s["device"], 1400)]
    for frac in (0.9, 0.6, 0.3, 0.05):  # 뽀모도로 칸이 거꾸로 줄어드는 모습
        p = Pomodoro(state="running", duration=25 * 60, end_at=time.time() + 25 * 60 * frac)
        seq.append(({**page_pomodoro(p, False), **nav(5, 5, 80)}, render_timer(p.remaining(), "running", p.end_at), 450))
    frames = [device_mockup(b, sm, 0.5) for b, sm, _ in seq]
    frames[0].save(os.path.join(out, name), save_all=True, append_images=frames[1:],
                   duration=[ms for *_, ms in seq], loop=0, optimize=True)


def banner(out: str, lang: str = "ko") -> None:
    """맨 위 배너: Codex 로 생성한 제품 사진풍 배경(banner-bg.jpg) + 실제 화면을 띄운 기기 + 절제된 타이포."""
    llms, (studio, _) = mock_llms(), mock_studio()
    bg = Image.open(os.path.join(out, "banner-bg.jpg")).convert("RGBA")
    W, H = bg.size  # 2172 x 724
    dev = device_mockup({**page_summary(llms, studio, NOW, True), **nav(1, 5, 80)}, clock_png(), 0.58,
                        transparent=True, photo=True)
    bg.alpha_composite(dev, (W - dev.width - 250, (H - dev.height) // 2 + 6))
    d = ImageDraw.Draw(bg)
    ink, mute, x = (34, 31, 27), (112, 104, 94), 300
    d.text((x, 214), "agentdeck", font=_sf(104, b"Semibold"), fill=ink)
    lines = (["AI 에이전트, LLM 한도, 맥 상태를", "책상 위 13개의 버튼으로."] if lang == "ko"
             else ["AI agents, LLM quotas and Mac health,", "on thirteen buttons on your desk."])
    f = _kr(40, 2)
    d.text((x + 4, 352), lines[0], font=f, fill=mute)
    d.text((x + 4, 406), lines[1], font=f, fill=mute)
    d.line([(x + 4, 492), (x + 64, 492)], fill=ink, width=3)
    meta = "Ulanzi D200  ·  macOS  ·  Claude · Codex · agy  ·  Herdr"
    d.text((x + 4, 520), meta, font=_kr(26, 4), fill=(140, 130, 118))
    bg.convert("RGB").save(os.path.join(out, "banner.png" if lang == "ko" else "banner.en.png"), optimize=True)


def studio_gif(path: str) -> None:
    """작업 현황: 결정(노랑)·완료(초록) 칸이 깜빡이는 모습."""
    (studio, meta), s = mock_studio(), screens()
    row = [w for w in studio.workspaces if w.name != TOWER][:5]
    frames = [device_mockup({**page_studio(studio, i % 2 == 0, row, meta), **nav(3, 5, 80)}, s["page3-studio"][1], 0.6)
              for i in range(2)]
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=[600, 600], loop=0, optimize=True)


def pomodoro_gif(path: str) -> None:
    """뽀모도로: 칸이 마지막부터 거꾸로 비워지는 모습."""
    frames, ms = [], []
    for frac in (1.0, 0.8, 0.6, 0.4, 0.2, 0.05):
        p = Pomodoro(state="running", duration=25 * 60, end_at=time.time() + 25 * 60 * frac)
        frames.append(device_mockup({**page_pomodoro(p, False), **nav(5, 5, 80)},
                                    render_timer(p.remaining(), "running", p.end_at), 0.6))
        ms.append(500)
    done = Pomodoro(state="done", duration=25 * 60)
    for i in range(4):  # 끝나면 체크무늬 깜빡임
        frames.append(device_mockup({**page_pomodoro(done, i % 2 == 0), **nav(5, 5, 80)},
                                    render_timer(0, "done", None), 0.6))
        ms.append(400)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=ms, loop=0, optimize=True)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "docs/images"
    os.makedirs(out, exist_ok=True)
    for lang in ("ko", "en"):  # 한국어 이미지 / 영어 이미지(.en)
        i18n.LANG = lang
        sfx = "" if lang == "ko" else ".en"
        for name, (buttons, small) in screens().items():
            if name in ("page3-studio", "page5-pomodoro"):
                continue
            device_mockup(buttons, small, 0.6).save(os.path.join(out, f"{name}{sfx}.png"))
        studio_gif(os.path.join(out, f"page3-studio{sfx}.gif"))
        pomodoro_gif(os.path.join(out, f"page5-pomodoro{sfx}.gif"))
        heatmap_gif(os.path.join(out, f"page6-heatmap{sfx}.gif"))
        game_gif(os.path.join(out, f"page7-games{sfx}.gif"))
        if lang == "ko":
            aquarium_gif(os.path.join(out, "page8-aquarium.gif"))
        banner(out, lang)
        hero_gif(out, f"hero{sfx}.gif")
    print("written to", out)
