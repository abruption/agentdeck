"""agy(Antigravity CLI)를 쓰는 컴퓨터에서 할당량을 SSH 로 가져온다.

원격에는 아무것도 설치하지 않는다: 아래 REMOTE 스크립트를 ssh stdin 으로 넘겨 실행한다.
토큰이 만료됐으면 `agy models` 를 한 번 실행해 agy 가 토큰을 갱신하게 한 뒤 재시도한다.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime

from config import AGY_HOST

HOST = AGY_HOST  # agy 를 쓰는 컴퓨터의 ssh 대상 (config.json agy.host), 없으면 비활성

REMOTE = r'''
import json, os, subprocess
P = os.path.expanduser("~/.gemini/antigravity-cli/antigravity-oauth-token")
URL = "https://daily-cloudcode-pa.googleapis.com/v1internal:retrieveUserQuotaSummary"
def curl():
    tok = json.load(open(P))["token"]["access_token"]
    out = subprocess.run(["curl", "-s", "-m", "10", "-X", "POST", URL, "-H", "Authorization: Bearer " + tok,
        "-H", "Content-Type: application/json", "-H", "User-Agent: antigravity", "-d", "{}"],
        capture_output=True, text=True).stdout
    d = json.loads(out)
    if "error" in d:
        raise RuntimeError(d["error"].get("status", "error"))
    return d
try:
    d = curl()
except Exception:
    env = dict(os.environ, PATH=os.path.expanduser("~/.local/bin") + ":/opt/homebrew/bin:" + os.environ.get("PATH", ""))
    subprocess.run(["agy", "models"], capture_output=True, timeout=60, env=env)  # 토큰 갱신 유도
    d = curl()
print(json.dumps(d))
'''


@dataclass
class Bucket:
    group: str
    window: str  # "5h" | "weekly"
    remaining: float  # 0~1
    reset: datetime | None


def agy_quota() -> list[Bucket] | None:
    if not HOST:
        return None
    try:
        r = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", HOST, "python3", "-"],
            input=REMOTE, capture_output=True, text=True, timeout=90,
        )
        d = json.loads(r.stdout)
    except Exception:
        return None
    out = []
    for g in d.get("groups", []):
        name = g.get("displayName", "")
        for b in g.get("buckets", []):
            reset = b.get("resetTime")
            out.append(Bucket(
                group=name,
                window=b.get("window", "?"),
                remaining=float(b.get("remainingFraction", 0)),
                reset=datetime.fromisoformat(reset.replace("Z", "+00:00")) if reset else None,
            ))
    return out


if __name__ == "__main__":
    for b in agy_quota() or []:
        print(b)
