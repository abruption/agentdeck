"""Herdr 워크스페이스(스페이스)/에이전트 현황과 창 이동.

1순위: 이 맥의 Herdr 창 (`herdr-app ls`) 중 config 의 studio.host 머신 스페이스
2순위: studio.host 에 SSH 로 `herdr-core ls --json` (Herdr 창이 닫혀 있을 때)

에이전트 상태: idle / working / done / blocked(권한·질문·인증 대기) / error
→ blocked·error : '결정 필요(attention)'
→ done          : '완료 알림' (작업을 끝냈지만 아직 안 봄. Herdr 창에서 보면 idle 로 바뀜)
알림(깜빡임)은 최상위 에이전트만: 사람이 연 탭의 에이전트 (이름 없음 + 다른 에이전트의 sub_agents 아님).
총괄이 띄운 하위 작업자(이름 있음, parent 있음, sub_agents 에 포함)는 작업 중 개수에만 반영한다.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections import OrderedDict
from dataclasses import dataclass, field, replace

from config import AGENT_SOURCE, HOOK_HOSTS, STUDIO_ENABLED, STUDIO_HOST, TOWER_MAIN_TAB as _TAB, TOWER_SPACE as _SPACE

HOST = STUDIO_HOST  # Herdr 에이전트가 도는 컴퓨터 (config.json studio.host)
HERDR_APP = os.path.expanduser("~/.local/bin/herdr-app")
REMOTE_CMD = "export PATH=$HOME/.local/bin:/opt/homebrew/bin:$PATH; herdr-core ls --json"
AGENTS = {"claude-code": "C", "codex": "X", "antigravity": "A"}
ATTENTION = {"blocked", "error"}
TOWER_SPACE = _SPACE  # 총괄(리드) 에이전트들이 모인 스페이스 이름
TOWER_MAIN_TAB = _TAB  # 그 스페이스에서 리드 pane 들이 있는 탭 이름


@dataclass
class Member:
    """스페이스 안의 에이전트 하나."""

    term: str
    tab: str | None
    app: str | None
    status: str | None
    top: bool
    subs: list[str] = field(default_factory=list)  # Herdr 창이 알려준 하위 에이전트 id
    pane: str | None = None  # Herdr 창의 pane id (확대용)


@dataclass
class Workspace:
    name: str
    space_id: str | None = None  # Herdr 창의 스페이스 id (창 이동용)
    working: int = 0
    attention: int = 0
    done: int = 0  # 완료 알림 (아직 안 본 완료)
    idle: int = 0
    agents: dict[str, int] = field(default_factory=dict)  # C/X/A 별 개수
    attention_terms: list[str] = field(default_factory=list)
    working_terms: list[str] = field(default_factory=list)
    done_terms: list[str] = field(default_factory=list)
    tabs: list[str] = field(default_factory=list)  # 탭 id (창 순서), 같은 칸 반복 누름 시 순환
    term_tab: dict[str, str] = field(default_factory=dict)  # 터미널 -> 탭 id
    tab_names: dict[str, str] = field(default_factory=dict)  # 탭 id -> 이름
    members: list[Member] = field(default_factory=list)

    def state_of(self, term: str) -> str:
        """확인(ack) 반영된 표시 상태: attention / done / working / idle."""
        if term in self.attention_terms:
            return "attention"
        if term in self.done_terms:
            return "done"
        m = next((x for x in self.members if x.term == term), None)
        return "working" if m and m.status == "working" else "idle"

    @property
    def total(self) -> int:
        return sum(self.agents.values())

    @property
    def focus_target(self) -> str | None:
        """눌렀을 때 보여줄 터미널: 결정 필요 > 완료 알림 > 작업 중."""
        return (self.attention_terms or self.done_terms or self.working_terms or [None])[0]

    def add(self, term: str, app: str | None, status: str | None, top: bool = True,
            subs: list[str] | None = None, pane: str | None = None) -> None:
        kind = AGENTS.get(app or "")
        if not kind:
            return  # 셸·보조 프로세스 제외
        self.members.append(Member(term, self.term_tab.get(term), app, status, top, list(subs or []), pane))
        self.agents[kind] = self.agents.get(kind, 0) + 1
        if not top:  # 하위 작업자: 알림 없이 작업 중 여부만
            if status == "working":
                self.working += 1
            else:
                self.idle += 1
            return
        if status in ATTENTION:
            self.attention += 1
            self.attention_terms.append(term)
        elif status == "working":
            self.working += 1
            self.working_terms.append(term)
        elif status == "done":
            self.done += 1
            self.done_terms.append(term)
        else:
            self.idle += 1


@dataclass
class StudioState:
    online: bool
    workspaces: list[Workspace]
    source: str = ""

    @property
    def working(self) -> int:
        return sum(w.working for w in self.workspaces)

    @property
    def attention(self) -> int:
        return sum(w.attention for w in self.workspaces)

    @property
    def done(self) -> int:
        return sum(w.done for w in self.workspaces)


def _sorted(groups) -> list[Workspace]:
    # 칸 위치가 바뀌지 않도록 Herdr 창의 스페이스 순서를 유지한다 (같은 칸 반복 누름 = 탭 순환)
    return [w for w in groups if w.total]


def _from_app() -> StudioState | None:
    try:
        r = subprocess.run([HERDR_APP, "ls"], capture_output=True, text=True, timeout=10)
        spaces = json.loads(r.stdout)["spaces"]
    except Exception:
        return None
    subs = {sid for s in spaces for tab in s.get("tabs", []) for t in tab.get("terminals", [])
            for sid in (t.get("sub_agents") or [])}
    groups = []
    for s in spaces:
        if s.get("machine") != HOST:  # studio.host 머신의 스페이스만
            continue
        ws = Workspace(s.get("name") or "?", space_id=s.get("id"))
        for tab in s.get("tabs", []):
            if tab.get("id"):
                ws.tabs.append(tab["id"])
                ws.tab_names[tab["id"]] = tab.get("name") or ""
            # sub_agents 는 상태 없는 id 목록(보조 프로세스)이라 제외
            for t in tab.get("terminals", []):
                term = t.get("terminal", "")
                ws.term_tab[term] = tab.get("id")
                ws.add(term, t.get("app"), t.get("status"), top=not t.get("name") and term not in subs,
                       subs=t.get("sub_agents"), pane=t.get("pane"))
        groups.append(ws)
    return StudioState(True, _sorted(groups), "app")


def _from_ssh() -> StudioState:
    try:
        r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", HOST, REMOTE_CMD],
                           capture_output=True, text=True, timeout=20)
        terms = json.loads(r.stdout).get("terminals", [])
    except Exception:
        return StudioState(False, [], "ssh")
    groups: OrderedDict[str, Workspace] = OrderedDict()
    for t in terms:
        name = (t.get("where") or "?").split(" / ")[0].strip()
        groups.setdefault(name, Workspace(name)).add(f"{HOST}/{t.get('address')}", t.get("agent"), t.get("status"),
                                                     top=not t.get("name") and not t.get("parent"))
    return StudioState(True, _sorted(groups.values()), "ssh")


def studio_state() -> StudioState:
    if AGENT_SOURCE == "hooks":  # IDE·터미널 상관없이 훅으로 모은 세션
        import hook_agents

        return hook_agents.state(HOOK_HOSTS)
    if not STUDIO_ENABLED:
        return StudioState(False, [], "disabled")
    return _from_app() or _from_ssh()


def alert_keys(ws: Workspace) -> set[tuple[str, str]]:
    """이 스페이스의 현재 알림들 (터미널, 상태)."""
    return {(t, "attention") for t in ws.attention_terms} | {(t, "done") for t in ws.done_terms}


def apply_ack(state: StudioState, acked: set[tuple[str, str]]) -> StudioState:
    """눌러서 확인한 알림은 깜빡이지 않도록 대기(idle)로 취급한 사본을 만든다.

    같은 터미널이라도 상태가 바뀌어 새 알림이 생기면 (터미널, 상태) 키가 달라 다시 깜빡인다.
    """
    out = []
    for w in state.workspaces:
        att = [t for t in w.attention_terms if (t, "attention") not in acked]
        done = [t for t in w.done_terms if (t, "done") not in acked]
        moved = (w.attention - len(att)) + (w.done - len(done))
        out.append(replace(w, attention=len(att), attention_terms=att, done=len(done), done_terms=done,
                           idle=w.idle + moved))
    return StudioState(state.online, _sorted(out), state.source)


def tower_split(ws: Workspace) -> tuple[list[Member], Workspace]:
    """리드 스페이스를 (리드 탭의 최상위 pane 들, 나머지 탭을 묶은 '기타 총괄' 스페이스) 로 나눈다.

    상태 정보가 없는 pane(status None)은 제외한다. 알림 확인(ack)은 ws 의 목록을 그대로 따른다.
    """
    main = next((tid for tid, n in ws.tab_names.items() if n == TOWER_MAIN_TAB), ws.tabs[0] if ws.tabs else None)
    panes = [m for m in ws.members if m.tab == main and m.top and m.status]
    rest = Workspace("기타 총괄", space_id=ws.space_id,
                     tabs=[t for t in ws.tabs if t != main],
                     tab_names={t: n for t, n in ws.tab_names.items() if t != main})
    for m in ws.members:
        if m.tab == main:
            continue
        rest.term_tab[m.term] = m.tab
        rest.add(m.term, m.app, m.status, m.top, m.subs, m.pane)
    # 원본(ws)에서 확인 처리된 알림은 여기서도 제외
    rest.attention_terms = [t for t in rest.attention_terms if t in ws.attention_terms]
    rest.done_terms = [t for t in rest.done_terms if t in ws.done_terms]
    rest.attention, rest.done = len(rest.attention_terms), len(rest.done_terms)
    return panes, rest


def _do(*args: str) -> bool:
    try:
        r = subprocess.run([HERDR_APP, "do", *args], capture_output=True, text=True, timeout=10)
        return '"ok": true' in r.stdout
    except Exception:
        return False


# ---------- 총괄 pane 이름 + 하위 에이전트 (studio.host 의 herdr-core, SSH) ----------
TOWER_META_SCRIPT = r'''
import json, os, subprocess
env = dict(os.environ, PATH=os.path.expanduser("~/.local/bin") + ":" + os.environ.get("PATH", ""))
def hc(*a):
    return json.loads(subprocess.run(["herdr-core", *a], capture_output=True, text=True, env=env).stdout)
terms = hc("ls", "--json")["terminals"]
names = {}
for t in terms:
    if (t.get("where") or "").startswith("%s /"):
        g = hc("get", t["address"], "--json")
        labels = g.get("labels") or {}
        names[t["address"]] = labels.get("ovis.pane") or g.get("title") or ""
print(json.dumps({"names": names, "terms": [{k: t.get(k) for k in ("address", "agent", "parent", "status", "name")}
                                             for t in terms]}))
''' % TOWER_SPACE

_meta_cache: tuple[float, dict] = (0.0, {})


@dataclass
class TowerMeta:
    names: dict[str, str]  # "<host>/t12" -> pane 이름 (ovis.pane 라벨)
    children: dict[str, list[tuple[str, str | None]]]  # pane -> [(종류 C/X/A/기타, 상태)]


def tower_meta(ttl: float = 60.0) -> TowerMeta:
    """총괄 pane 이름(ovis.pane 라벨)과 pane 별 하위 에이전트. ttl 초 동안 캐시."""
    global _meta_cache
    if not STUDIO_ENABLED:
        return TowerMeta({}, {})
    import time as _t

    at, d = _meta_cache
    if _t.time() - at > ttl:
        try:
            r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", HOST, "python3", "-"],
                               input=TOWER_META_SCRIPT, capture_output=True, text=True, timeout=30)
            d = json.loads(r.stdout)
            _meta_cache = (_t.time(), d)
        except Exception:
            pass
    pre = HOST + "/"
    names = {pre + k: v for k, v in (d.get("names") or {}).items()}
    by_addr = {pre + t["address"]: t for t in d.get("terms") or []}
    children: dict[str, list] = {}
    for addr, t in by_addr.items():
        if t.get("parent"):
            children.setdefault(pre + t["parent"], []).append(addr)
    out = {k: [(AGENTS.get(by_addr[c].get("agent") or "", "기타"), (by_addr[c].get("status"))) for c in v
               if c in by_addr] for k, v in children.items()}
    return TowerMeta(names, out)


def child_kinds(meta: TowerMeta, m: Member) -> list[tuple[str, str | None]]:
    """pane 의 하위 에이전트 [(종류, 상태)]: parent 로 연결된 것 + Herdr 창 sub_agents 중 종류를 모르는 것('기타')."""
    kinds = list(meta.children.get(m.term, []))
    extra = max(0, len(set(m.subs)) - len(kinds))
    return kinds + [("기타", None)] * extra


def focus_terminal(term: str) -> bool:
    """특정 에이전트(pane)를 보여주고 Herdr 창을 앞으로."""
    ok = _do("agent.focus", "--terminal", term)
    subprocess.run(["open", "-a", "Herdr"], timeout=10)
    return ok


def zoom_pane(term: str, pane: str | None, unzoom: str | None = None) -> bool:
    """unzoom(이전에 확대한 pane)을 먼저 원래대로 돌린 뒤, term 으로 이동해 그 pane 만 크게 보여준다.

    pane.zoom 은 토글이라 확대 여부는 호출 측(대시보드)이 기억한다.
    """
    if unzoom:
        _do("pane.zoom", "--pane", unzoom)
    ok = _do("agent.focus", "--terminal", term)
    if pane:
        ok = _do("pane.zoom", "--pane", pane) and ok
    subprocess.run(["open", "-a", "Herdr"], timeout=10)
    return ok


def unzoom_pane(pane: str) -> bool:
    """확대한 pane 을 원래 배치로 (Herdr 창도 앞으로)."""
    ok = _do("pane.zoom", "--pane", pane)
    subprocess.run(["open", "-a", "Herdr"], timeout=10)
    return ok


def tab_cycle(ws: Workspace) -> list[str]:
    """반복 누름 순서: 우선 대상(결정 필요 > 작업 중)이 있는 탭부터, 이후 창의 탭 순서대로."""
    first = ws.term_tab.get(ws.focus_target or "")
    if first in ws.tabs:
        i = ws.tabs.index(first)
        return ws.tabs[i:] + ws.tabs[:i]
    return list(ws.tabs)


def focus(ws: Workspace, step: int = 0) -> bool:
    """Herdr 창을 앞으로 가져오고 해당 스페이스를 보여준다.

    step 0: 우선 대상 에이전트(결정 필요 > 작업 중), 없으면 스페이스
    step n: 같은 칸을 n 번 더 누름 → 스페이스의 탭을 순서대로 순환
    """
    if AGENT_SOURCE == "hooks":
        import hook_agents

        return hook_agents.focus(ws, step)
    order = tab_cycle(ws)
    if step == 0 and ws.focus_target:
        ok = _do("agent.focus", "--terminal", ws.focus_target)
    elif order:
        ok = (_do("space.select", "--id", ws.space_id) if ws.space_id else True) and \
            _do("tab.select", "--id", order[step % len(order)])
    elif ws.space_id:
        ok = _do("space.select", "--id", ws.space_id)
    else:
        return False
    subprocess.run(["open", "-a", "Herdr"], timeout=10)
    return ok


if __name__ == "__main__":
    s = studio_state()
    print("source:", s.source, "online:", s.online, "working:", s.working, "attention:", s.attention)
    for w in s.workspaces:
        print(f"  {w.name}: 작업 {w.working} 결정 {w.attention} 완료알림 {w.done} 대기 {w.idle} {w.agents} -> {w.focus_target or w.space_id}")
