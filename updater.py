"""새 버전 알림과 한 번에 업데이트.

하루 한 번(그리고 대시보드가 켜질 때) GitHub 에 새 커밋이 있는지 확인한다 (git fetch).
있으면 시계 칸에 "업데이트" 칩이 뜨고, 시계가 있는 페이지에서 넓은 칸을 2초 동안 누르고 있으면
git pull(빨리 감기만) → 필요하면 패키지 설치 → 대시보드를 다시 켠다 (launchd 가 자동으로 다시 실행).

내 컴퓨터에서 고친 파일과 겹치면 업데이트하지 않고 이유만 알려 준다 (내 수정은 지우지 않는다).
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
from pathlib import Path

ROOT = Path(__file__).parent
CHECK_SEC = 24 * 3600
HOLD_SEC = 2.0  # 넓은 칸을 이만큼 누르고 있으면 업데이트

_state = {"behind": 0, "subject": "", "checked": 0.0, "branch": "", "error": ""}
_lock = threading.Lock()


def _git(*args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, timeout=timeout)


def upstream() -> str:
    r = _git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    return r.stdout.strip() if r.returncode == 0 else "origin/main"


def check(force: bool = False) -> dict:
    """새 커밋 수와 가장 최근 커밋 제목. 하루 한 번만 실제로 확인."""
    with _lock:
        if not force and time.time() - _state["checked"] < CHECK_SEC:
            return dict(_state)
        _state["checked"] = time.time()
    try:
        up = upstream()
        remote, _, branch = up.partition("/")
        f = _git("fetch", "--quiet", remote, branch, timeout=60)
        if f.returncode != 0:
            raise RuntimeError(f.stderr.strip()[:80] or "fetch 실패")
        n = int(_git("rev-list", "--count", f"HEAD..{up}").stdout.strip() or 0)
        subj = _git("log", "-1", "--format=%s", up).stdout.strip() if n else ""
        with _lock:
            _state.update(behind=n, subject=subj, branch=up, error="")
    except Exception as e:
        with _lock:
            _state["error"] = str(e)[:80]
    return dict(_state)


def status() -> dict:
    with _lock:
        return dict(_state)


def start_background() -> None:
    def loop() -> None:
        time.sleep(30)  # 켜자마자 네트워크를 쓰지 않게 조금 뒤에
        while True:
            check()
            time.sleep(3600)

    threading.Thread(target=loop, daemon=True).start()


def update() -> tuple[bool, str]:
    """빨리 감기만 되는 git pull. 성공하면 (True, 요약)."""
    up = status().get("branch") or upstream()
    before = _git("rev-parse", "HEAD").stdout.strip()
    req_before = (ROOT / "requirements.txt").read_bytes() if (ROOT / "requirements.txt").exists() else b""
    r = _git("merge", "--ff-only", up, timeout=120)
    if r.returncode != 0:
        msg = (r.stderr or r.stdout).strip().splitlines()
        hint = "내 컴퓨터에서 고친 파일과 겹쳐요" if any("overwritten" in m or "local changes" in m for m in msg) else \
            (msg[-1][:60] if msg else "업데이트 실패")
        return False, hint
    req_after = (ROOT / "requirements.txt").read_bytes() if (ROOT / "requirements.txt").exists() else b""
    if req_after != req_before:  # 새 패키지가 필요하면 설치
        py = ROOT / ".venv" / "bin" / "python"
        subprocess.run([str(py), "-m", "pip", "install", "-q", "-r", str(ROOT / "requirements.txt")],
                       capture_output=True, timeout=600)
    n = _git("rev-list", "--count", f"{before}..HEAD").stdout.strip()
    with _lock:
        _state.update(behind=0, subject="")
    return True, f"{n}개 변경 반영"


def restart_soon(delay: float = 1.5) -> None:
    """잠시 뒤 프로세스를 끝낸다 → launchd(KeepAlive)가 새 코드로 다시 실행."""
    threading.Timer(delay, lambda: os._exit(0)).start()


if __name__ == "__main__":
    print(check(force=True))
