#!/usr/bin/env python3
"""에이전트 상태 훅 설치/제거 (훅 방식: VS Code·Cursor·터미널 등 어디서 돌든 상태 수집).

  python3 scripts/install-hooks.py            # Claude Code 훅 설치
  python3 scripts/install-hooks.py --codex    # + Codex notify 연결 (기존 notify 는 이어서 실행되도록 감쌈)
  python3 scripts/install-hooks.py --uninstall

기존 훅은 건드리지 않고 우리 항목만 추가/제거한다. 바꾸기 전에 .bak-agentdeck 백업을 만든다.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(ROOT, "hooks", "agent_hook.py")
CLAUDE_CMD = f'python3 "{HOOK}" claude'
CLAUDE_SETTINGS = os.path.expanduser("~/.claude/settings.json")
CODEX_CONFIG = os.path.expanduser("~/.codex/config.toml")
EVENTS = {  # 이벤트 → matcher (도구 이벤트만 "*")
    "SessionStart": None, "UserPromptSubmit": None, "PreToolUse": "*", "PostToolUse": "*",
    "PermissionRequest": "*", "Notification": None, "Stop": None, "StopFailure": None, "SessionEnd": None,
}


def backup(path: str) -> None:
    if os.path.exists(path):
        shutil.copy2(path, path + ".bak-agentdeck")


def is_ours(entry: dict) -> bool:
    return any("agent_hook.py" in (h.get("command") or "") for h in entry.get("hooks", []))


def claude(install: bool) -> None:
    data = json.load(open(CLAUDE_SETTINGS)) if os.path.exists(CLAUDE_SETTINGS) else {}
    hooks = data.setdefault("hooks", {})
    for ev, matcher in EVENTS.items():
        arr = [e for e in hooks.get(ev, []) if not is_ours(e)]  # 우리 것 제거 (재설치 시 중복 방지)
        if install:
            entry = {"hooks": [{"type": "command", "command": CLAUDE_CMD, "timeout": 5}]}
            if matcher:
                entry = {"matcher": matcher, **entry}
            arr.append(entry)
        if arr:
            hooks[ev] = arr
        else:
            hooks.pop(ev, None)
    backup(CLAUDE_SETTINGS)
    os.makedirs(os.path.dirname(CLAUDE_SETTINGS), exist_ok=True)
    with open(CLAUDE_SETTINGS, "w") as fp:
        json.dump(data, fp, indent=2, ensure_ascii=False)
    print(("설치" if install else "제거"), "Claude Code 훅:", CLAUDE_SETTINGS)


def codex(install: bool) -> None:
    if not os.path.exists(CODEX_CONFIG):
        print("Codex 설정 없음:", CODEX_CONFIG)
        return
    text = open(CODEX_CONFIG).read()
    m = re.search(r"^notify\s*=\s*(\[.*?\])\s*$", text, re.M | re.S)
    current = json.loads(m.group(1)) if m else None
    ours = ["python3", HOOK, "codex", "--"]
    if current and len(current) >= 4 and current[1].endswith("agent_hook.py"):
        original = current[4:]  # 이미 우리 래퍼: 원래 명령만 꺼냄
    else:
        original = current or []
    new = (ours + original) if install else original
    line = "notify = " + json.dumps(new, ensure_ascii=False) if new else ""
    if m:
        text = text[:m.start()] + line + text[m.end():]
    elif line:
        text = line + "\n" + text
    backup(CODEX_CONFIG)
    open(CODEX_CONFIG, "w").write(text)
    print(("설치" if install else "제거"), "Codex notify:", CODEX_CONFIG, "(기존:", original or "없음", ")")


if __name__ == "__main__":
    uninstall = "--uninstall" in sys.argv
    claude(not uninstall)
    if "--codex" in sys.argv or uninstall:
        codex(not uninstall)
