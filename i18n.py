"""기기 화면 문구 언어 (config.json 의 "ui_lang": "ko" | "en").

페이지 코드는 한국어로 문구를 만들고, 그리는 단계(render_icon·시계 패널)에서 tr() 로 바꾼다.
숫자가 들어간 문구는 정규식, 나머지는 긴 문구부터 치환한다.
"""

from __future__ import annotations

import re

try:
    from config import CFG

    LANG: str = CFG.get("ui_lang", "ko")
except Exception:
    LANG = "ko"

# 숫자가 들어가는 패턴 (먼저 적용)
PATTERNS: list[tuple[str, str]] = [
    (r"(\d+)/(\d+) 페이지", r"Page \1/\2"),
    (r"(\d+)월 (\d+)일", None),  # 날짜: 아래 _date 에서 처리
    (r"캐시 정리 가능 ([\d.]+[GT]B)", r"\1 reclaimable"),
    (r"정리 가능 ([\d.]+[GT]B)", r"\1 reclaimable"),
    (r"(\d+)초마다", r"every \1s"),
    (r"가동 (\d+)일", r"up \1d"),
    (r"(\d+)개 항목", r"\1 items"),
    (r"(\d+)개", r"\1 items"),
    (r"(\d+)분", r"\1 min"),
    (r"(\d+)시간", r"\1h"),
    (r"(\d+)일", r"\1d"),
    (r"CPU (\d+)위", r"CPU #\1"),
    (r"([\d.]+[GT]B) 중", r"of \1"),
    (r"%H:%M 종료", r"%H:%M end"),
]

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# 긴 문구부터 (부분 치환)
WORDS: list[tuple[str, str]] = sorted([
    ("지금 쓰기 좋은", "Best now"), ("다음 리셋", "Next reset"), ("시간 대비", "vs time"),
    ("한도 정보 없음", "no data"), ("정보 없음", "no data"), ("데이터 없음", "no data"),
    ("연결 안 됨·미설정", "offline / not set"), ("연결 안 됨", "offline"), ("스튜디오 OFF", "Studio OFF"),
    ("눌러서 워크트리 보기", "Press for worktrees"), ("눌러서 이동", "Press to open"), ("눌러서 확인", "Press to view"),
    ("눌러서 종료", "Press to stop"), ("눌러서 닫기", "Press to close"), ("누르면 닫기", "Press to close"),
    ("누르면 시작", "Press to start"), ("누르면 변경", "Press to change"), ("길게 한 번 더", "Hold again"),
    ("길게: 밝기", "Hold: bright"), ("짧게: 일시정지 · 길게: 취소", "Tap: pause · Hold: cancel"),
    ("'취소' 칸 또는 길게: 종료", "'Cancel' tile or hold: stop"), ("아무 칸: 계속", "Any tile: resume"),
    ("기타 총괄", "Other leads"), ("작업 현황", "Agents"), ("작업 중", "Working"), ("위임 중", "Delegated"),
    ("총괄 지시?", "Ask lead?"), ("총괄", "lead"),
    ("빌드 산출물", "Build artifacts"), ("캐시 정리 가능", "cache"), ("정리 가능", "Mergeable"),
    ("디스크 남음", "Disk free"), ("남은 용량", "free"), ("사용률", "usage"), ("Mole 측정값", "from Mole"),
    ("재시작 권장", "restart advised"), ("Mole 없음", "no Mole"),
    ("다음 기기", "Next Mac"), ("시간 선택", "Pick a time"), ("집중 중", "Focus"), ("일시정지", "Paused"),
    ("뽀모도로", "Pomodoro"), ("완료!", "Done!"), ("비어 있음", "empty"), ("분리됨", "Detached"),
    ("워크트리", "Worktrees"), ("스튜디오", "Studio"), ("페이스", "pace"), ("주간", "Week"),
    ("리셋됨", "reset"), ("리셋", "reset"), ("갱신", "Refresh"), ("이전", "Prev"), ("다음", "Next"),
    ("뒤로", "Back"), ("머신", "Machines"), ("기기", "Mac"), ("휴지통", "Trash"), ("비우기?", "Empty?"),
    ("비우기", "Empty"), ("정리?", "Purge?"), ("정리", "Purge"), ("삭제?", "Remove?"),
    ("메모리", "Memory"), ("디스크", "Disk"), ("건강", "Health"), ("실행", "run"), ("하위", "sub"),
    ("결정", "Decide"), ("완료", "Done"), ("작업", "Working"), ("대기", "Idle"), ("방치", "Stale"),
    ("오래됨", "Old"), ("정상", "OK"), ("변경", "changes"), ("앞섬", "ahead"), ("과속", "Too fast"),
    ("적정", "On track"), ("여유", "Ahead"), ("추천", "Best"), ("확인", "check"), ("취소", "Cancel"),
    ("마다", " each"), ("초", "s"), ("없음", "none"), ("타이머", "Timer"), ("종료", "end"),
], key=lambda kv: -len(kv[0]))

WEEKDAYS_EN = {"월요일": "Monday", "화요일": "Tuesday", "수요일": "Wednesday", "목요일": "Thursday",
               "금요일": "Friday", "토요일": "Saturday", "일요일": "Sunday"}


def tr(text: str | None) -> str | None:
    """현재 LANG 으로 문구를 바꾼다 (ko 면 그대로)."""
    if not text or LANG == "ko" or not re.search("[가-힣]", text):
        return text
    if text in WEEKDAYS_EN:
        return WEEKDAYS_EN[text]
    s = re.sub(r"(\d+)월 (\d+)일", lambda m: f"{MONTHS[int(m.group(1)) - 1]} {m.group(2)}", text)
    for pat, rep in PATTERNS:
        if rep:
            s = re.sub(pat, rep, s)
    for ko, en in WORDS:
        s = s.replace(ko, en)
    return s
