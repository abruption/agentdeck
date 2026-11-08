"""D200 LLM 한도 + 에이전트 스튜디오 현황 대시보드 (페이지 넘김).

페이지: 1 요약 / 2 한도 그리드 / 3 스튜디오(Herdr)
하단 줄: [◀ 이전][갱신 · 길게 누르면 밝기][다음 ▶] + 오른쪽 넓은 칸 시계

실행: .venv/bin/python dashboard.py
"""

from __future__ import annotations

import signal
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from clock import render_clock, render_market, render_message, render_timer, render_worktree_summary
from d200 import D200, SMALL_BACKGROUND, Button, InputEvent
from machines import MachineStat, machine_stats
from pages import (LLM, Limit, nav, nav_device, nav_worktrees, page_device, page_grid, page_machines, page_pomodoro,
                   page_market, page_studio, page_summary, page_worktrees)
import market
from aquarium import Aquarium
from games import Games
from config import CFG
from mole import MOLE_HOSTS, dryrun_info, empty_trash, mole_status, refresh_dryrun, run_clean, run_purge, trash_info
from machines import MACHINES
from worktrees import Worktree, ask_tower, open_in_herdr, remove_worktree, worktrees
from pomodoro import PRESETS, Pomodoro, notify_done
from remote_agy import agy_quota
from remote_herdr import (TOWER_SPACE, StudioState, TowerMeta, Workspace, alert_keys, apply_ack, focus,
                          studio_state, tower_meta, tower_split, unzoom_pane, zoom_pane)
from usage import claude_usage, codex_live, codex_usage

REFRESH_SEC = 30
BRIGHTNESS_STEPS = [20, 50, 80, 100]
LONG_PRESS = 0.8
W5, WEEK = timedelta(hours=5), timedelta(days=7)
PAGES = 8
GAME_PAGE = 7  # 게임: 두더지 잡기 · 순서 기억
AQUA_PAGE = 8  # 어항 (넘김 순서 마지막, 화면보호기로도 사용)
GAME_TICK = 0.05
AQUA_FPS = 5
WT_PAGE = 16  # 워크트리: 작업 현황 넓은 칸에서 들어가는 하위 페이지 (넘김 순서 밖)
DEV_PAGE = 17  # 기기 상세: 머신 페이지에서 컴퓨터를 눌러 들어가는 하위 페이지
WT_POLL_SEC = 60
ARM_SEC = 10  # 길게 한 번 누른 뒤 확인 대기 시간
MACHINE_POLL_SEC = 60
STUDIO_POLL_SEC = 5
REPEAT_WINDOW = 30  # 같은 칸 반복 누름으로 보는 시간(초)


def signature(s: StudioState) -> tuple:
    """화면에 영향을 주는 스튜디오 상태 요약 (바뀌었을 때만 다시 그리기)."""
    return (s.online, tuple((w.name, w.working, w.attention, w.done, w.idle) for w in s.workspaces))


def collect_llms(pool: ThreadPoolExecutor) -> list[LLM]:
    """Claude(로컬 statusline 스냅샷), Codex(실시간), agy(config 의 agy.host) 한도를 모은다."""
    f_codex = pool.submit(codex_live)
    f_agy = pool.submit(agy_quota)
    cu = claude_usage()
    xu = f_codex.result() or codex_usage()
    ag = f_agy.result()

    def lim(used, reset, win):
        return Limit(None if used is None else 1 - used / 100, reset, win)

    claude = LLM("CLAUDE", "#d97757",
                 five=lim(cu.five_hour.used_percent, cu.five_hour.resets_at, W5),
                 week=lim(cu.seven_day.used_percent, cu.seven_day.resets_at, WEEK))
    codex = LLM("CODEX", "#10a37f", week=lim(xu.primary.used_percent, xu.primary.resets_at, WEEK))
    if xu.secondary.used_percent is not None:
        codex.five = lim(xu.secondary.used_percent, xu.secondary.resets_at, W5)
    agy = LLM("AGY", "#7aa2f7")
    for b in ag or []:
        if b.window == "5h":
            agy.five = Limit(b.remaining, b.reset, W5)
        elif b.window == "weekly":
            agy.week = Limit(b.remaining, b.reset, WEEK)
    return [claude, codex, agy]


class LoggingPool(ThreadPoolExecutor):
    """백그라운드 작업에서 난 예외를 로그에 남긴다 (조용히 묻히지 않게)."""

    def submit(self, fn, /, *args, **kwargs):
        fut = super().submit(fn, *args, **kwargs)

        def done(f):
            if f.exception():
                print(f"{datetime.now():%H:%M:%S} task error in {getattr(fn, '__name__', fn)}: {f.exception()!r}",
                      flush=True)

        fut.add_done_callback(done)
        return fut


class Dashboard:
    def __init__(self) -> None:
        self.deck = D200()
        self.deck.on_event = self.on_event
        self.pool = LoggingPool(max_workers=8)
        self.page = 1
        self.brightness_idx = 2
        self.llms: list[LLM] = []
        self.studio = StudioState(False, [])
        self.pressed_at: dict[int, float] = {}
        self.fetch_now = threading.Event()
        self.stop = threading.Event()
        self.render_lock = threading.Lock()
        self.rendered_minute = ""
        self.blink_on = False
        self.machines: list[MachineStat] = []
        self.machines_at = 0.0
        self.raw_studio = StudioState(False, [])  # Herdr 원본 상태
        self.acked: set[tuple[str, str]] = set()  # 눌러서 확인한 알림 (터미널, 상태)
        self.last_focus: tuple[str, int, float] = ("", 0, 0.0)  # (스페이스 이름, 누른 횟수, 시각)
        self.row_names: list[str] = []  # 3페이지 가운데 줄 스튜디오 순서
        self.row_lock_until = 0.0
        self.tower_meta = TowerMeta({}, {})
        self.zoomed_pane: str | None = None  # 대시보드가 확대해 둔 총괄 pane
        self.pomo = Pomodoro.load()
        self.market_view = 0  # market.VIEWS 순서
        self.aquarium = Aquarium(int(CFG.get("aquarium_fish", 14)))  # 물고기 수 (config)
        self.aqua_thread: threading.Thread | None = None
        self.aqua_entered = 0.0
        self.games = Games()
        self.game_thread: threading.Thread | None = None
        self.game_handled: set[int] = set()  # 누를 때 이미 처리한 칸 (뗄 때 무시)
        self.saver_from: int | None = None  # 화면보호기로 들어오기 전 페이지 (None 이면 직접 들어옴)
        self.last_input = time.time()
        self.saver_sec = float(CFG.get("screensaver_min", 10)) * 60  # 0 이면 화면보호기 끔
        self.market_quotes = None
        self.market_idx: list = []
        self.market_breadth = (0, 0)
        self.wts: list[Worktree] | None = []
        self.wts_at = 0.0
        self.wt_armed: tuple[str, str, float] | None = None  # (경로, remove|ask, 만료 시각)
        self.wt_msg: tuple[str, list[str], str, float] | None = None  # (제목, 줄들, 색, 만료 시각)
        self.device_idx = 0  # 기기 상세 페이지에서 보고 있는 컴퓨터 (MACHINES 순서)
        self.mole: dict = {}  # 이름 → MoleStatus
        self.trash: dict = {}  # 이름 → (항목 수, GB)
        self.mole_at = 0.0
        self.dev_armed: tuple[str, str, float] | None = None  # (기기 이름, purge|trash, 만료)

    @property
    def brightness(self) -> int:
        return BRIGHTNESS_STEPS[self.brightness_idx]

    # ---- 입력 ----
    def on_event(self, ev: InputEvent) -> None:
        if ev.kind != "button":
            return
        if ev.action == "press":
            self.pressed_at[ev.index] = time.time()
            if self.page == GAME_PAGE and (ev.index < 10 or ev.index >= 13):  # 게임은 누르는 순간 처리
                self.last_input = time.time()
                self.game_handled.add(ev.index)
                self.games.press(ev.index)
                self.ensure_game_loop()
                self.render_game()
            return
        if ev.action != "release":
            return
        held = time.time() - self.pressed_at.pop(ev.index, time.time())
        self.last_input = time.time()
        if ev.index in self.game_handled:
            self.game_handled.discard(ev.index)
            return
        if self.page == GAME_PAGE and ev.index in (10, 12):
            self.games.menu()  # 페이지를 떠나면 게임은 메뉴로
        if self.page == GAME_PAGE and ev.index == 11 and held < LONG_PRESS and self.games.mode != "menu":
            self.games.menu()  # 게임 중 가운데 짧게 = 메뉴로
            self.render()
            return
        if self.page == AQUA_PAGE:  # 어항: 짧게 = 먹이, 길게 = 나가기
            if held >= LONG_PRESS:
                self.leave_aquarium()
            else:
                self.aquarium.feed(ev.index if ev.index < 13 else 13)
            return
        if self.page == DEV_PAGE and ev.index in (10, 12):  # 기기 상세 → 뒤로(머신) / 다음 기기
            if ev.index == 10:
                self.page = 4
            else:
                self.open_device((self.device_idx + 1) % len(MACHINES))
                return
            self.render()
        elif self.page == DEV_PAGE and ev.index < 10:
            self.on_device_press(ev.index, held)
        elif self.page == 4 and ev.index < 10 and ev.index % 5 < 4:  # 머신 페이지 컴퓨터 칸 → 기기 상세
            self.open_device(ev.index % 5)
        elif self.page == WT_PAGE and ev.index in (10, 12):  # 워크트리 → 뒤로(작업 현황) / 다음(머신)
            self.page = 3 if ev.index == 10 else 4
            self.render()
        elif ev.index == 10:
            self.page = PAGES if self.page == 1 else self.page - 1
            if self.page == AQUA_PAGE:
                self.enter_aquarium(saver=False)
                return
            self.render()
            if self.page == 6:
                self.pool.submit(self.refresh_market)
        elif ev.index == 12:
            self.page = 1 if self.page == PAGES else self.page + 1
            if self.page == AQUA_PAGE:
                self.enter_aquarium(saver=False)
                return
            self.render()
            if self.page == 6:
                self.pool.submit(self.refresh_market)
        elif self.page == 3 and ev.index >= 13:  # 작업 현황의 넓은 칸 = 워크트리 버튼
            self.page = WT_PAGE
            self.render()
            self.pool.submit(self.refresh_worktrees)
        elif self.page == WT_PAGE and ev.index < 10:
            self.on_worktree_press(ev.index, held)
        elif self.page == 3 and ev.index < 10:
            self.on_studio_press(ev.index)
        elif self.page == 5 and (ev.index < 10 or ev.index >= 13):  # 넓은 타이머 칸(13·14)도 조작 가능
            self.on_pomodoro_press(ev.index, held)
        elif self.page == 1 and ev.index == 8 and (self.studio.attention or self.studio.done):  # 요약 스튜디오 칸: 알림 있는 곳으로
            alerts = [w for w in self.studio.workspaces if w.attention] or [w for w in self.studio.workspaces if w.done]
            self.focus_ws(alerts[0])
        elif self.page == 6 and ev.index < 10:  # 히트맵 칸: HeatTab 새 탭
            self.pool.submit(market.open_heattab)
        elif self.page == 6 and ev.index == 11 and held < LONG_PRESS:  # 히트맵: 가운데 짧게 = 보기 전환
            self.market_view = (self.market_view + 1) % len(market.VIEWS)
            self.market_quotes = None
            self.render()
            self.pool.submit(self.refresh_market)
        elif ev.index == 11:
            if held >= LONG_PRESS:  # 길게: 밝기 순환
                self.brightness_idx = (self.brightness_idx + 1) % len(BRIGHTNESS_STEPS)
                self.deck.set_brightness(self.brightness)
                self.render()
            else:  # 짧게: 즉시 갱신
                self.fetch_now.set()

    # ---- 워크트리(하위 페이지) ----
    def refresh_worktrees(self) -> None:
        self.wts = worktrees()
        self.wts_at = time.time()
        if self.page == WT_PAGE:
            self.render()

    def armed_now(self) -> tuple[str | None, str | None]:
        if self.wt_armed and time.time() < self.wt_armed[2]:
            return self.wt_armed[0], self.wt_armed[1]
        return None, None

    # ---- 기기 상세(하위 페이지) ----
    def refresh_mole(self) -> None:
        got = []
        for name, host in MOLE_HOSTS.items():
            st = mole_status(host)
            if st:
                self.mole[name] = st
                got.append(f"{name}={st.health}")
                refresh_dryrun(host)  # 정리 가능 용량: 6시간마다 백그라운드 측정 (상세 페이지를 안 열어도)
        self.mole_at = time.time()
        print(f"{datetime.now():%H:%M:%S} mole: {' '.join(got) or '응답 없음'}", flush=True)
        if self.page in (4, DEV_PAGE):
            self.render()

    def refresh_device(self) -> None:
        name = MACHINES[self.device_idx][0]
        host = MOLE_HOSTS.get(name)
        if host:
            st = mole_status(host)
            if st:
                self.mole[name] = st
            info = trash_info(host)
            if info:
                self.trash[name] = info
            refresh_dryrun(host)  # 6시간 넘었으면 백그라운드 측정
        if self.page == DEV_PAGE:
            self.render()

    def open_device(self, idx: int) -> None:
        self.device_idx, self.page, self.dev_armed = idx, DEV_PAGE, None
        self.render()
        self.pool.submit(self.refresh_device)

    def on_device_press(self, idx: int, held: float) -> None:
        name = MACHINES[self.device_idx][0]
        host = MOLE_HOSTS.get(name)
        if idx not in (7, 8, 9) or not host:
            return
        action = {7: "clean", 8: "purge", 9: "trash"}[idx]
        if held < LONG_PRESS:  # 짧게: 설명만
            dry, tr = dryrun_info(host), self.trash.get(name)
            if action == "clean":
                size = f"{dry['clean_gb']:.1f}GB" if dry.get("clean_gb") is not None else "측정 전"
                self.toast("캐시·로그 정리", [f"{name} · {size}", "앱 캐시·로그·임시 파일 (mo clean)", "길게 2번 눌러 실행"], "#ff9e64")
            elif action == "purge":
                size = f"{dry['purge_gb']:.1f}GB · {dry.get('purge_items', 0)}개" if dry.get("purge_gb") is not None else "측정 전"
                self.toast("빌드 산출물 정리", [f"{name} · {size}", "node_modules·.venv·dist 등", "길게 2번 눌러 실행"], "#ff9e64")
            else:
                size = (f"{tr[1]:.1f}GB · {tr[0]}개" if tr[0] >= 0 else f"{tr[1]:.1f}GB") if tr else "-"
                self.toast("휴지통 비우기", [f"{name} · {size}", "영구 삭제됩니다", "길게 2번 눌러 실행"], "#ff9e64")
            return
        armed = self.dev_armed if self.dev_armed and time.time() < self.dev_armed[2] else None
        if not armed or armed[:2] != (name, action):  # 길게 첫 번째: 확인 대기
            self.dev_armed = (name, action, time.time() + ARM_SEC)
            what = {"clean": "캐시·로그 정리 (mo clean)", "purge": "빌드 산출물 정리 (mo purge)",
                    "trash": "휴지통 영구 비우기"}[action]
            self.toast("확인 필요", [name, what, f"{ARM_SEC}초 안에 길게 한 번 더"], "#f7768e", ARM_SEC)
            return
        self.dev_armed = None  # 길게 두 번째: 실행
        doing = {"clean": "캐시 정리 중 (몇 분 걸릴 수 있어요)", "purge": "산출물 정리 중 (몇 분 걸릴 수 있어요)",
                 "trash": "휴지통 비우는 중"}[action]
        self.toast("실행 중…", [name, doing], "#e0af68", 900)

        def run() -> None:
            ok, msg = {"clean": run_clean, "purge": run_purge, "trash": empty_trash}[action](host)
            self.toast("완료" if ok else "실패", [name, msg], "#9ece6a" if ok else "#f7768e", 15)
            self.refresh_device()

        self.pool.submit(run)

    def toast(self, title: str, lines: list[str], color: str = "#bb9af7", sec: float = 8) -> None:
        self.wt_msg = (title, lines, color, time.time() + sec)
        self.render()

    def on_worktree_press(self, idx: int, held: float) -> None:
        items = self.wts or []
        if idx >= len(items):
            return
        w = items[idx]
        if held < LONG_PRESS:  # 짧게: Herdr 에서 열기
            self.wt_armed = None
            tower = next((x for x in self.raw_studio.workspaces if x.name == TOWER_SPACE), None)
            self.pool.submit(open_in_herdr, w, tower.space_id if tower else None)
            return
        action = "remove" if w.can_remove else "ask"
        path, armed_action = self.armed_now()
        if path != w.path:  # 길게 첫 번째: 확인 대기
            self.wt_armed = (w.path, action, time.time() + ARM_SEC)
            what = "워크트리 삭제 (브랜치는 유지)" if action == "remove" else "리드 에이전트에게 정리 요청 전송"
            self.toast("확인 필요", [f"{w.repo}/{w.name}", what, f"{ARM_SEC}초 안에 길게 한 번 더"], "#f7768e", ARM_SEC)
            return
        self.wt_armed = None  # 길게 두 번째: 실행
        self.toast("실행 중…", [f"{w.repo}/{w.name}"], "#e0af68", 30)

        def run() -> None:
            ok, out = remove_worktree(w) if armed_action == "remove" else ask_tower(w)
            done = "삭제 완료" if armed_action == "remove" else "총괄에게 전송함"
            self.toast(done if ok else "실패", [f"{w.repo}/{w.name}", out[:40]] if not ok else [f"{w.repo}/{w.name}"],
                       "#9ece6a" if ok else "#f7768e")
            self.refresh_worktrees()

        self.pool.submit(run)

    # ---- 어항 (7페이지 · 화면보호기) ----
    def enter_aquarium(self, saver: bool) -> None:
        self.saver_from = self.page if saver else None
        self.page = AQUA_PAGE
        self.aqua_entered = time.time()
        if not (self.aqua_thread and self.aqua_thread.is_alive()):
            self.aqua_thread = threading.Thread(target=self.aqua_loop, daemon=True)
            self.aqua_thread.start()

    def leave_aquarium(self, to: int | None = None) -> None:
        self.page = to or self.saver_from or 1
        self.saver_from = None
        self.render()

    def aqua_loop(self) -> None:
        """어항 페이지에 있는 동안 초당 AQUA_FPS 번 화면을 다시 보낸다."""
        while self.page == AQUA_PAGE and not self.stop.is_set():
            t0 = time.time()
            self.aquarium.step(1 / AQUA_FPS)
            self.render()
            time.sleep(max(0.0, 1 / AQUA_FPS - (time.time() - t0)))

    # ---- 게임 (7페이지) ----
    def ensure_game_loop(self) -> None:
        if not (self.game_thread and self.game_thread.is_alive()):
            self.game_thread = threading.Thread(target=self.game_loop, daemon=True)
            self.game_thread.start()

    def game_loop(self) -> None:
        """게임 중에는 짧은 간격으로 시간을 진행하고, 화면이 바뀔 때만 다시 보낸다."""
        last = None
        while self.page == GAME_PAGE and self.games.active and not self.stop.is_set():
            self.games.tick()
            key = (tuple(self.games.tiles().items()), self.games.wide_key())
            if key != last:
                last = key
                self.render_game()
            time.sleep(GAME_TICK)
        if self.page == GAME_PAGE:
            self.render_game()  # 끝 화면

    def render_game(self) -> None:
        with self.render_lock:
            try:
                body = {i: Button(image=p) for i, p in self.games.tiles().items()}
                middle = ("메뉴", "게임 그만") if self.games.mode != "menu" else None
                self.deck.set_buttons({**body, **nav(GAME_PAGE, PAGES, self.brightness, middle)},
                                      small_png=self.games.wide())
            except Exception as e:
                print(f"{datetime.now():%H:%M:%S} game render error: {e}", flush=True)

    # ---- 주식 히트맵(6페이지) ----
    def refresh_market(self) -> None:
        if not market.MARKET_ENABLED:
            return
        view = market.VIEWS[self.market_view]
        self.market_quotes = market.view_data(view)
        self.market_idx = market.indices()
        self.market_breadth = market.breadth()
        if self.page == 6:
            self.render()

    # ---- 뽀모도로(5페이지) ----
    def on_pomodoro_press(self, idx: int, held: float) -> None:
        if self.pomo.state == "setup":
            if idx < len(PRESETS):
                self.pomo.start(PRESETS[idx])
        elif self.pomo.state == "done":
            self.pomo.reset()
        elif self.pomo.state == "paused" and idx == 9:  # 일시정지 화면의 '취소' 칸
            self.pomo.reset()
        elif held >= LONG_PRESS:  # 길게: 취소 (장치가 지원하면)
            self.pomo.reset()
        else:  # 짧게: 일시정지/재개
            self.pomo.toggle_pause()
        self.render()

    # ---- 작업 현황(3페이지) ----
    def raw_tower(self) -> Workspace | None:
        return next((w for w in self.raw_studio.workspaces if w.name == TOWER_SPACE), None)

    def studio_row(self) -> list[Workspace]:
        """가운데 줄 5칸: 결정 > 완료 > 작업 중 > 창 순서. 최근 누른 뒤 30초 동안은 위치 고정."""
        others = [w for w in self.studio.workspaces if w.name != TOWER_SPACE]
        size = 5 if any(w.name == TOWER_SPACE for w in self.studio.workspaces) else 10
        if time.time() < self.row_lock_until and self.row_names:
            by_name = {w.name: w for w in others}
            row = [by_name[n] for n in self.row_names if n in by_name]
            return row + [w for w in others if w.name not in self.row_names][: size - len(row)]
        order = {w.name: i for i, w in enumerate(others)}
        row = sorted(others, key=lambda w: (-w.attention, -w.done, -w.working, order[w.name]))[:size]
        self.row_names = [w.name for w in row]
        return row

    def on_studio_press(self, idx: int) -> None:
        tower = next((w for w in self.studio.workspaces if w.name == TOWER_SPACE), None)
        if not tower:  # 리드 스페이스 없음(훅 방식): 10칸 모두 프로젝트
            row = self.studio_row()
            if idx < len(row):
                self.focus_ws(row[idx])
            return
        if idx < 4:  # 리드 탭 pane: 그 에이전트로 이동 + 알림 확인
            if not tower:
                return
            panes, _ = tower_split(tower)
            if idx < len(panes):
                m = panes[idx]
                self.acked |= {(m.term, "attention"), (m.term, "done")}
                self.set_studio(self.raw_studio)
                self.render()
                # 처음 누름: 이동 + 확대 / 같은 pane 다시 누름: 원래 배치로
                if self.zoomed_pane and self.zoomed_pane == m.pane:
                    self.pool.submit(unzoom_pane, m.pane)
                    self.zoomed_pane = None
                else:
                    self.pool.submit(zoom_pane, m.term, m.pane, self.zoomed_pane)
                    self.zoomed_pane = m.pane
        elif idx == 4:  # 기타 총괄 탭들
            raw = self.raw_tower()
            if raw:
                self.focus_ws(tower_split(raw)[1])
        else:
            row = self.studio_row()
            if idx - 5 < len(row):
                self.focus_ws(row[idx - 5])

    def focus_ws(self, ws) -> None:
        """처음 누르면 우선 대상으로, 같은 칸을 30초 안에 다시 누르면 다음 탭으로."""
        name, count, at = self.last_focus
        step = count + 1 if name == ws.name and time.time() - at < REPEAT_WINDOW else 0
        self.last_focus = (ws.name, step, time.time())
        self.row_lock_until = time.time() + REPEAT_WINDOW  # 반복 누름 동안 칸 위치 고정
        # 원본 상태 기준으로 이 스페이스 알림을 확인 처리 → 깜빡임 즉시 끄기
        raw = next((w for w in self.raw_studio.workspaces if w.name == ws.name), ws)
        self.acked |= alert_keys(raw)
        self.set_studio(self.raw_studio)
        self.render()
        self.pool.submit(focus, raw, step)

    def set_studio(self, raw: StudioState) -> None:
        """원본 상태 저장 + 이미 사라진 알림의 확인 기록 정리 + 확인한 알림 제외한 화면용 상태."""
        self.raw_studio = raw
        current = set().union(*(alert_keys(w) for w in raw.workspaces)) if raw.workspaces else set()
        self.acked &= current
        self.studio = apply_ack(raw, self.acked)

    # ---- 화면 ----
    def clock_status(self) -> list[tuple[str, str]]:
        """시계 하단 칩: 스튜디오 작업/확인 수 + 지금 여유 있는 LLM."""
        chips: list[tuple[str, str]] = []
        if self.studio.online:
            chips.append((f"작업 {self.studio.working}", "#7aa2f7"))
            chips.append((f"결정 {self.studio.attention}", "#e0af68" if self.studio.attention else "#565f89"))
            chips.append((f"완료 {self.studio.done}", "#9ece6a" if self.studio.done else "#565f89"))
        else:
            chips.append(("스튜디오 OFF", "#f7768e"))
        if self.pomo.state in ("running", "paused"):  # 타이머 진행 중이면 다른 페이지 시계에도 표시
            chips.append((f"집중 {int(self.pomo.remaining() // 60) + 1}분", "#f7768e"))
        else:
            ranked = sorted((m for m in self.llms if m.binding()), key=lambda m: m.binding().remaining, reverse=True)
            if ranked:
                chips.append((f"추천 {ranked[0].name}", "#9ece6a"))
        return chips

    def render(self) -> None:
        if self.page == GAME_PAGE:
            self.render_game()
            return
        with self.render_lock:
            now = datetime.now(timezone.utc)
            if self.page == AQUA_PAGE:
                hint = "짧게 눌러 먹이 · 길게 눌러 나가기" if time.time() - self.aqua_entered < 4 else None
                tiles, wide = self.aquarium.tiles(hint)
                try:
                    self.deck.set_buttons({i: Button(image=p) for i, p in tiles.items()}, small_png=wide)
                except Exception as e:
                    print(f"{datetime.now():%H:%M:%S} aqua render error: {e}", flush=True)
                return
            if self.page == 1:
                body = page_summary(self.llms, self.studio, now, self.blink_on)
            elif self.page == 2:
                body = page_grid(self.llms, now)
            elif self.page == 3:
                body = page_studio(self.studio, self.blink_on, self.studio_row(), self.tower_meta)
            elif self.page == 4:
                dry = {n: dryrun_info(h) for n, h in MOLE_HOSTS.items()}
                body = page_machines(self.machines, now, self.mole, dry)
            elif self.page == 5:
                body = page_pomodoro(self.pomo, self.blink_on)
            elif self.page == 6:
                body = page_market(market.VIEWS[self.market_view], self.market_quotes)
            elif self.page == DEV_PAGE:
                name, host = MACHINES[self.device_idx][0], MOLE_HOSTS.get(MACHINES[self.device_idx][0])
                m = next((x for x in self.machines if x.name == name), None)
                armed = self.dev_armed[1] if self.dev_armed and self.dev_armed[0] == name and time.time() < self.dev_armed[2] else None
                body = page_device(m, self.mole.get(name), dryrun_info(host) if host else {}, self.trash.get(name), armed) \
                    if m else {}
            else:
                body = page_worktrees(self.wts, *self.armed_now())
            try:
                if self.page == 5:
                    small = render_timer(self.pomo.remaining(), self.pomo.state,
                                         self.pomo.end_at if self.pomo.state == "running" else None)
                elif self.page == 6:
                    small = render_market(self.market_idx or market.indices(), self.market_breadth,
                                          market.VIEW_LABEL[market.VIEWS[self.market_view]])
                elif self.page == 3:  # 시계 대신 워크트리 요약 (누르면 워크트리 페이지)
                    small = render_worktree_summary(self.wts)
                elif self.page == DEV_PAGE:
                    if self.wt_msg and time.time() < self.wt_msg[3]:
                        small = render_message(*self.wt_msg[:3])
                    else:
                        name = MACHINES[self.device_idx][0]
                        lines = ["아래 오른쪽 두 칸: 길게 2번 = 실행", "짧게 = 설명"] if name in MOLE_HOSTS else ["Mole 이 설치되지 않은 기기"]
                        small = render_message(name, lines)
                elif self.page == WT_PAGE:
                    if self.wt_msg and time.time() < self.wt_msg[3]:
                        small = render_message(*self.wt_msg[:3])
                    else:
                        small = render_message("워크트리", ["짧게: Herdr 에서 열기",
                                                         "길게 2번: 정리 가능 → 삭제",
                                                         "길게 2번: 그 외 → 총괄에 정리 요청"])
                else:
                    small = render_clock(status=self.clock_status())
                if self.page == WT_PAGE:
                    navs = nav_worktrees(self.brightness)
                elif self.page == DEV_PAGE:
                    navs = nav_device(self.brightness)
                elif self.page == 6:
                    nxt = market.VIEW_LABEL[market.VIEWS[(self.market_view + 1) % len(market.VIEWS)]]
                    navs = nav(self.page, PAGES, self.brightness, ("보기", f"→ {nxt}"))
                else:
                    navs = nav(self.page, PAGES, self.brightness)
                self.deck.set_buttons({**body, **navs}, small_png=small)
                self.rendered_minute = datetime.now().strftime("%H:%M")
            except Exception as e:
                print(f"{datetime.now():%H:%M:%S} render error: {e}", flush=True)

    def fetch(self) -> None:
        try:
            if time.time() - self.machines_at >= MACHINE_POLL_SEC or self.page == 4:
                self.machines = machine_stats(self.pool)
                self.machines_at = time.time()
            if time.time() - self.wts_at >= WT_POLL_SEC:
                self.pool.submit(self.refresh_worktrees)
            if self.page == 6:
                self.pool.submit(self.refresh_market)
            if self.page == DEV_PAGE:
                self.machines = machine_stats(self.pool)
                self.pool.submit(self.refresh_device)
            elif time.time() - self.mole_at >= MACHINE_POLL_SEC:
                self.pool.submit(self.refresh_mole)
            f_studio = self.pool.submit(studio_state)
            f_meta = self.pool.submit(tower_meta)  # 60초 캐시
            self.llms = collect_llms(self.pool)
            self.set_studio(f_studio.result())
            self.tower_meta = f_meta.result()
        except Exception as e:  # 수집 실패해도 데몬은 계속
            print(f"{datetime.now():%H:%M:%S} fetch error: {e}", flush=True)

    def run(self) -> None:
        self.deck.start()
        self.deck.set_brightness(self.brightness)
        self.deck.set_small_window(mode=SMALL_BACKGROUND)  # 넓은 칸 = 커스텀 시계 이미지
        print("D200 대시보드 시작 (Ctrl+C 종료)", flush=True)
        while not self.stop.is_set() and not self.deck.disconnected.is_set():
            self.fetch()
            self.render()
            # 1초 단위: 끊김 감지, 결정 필요 칸 깜빡임, 스튜디오 5초 폴링, 분 바뀌면 시계 갱신
            for sec in range(REFRESH_SEC):
                if self.fetch_now.wait(1) or self.stop.is_set() or self.deck.disconnected.is_set():
                    break
                dirty = False
                if sec % STUDIO_POLL_SEC == STUDIO_POLL_SEC - 1:
                    new = studio_state()
                    if signature(new) != signature(self.raw_studio):
                        self.set_studio(new)
                        dirty = True
                if self.pomo.check_finished():  # 타이머 끝: 알림 + 5페이지로
                    notify_done(self.pomo.duration / 60)
                    self.page, dirty = 5, True
                if self.page == 5 and self.pomo.state == "running":
                    dirty = True  # 매초 남은 시간·칸 갱신
                if (self.page == 5 and self.pomo.state == "done") or \
                        ((self.studio.attention or self.studio.done) and self.page in (1, 3)):
                    self.blink_on, dirty = not self.blink_on, True
                elif self.blink_on:
                    self.blink_on, dirty = False, True
                # 화면보호기: 오래 입력이 없으면 어항, 알림이 생기면 빠져나오기
                alert = self.studio.attention or self.studio.done or self.pomo.state == "done"
                if self.page == AQUA_PAGE:
                    if alert and self.saver_from is not None:
                        self.leave_aquarium(5 if self.pomo.state == "done" else 3)
                    continue
                if self.page == GAME_PAGE and self.games.active:
                    continue  # 게임 중엔 화면보호기·주기 갱신 없음
                if self.saver_sec and not alert and time.time() - self.last_input > self.saver_sec:
                    self.enter_aquarium(saver=True)
                    continue
                # 워크트리: 확인 대기·결과 메시지가 만료되면 원래 화면으로
                if self.wt_armed and time.time() >= self.wt_armed[2]:
                    self.wt_armed, dirty = None, dirty or self.page == WT_PAGE
                if self.dev_armed and time.time() >= self.dev_armed[2]:
                    self.dev_armed, dirty = None, dirty or self.page == DEV_PAGE
                if self.wt_msg and time.time() >= self.wt_msg[3]:
                    self.wt_msg, dirty = None, dirty or self.page in (WT_PAGE, DEV_PAGE)
                if dirty or datetime.now().strftime("%H:%M") != self.rendered_minute:
                    self.render()
            self.fetch_now.clear()
        self.deck.close()
        if self.deck.disconnected.is_set():
            print(f"{datetime.now():%H:%M:%S} 장치 연결 끊김, 종료", flush=True)
            raise SystemExit(1)  # launchd KeepAlive 가 재시작


def main() -> None:
    try:
        dash = Dashboard()
    except RuntimeError as e:  # 장치 미연결: launchd 가 잠시 후 다시 시도
        print(f"{datetime.now():%H:%M:%S} {e}", flush=True)
        raise SystemExit(1)

    def _quit(*_):
        dash.stop.set()
        dash.fetch_now.set()

    signal.signal(signal.SIGINT, _quit)
    signal.signal(signal.SIGTERM, _quit)
    dash.run()


if __name__ == "__main__":
    main()
