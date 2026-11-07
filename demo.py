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
        "page6-heatmap": ({**page_market("top", mock_market()[0]), **nav(6, 6, 80, ("보기", "→ 코스닥 상위"))},
                          render_market(mock_market()[1], mock_market()[2], "코스피 상위")),
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
        banner(out, lang)
        hero_gif(out, f"hero{sfx}.gif")
    print("written to", out)
