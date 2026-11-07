"""Mole(tw93/Mole, `mo`) 연동 — config.json 에서 mole: true 인 컴퓨터.

보기
  mo status --json        : 건강 점수, 휴지통 용량, CPU 상위 프로세스, 장시간 CPU 과다 경고
  mo purge --dry-run      : 정리 가능한 빌드 산출물 용량 (약 1분) ┐ 6시간 캐시,
  mo clean --dry-run      : 정리 가능한 캐시·로그 용량 (약 2분)   ┘ 기기 상세 페이지를 열 때 오래됐으면 다시 측정
실행 (대시보드에서 길게 두 번 눌러 확인)
  mo purge --yes          : 빌드 산출물 정리
  휴지통 비우기            : ~/.Trash 안의 항목 영구 삭제
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field

from config import MACHINES_CFG

# 컴퓨터 표시 이름 → ssh 대상 ("local" = 이 맥). config.json 에서 mole: true 인 컴퓨터만
MOLE_HOSTS = {m["name"]: (m.get("ssh") or "local") for m in MACHINES_CFG if m.get("mole")}
CACHE_PATH = os.path.expanduser("~/.cache/d200/mole_dryrun.json")
DRYRUN_TTL = 6 * 3600
PATH_PREFIX = "export PATH=/opt/homebrew/bin:$HOME/.local/bin:$PATH; "
ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")


def _ssh(host: str, cmd: str, timeout: int = 60) -> subprocess.CompletedProcess:
    if host == "local":
        return subprocess.run(["bash", "-c", PATH_PREFIX + cmd], capture_output=True, text=True, timeout=timeout)
    return subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", host, PATH_PREFIX + cmd],
                          capture_output=True, text=True, timeout=timeout)


def _size_gb(text: str) -> float | None:
    m = re.match(r"\s*([\d.]+)\s*(TB|GB|MB|KB|B)", text)
    if not m:
        return None
    return float(m.group(1)) * {"TB": 1024, "GB": 1, "MB": 1 / 1024, "KB": 1 / 1024**2, "B": 1 / 1024**3}[m.group(2)]


@dataclass
class MoleStatus:
    health: int
    health_msg: str
    trash_gb: float
    top: list[tuple[str, float]] = field(default_factory=list)  # (프로세스, CPU%)
    alerts: list[str] = field(default_factory=list)  # 장시간 CPU 과다 프로세스


def mole_status(host: str) -> MoleStatus | None:
    try:
        d = json.loads(_ssh(host, "mo status --json 2>/dev/null", 30).stdout)
    except Exception:
        return None
    alerts = []
    for a in d.get("process_alerts") or []:
        name = a.get("name") or a.get("command") or "?"
        alerts.append(f"{name} {a.get('cpu', '')}%".strip())
    return MoleStatus(
        health=int(d.get("health_score") or 0),
        health_msg=d.get("health_score_msg") or "",
        trash_gb=(d.get("trash_size") or 0) / 1024**3,
        top=[(p.get("name", "?"), float(p.get("cpu") or 0)) for p in (d.get("top_processes") or [])[:3]],
        alerts=alerts,
    )


# ---------- dry-run (느림, 캐시) ----------
_lock = threading.Lock()
_running: set[str] = set()


def _load() -> dict:
    try:
        return json.load(open(CACHE_PATH))
    except Exception:
        return {}


def dryrun_info(host: str) -> dict:
    """{purge_gb, purge_items, clean_gb, at} 중 측정된 것. 측정 중이면 measuring=True."""
    info = dict(_load().get(host, {}))
    info["measuring"] = host in _running
    return info


def refresh_dryrun(host: str, force: bool = False) -> None:
    """오래됐으면(또는 force) 백그라운드에서 purge·clean dry-run 측정. 이미 측정 중이면 무시."""
    info = _load().get(host, {})
    if not force and time.time() - info.get("at", 0) < DRYRUN_TTL:
        return
    with _lock:
        if host in _running:
            return
        _running.add(host)

    def work() -> None:
        try:
            res: dict = {}
            out = ANSI.sub("", _ssh(host, "mo purge --dry-run 2>&1 | tail -5", 300).stdout)
            m = re.search(r"Would free:\s*([\d.]+\s*[KMGT]?B)\s*\|\s*Items:\s*(\d+)", out)
            if m:
                res["purge_gb"], res["purge_items"] = _size_gb(m.group(1)), int(m.group(2))
            elif "nothing" in out.lower() or "no " in out.lower():
                res["purge_gb"], res["purge_items"] = 0.0, 0
            out = ANSI.sub("", _ssh(host, "mo clean --dry-run 2>&1 | tail -8", 400).stdout)
            m = re.search(r"Potential space:\s*([\d.]+\s*[KMGT]?B)", out)
            if m:
                res["clean_gb"] = _size_gb(m.group(1))
            res["at"] = time.time()
            with _lock:
                data = _load()
                data[host] = {**data.get(host, {}), **res}
                os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
                json.dump(data, open(CACHE_PATH, "w"))
        finally:
            with _lock:
                _running.discard(host)

    threading.Thread(target=work, daemon=True).start()


# ---------- 실행 ----------
def run_purge(host: str) -> tuple[bool, str]:
    r = _ssh(host, "mo purge --yes 2>&1 | tail -6", 900)
    out = ANSI.sub("", r.stdout)
    m = re.search(r"(Freed|Would free|free[d]?):?\s*([\d.]+\s*[KMGT]?B)", out, re.I)
    msg = f"{m.group(2)} 확보" if m else (out.strip().splitlines() or [""])[-1][:60]
    refresh_dryrun(host, force=True)
    return r.returncode == 0, msg


def trash_info(host: str) -> tuple[int, float] | None:
    """(항목 수, GB). 휴지통 폴더 접근이 막혀 있으면(로컬 맥의 전체 디스크 접근 제한) Mole 값으로 대체, 항목 수 -1."""
    r = _ssh(host, "ls -A ~/.Trash | grep -v '^.DS_Store$' | wc -l; du -sk ~/.Trash | cut -f1", 60)
    try:
        if "not permitted" in r.stderr:
            raise PermissionError
        n, kb = r.stdout.split()
        return int(n), int(kb) / 1024**2
    except Exception:
        st = mole_status(host)
        return (-1, st.trash_gb) if st else None


def empty_trash(host: str) -> tuple[bool, str]:
    before = trash_info(host)
    if host == "local":  # 이 맥: 휴지통 폴더 직접 접근이 막혀 Finder 에 요청 (처음 한 번 제어 허용 필요)
        r = subprocess.run(["osascript", "-e", 'tell application "Finder" to empty trash'],
                           capture_output=True, text=True, timeout=600)
    else:
        r = _ssh(host, "find ~/.Trash -mindepth 1 -maxdepth 1 ! -name .DS_Store -exec rm -rf {} +", 600)
    after = trash_info(host)
    if r.returncode != 0:
        return False, (r.stderr.strip() or "삭제 실패")[:60]
    freed = (before[1] - after[1]) if before and after else 0
    return True, f"{freed:.1f}GB 비움" if freed >= 0.1 else "비움 완료"


if __name__ == "__main__":
    for name, host in MOLE_HOSTS.items():
        print(name, mole_status(host), dryrun_info(host), trash_info(host))
