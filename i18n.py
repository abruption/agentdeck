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
    (r"(최고|시도) (\d+)번", r"\1 \2"),  # 게임 횟수
    (r"(\d+)코인 걸기", r"Bet \1"),
    (r"(\d+)코인(?=$| ·)", r"\1 coins"),
    (r"(\d+)분", r"\1 min"),
    (r"(\d+)시간", r"\1h"),
    (r"(\d+)일", r"\1d"),
    (r"CPU (\d+)위", r"CPU #\1"),
    (r"([\d·→]+)번(?= ·|$|\s*$)", r"#\1"),  # 복승 3·1번, 쌍승 4→2번
    (r"(\d)번 (\d)착", lambda m: f"#{m.group(1)} {_ord(int(m.group(2)))}"),
    (r"^([\d·]+)위$", r"P\1"),
    (r"(\d)번째 선택", r"pick \1"),
    (r"(\d)착 예상", lambda m: f"{_ord(int(m.group(1)))} pick"),
    (r"(\d)번 (?=(흑진주|먹구름|번개|질풍|천둥|바람|별빛|은하|태풍|불꽃|청룡|백설))", r"#\1 "),  # 경마 말 번호
    (r"^(\d)위$", r"#\1"),
    (r"^(\d)착$", r"#\1"),
    (r"내 말 (\d)착", r"My horse #\1"),
    (r"([\d.]+[GT]B) 중", r"of \1"),
    (r"%H:%M 종료", r"%H:%M end"),
]

def _ord(n: int) -> str:
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n, 'th')}"


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# 긴 문구부터 (부분 치환)
WORDS: list[tuple[str, str]] = sorted([
    ("두더지 잡기", "Whack-a-mole"), ("순서 기억", "Memory"), ("황금 +3 · 폭탄 -3", "Gold +3 · Bomb -3"),
    ("남은 시간", "Time left"), ("새 기록!", "New best!"), ("게임 끝", "Game over"), ("게임 그만", "Quit game"),
    ("판 누르기: 다시 하기", "Tap board: play again"), ("가운데: 메뉴", "Middle: menu"), ("잘 보세요", "Watch"),
    ("따라 누르기", "Repeat"), ("최고 기록", "Best"), ("두더지", "Mole"), ("순서", "Memory"),
    ("왼쪽:", "Left:"), ("오른쪽:", "Right:"), ("(30초)", "(30s)"), ("헛방", "Miss"), ("최고", "Best"),
    ("게임", "Games"), ("메뉴", "Menu"),
    ("짝 맞추기", "Pairs"), ("슬롯머신", "Slots"), ("기록 없음", "No record"), ("코인을 다 썼어요", "Out of coins"),
    ("판 누르기: 20코인으로 다시", "Tap board: restart with 20"), ("잭팟!", "Jackpot!"), ("당첨!", "Win!"),
    ("두 개 같음", "Two of a kind"), ("STOP 으로 하나씩 멈추기", "Press STOP on each reel"),
    ("양쪽 끝 칸: 돌리기 (1코인)", "Side keys: spin (1 coin)"), ("다이아", "Diamond"), ("별", "Star"),
    ("두 개 같으면", "Two alike"), ("잘 봐 두세요", "Memorize!"), ("맞춘 짝", "Pairs found"), ("시도", "Tries"),
    ("다 맞췄어요", "All matched"), ("하고 싶은 게임 칸을 누르세요", "Press a game to start"),
    ("두더지 · 순서 기억 · 짝 맞추기 · 슬롯머신", "Mole · Memory · Pairs · Slots"),
    ("가운데 버튼: 게임 중 메뉴로", "Middle: back to menu"),
    ("두더지 · 순서 · 짝 · 슬롯 · 블랙잭 · 포커", "Mole · Memory · Pairs · Slots · BJ · Poker"),
    ("두더지 · 순서 · 짝 · 슬롯 · 블랙잭 · 포커 · 경마", "Mole · Memory · Pairs · Slots · BJ · Poker · Race"), ("아랫줄에서 우승할 말을 고르세요", "Pick a winner on the bottom row"), ("배당이 높을수록 이기기 어려운 말", "Higher odds = longer shot"), ("여기를 누르면 출발", "Press here to start"), ("또 누르면 변경", "tap again to change"), ("아무 칸: 다음 경주", "Any key: next race"), ("마지막 직선, 접전!", "Final stretch, neck and neck!"), ("마지막 직선!", "Final stretch!"), ("출발했습니다!", "And they're off!"), ("선두로!", "takes the lead!"), ("선두", "leads"), ("우승!", "wins!"), ("맞혔어요! ", "Winner! "), ("출발 준비", "Get ready"), ("맞히면", "pays"), ("쌍승", "Exacta"), ("고른 순서대로 1착·2착", "1st and 2nd in the order you picked"),
    ("왼쪽 위 칸: 복승 ⇄ 쌍승", "Top-left: Quinella ⇄ Exacta"), ("2마리 복승·쌍승 · 3마리 삼복승", "2 = Quinella/Exacta · 3 = Trio"),
    ("착 예상", " place pick"), ("삼복승", "Trio"), ("복승", "Quinella"), ("단승", "Win"), (" 적중!", " hit!"),
    ("아랫줄 말 고르기: 1마리 단승", "Bottom row: 1 horse = Win"), ("2마리 복승 · 3마리 삼복승 (순서 상관없이)", "2 = Quinella · 3 = Trio (any order)"),
    ("윗줄 칩: 베팅액", "Top chips: bet size"), ("1착을 맞히면", "Pick the winner"), ("두 마리가 1·2착 (순서 상관없이)", "Both finish 1st-2nd (any order)"),
    ("세 마리가 1·2·3착 (순서 상관없이)", "All three finish top 3 (any order)"), ("번째 선택", " pick"), ("선택", "picked"), ("착순", "Order"), ("순위", "Pos"), ("내 말", "My horse"), ("경마", "Horse race"), ("출발", "GO"), ("흑진주", "Black Pearl"), ("먹구름", "Storm Cloud"), ("번개", "Bolt"), ("질풍", "Gale"), ("천둥", "Thunder"), ("바람", "Breeze"), ("별빛", "Starlight"), ("은하", "Galaxy"), ("태풍", "Typhoon"), ("불꽃", "Blaze"), ("청룡", "Blue Dragon"), ("백설", "Snowy"),
    ("포커 대결", "Poker duel"), ("하이카드", "High card"), ("원페어", "One pair"), ("상대가 바꾸는 중", "Opponent drawing"),
    ("상대", "Opp"), ("장 교체", " swapped"), ("내 패", "Me"), ("내 카드를 눌러 킵", "Tap your cards to hold"),
    ("킵 다 고르면 여기 누르기", "Then press here to draw"), ("컴퓨터와 5장 드로우 포커", "5-card draw vs computer"),
    ("이기면 2배 · 스트레이트 이상은 보너스", "Win pays 2x · straight+ bonus"), ("아무 칸: 다음 판 · 여기: 베팅", "Any key: next · here: bet"),
    ("로열 플러시", "Royal flush"), ("스트레이트 플러시", "Straight flush"),
    ("포카드", "Four of a kind"), ("풀하우스", "Full house"), ("플러시", "Flush"), ("스트레이트", "Straight"),
    ("트리플", "Three of a kind"), ("투페어", "Two pair"), ("J 이상 원페어", "Jacks or better"), ("교체", "DRAW"),
    ("킵 고르고 여기 누르기", "Pick holds, then press here"), ("지금 패", "Now"), ("없음", "nothing"),
    ("딜 또는 여기: 다음 판", "Deal or here: next hand"), ("아쉬워요", "No win"), ("베팅 고르고 딜", "Pick a bet, then deal"),
    ("누르면 남김", "tap to hold"), ("남김", "held"), ("킵?", "Hold?"), ("킵", "HOLD"), ("배", "x"), ("코인 걸기", "bet"), ("블랙잭!", "Blackjack!"),
    ("블랙잭", "Blackjack"), ("한 장 더", "one more"), ("그만", "stay"), ("딜러 차례", "dealer's turn"),
    ("베팅 바꾸기", "change bet"), ("바꾸기", "change"), ("베팅", "Bet"), ("딜러 버스트", "Dealer bust"),
    ("버스트", "Bust"), ("딜러", "Dealer"), ("나 ", "You "), ("넓은 칸: 더블", "Wide tile: double"),
    ("오른쪽 위: 딜 · 오른쪽 아래: 베팅 바꾸기", "Top right: deal · Bottom right: bet"),
    ("21에 가깝게, 넘으면 짐", "Get close to 21 without going over"), ("이겼어요", "You win"), ("비겼어요", "Push"),
    ("졌어요", "You lose"), ("아무 칸: 다음 판", "Any key: next hand"), ("딜", "DEAL"), ("돌리기", "SPIN"), ("코인", "Coins"),
    ("지금 쓰기 좋은", "Best now"), ("다음 리셋", "Next reset"), ("시간 대비", "vs time"),
    ("한도 정보 없음", "no data"), ("정보 없음", "no data"), ("데이터 없음", "no data"),
    ("연결 안 됨·미설정", "offline / not set"), ("연결 안 됨", "offline"), ("스튜디오 OFF", "Studio OFF"),
    ("눌러서 워크트리 보기", "Press for worktrees"), ("눌러서 이동", "Press to open"), ("눌러서 확인", "Press to view"),
    ("눌러서 종료", "Press to stop"), ("눌러서 닫기", "Press to close"), ("누르면 닫기", "Press to close"),
    ("누르면 시작", "Press to start"), ("누르면 변경", "Press to change"), ("길게 한 번 더", "Hold again"),
    ("길게: 밝기", "Hold: bright"), ("짧게: 일시정지 · 길게: 취소", "Tap: pause · Hold: cancel"),
    ("'취소' 칸 또는 길게: 종료", "'Cancel' tile or hold: stop"), ("아무 칸: 계속", "Any tile: resume"),
    ("코스피 상위", "KOSPI top"), ("코스닥 상위", "KOSDAQ top"), ("환율·원자재·금리", "FX · commodities · rates"),
    ("짧게 눌러 먹이 · 길게 눌러 나가기", "Tap to feed · hold to exit"),
    ("시총 상위", "Top market cap"), ("업종 등락", "Sector movers"), ("내 포트폴리오", "My portfolio"),
    ("관심 업종", "Watched sectors"), ("장 마감", "closed"), ("장중", "open"), ("히트맵", "Heatmap"),
    ("config 에 종목 추가", "add codes in config"), ("없는 업종", "unknown sector"), ("조회 실패", "lookup failed"),
    ("기타 총괄", "Other leads"), ("작업 현황", "Agents"), ("작업 중", "Working"), ("위임 중", "Delegated"),
    ("총괄 지시?", "Ask lead?"), ("총괄", "lead"),
    ("캐시·로그 정리", "Clean caches & logs"), ("캐시·로그", "Caches & logs"), ("앱 캐시·로그·임시 파일", "app caches, logs, temp files"),
    ("캐시 정리 중", "Cleaning caches"), ("이미 깨끗해요", "already clean"), ("빌드 산출물", "Build artifacts"), ("캐시 정리 가능", "cache"), ("정리 가능", "Mergeable"),
    ("디스크 남음", "Disk free"), ("남은 용량", "free"), ("사용률", "usage"), ("Mole 측정값", "from Mole"),
    ("재시작 권장", "restart advised"), ("Mole 없음", "no Mole"),
    ("다음 기기", "Next Mac"), ("시간 선택", "Pick a time"), ("집중 중", "Focus"), ("일시정지", "Paused"),
    ("뽀모도로", "Pomodoro"), ("완료!", "Done!"), ("비어 있음", "empty"), ("분리됨", "Detached"),
    ("워크트리", "Worktrees"), ("스튜디오", "Studio"), ("페이스", "pace"), ("주간", "Week"),
    ("리셋됨", "reset"), ("리셋", "reset"), ("갱신", "Refresh"), ("이전", "Prev"), ("다음", "Next"),
    ("뒤로", "Back"), ("보기", "View"), ("머신", "Machines"), ("기기", "Mac"), ("휴지통", "Trash"), ("비우기?", "Empty?"),
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
