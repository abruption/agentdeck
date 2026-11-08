"""알리익스프레스 주문을 내 맥에서 가져와 택배 목록(parcels.py)에 넣는다.

    .venv/bin/python parcels_import.py login   # 택배 전용 Chrome 창이 열림 → 알리에 직접 로그인 (처음 한 번)
    .venv/bin/python parcels_import.py         # 화면 없이 주문·운송장 가져오기

동작
- 일반 Chrome 과 따로 쓰는 전용 프로필(~/.cache/d200/ali-browser)을 쓴다. 로그인 정보는 이 맥의 그 폴더에만 남는다.
- 이 맥 안(127.0.0.1)에서만 브라우저에 접속한다. 비밀번호는 저장하지도 입력하지도 않는다 (로그인은 사람이 직접).
- 주문 페이지에서는 "주문 더 보기" 단추만 누른다. 배송 완료 확인·취소 같은 단추는 누르지 않는다.
- 가져온 내용은 ~/.cache/d200/parcels.json 에만 저장된다.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

import parcels

PROFILE = Path.home() / ".cache" / "d200" / "ali-browser"
PORT = 9333
ORDERS_URL = "https://www.aliexpress.com/p/order/index.html"
TRACK_URL = "https://www.aliexpress.com/p/tracking/index.html?_addShare=no&_login=yes&tradeOrderId={id}"
CHROME = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
          "/Applications/Chromium.app/Contents/MacOS/Chromium",
          "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"]
MAX_ORDERS = 40
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DAYS = 60  # 최근 이 기간 주문만

# 주문 목록에서 주문 카드 읽기 (누르는 단추는 '주문 더 보기' 하나뿐)
LIST_JS = r'''(async (days) => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const ids = () => [...new Set([...document.querySelectorAll('a[href*="order/detail.html?orderId="]')]
      .map(a => new URL(a.href).searchParams.get('orderId')))];
  const MORE = ['주문 더 보기', 'view orders', 'more orders', 'load more'];
  for (let i = 0; i < 12; i++) {
    const btn = [...document.querySelectorAll('button')].find(b => MORE.includes(b.textContent.trim().toLowerCase()));
    const txt = document.body.innerText;
    const MON = {jan:0,feb:1,mar:2,apr:3,may:4,jun:5,jul:6,aug:7,sep:8,oct:9,nov:10,dec:11};
    const ds = [...txt.matchAll(/(\d{4})[년.\-\/ ]\s*(\d{1,2})[월.\-\/ ]\s*(\d{1,2})/g)]
        .map(m => new Date(+m[1], +m[2] - 1, +m[3]).getTime())
        .concat([...txt.matchAll(/\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.? (\d{1,2}), (\d{4})/g)]
        .map(m => new Date(+m[3], MON[m[1].toLowerCase()], +m[2]).getTime()));
    if (!btn || (ds.length && Date.now() - Math.min(...ds) > days * 86400000)) break;
    const n = ids().length; btn.click();
    for (let k = 0; k < 12 && ids().length === n; k++) await sleep(500);
  }
  return ids().map(id => {
    const a = document.querySelector(`a[href*="orderId=${id}"]`);
    let best = a, n = a;
    while (n && n.parentElement) {   // 이 주문 하나만 담은 가장 큰 덩어리 = 주문 카드
      const p = n.parentElement;
      const s = new Set([...p.querySelectorAll('a[href*="order/detail.html?orderId="]')].map(x => new URL(x.href).searchParams.get('orderId')));
      if (s.size > 1) break;
      best = p; n = p;
    }
    const track = [...best.querySelectorAll('a')].map(x => x.href).find(h => /tracking/.test(h)) || '';
    return {id, text: best.innerText.slice(0, 900), track};
  });
})'''


def _chrome() -> str:
    for c in CHROME:
        if Path(c).exists():
            return c
    found = shutil.which("google-chrome") or shutil.which("chromium")
    if not found:
        raise SystemExit("Chrome(또는 Chromium·Edge)이 필요해요")
    return found


def _alive() -> str | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=2) as r:
            return json.loads(r.read())["webSocketDebuggerUrl"]
    except Exception:
        return None


def launch(headless: bool) -> subprocess.Popen | None:
    """전용 프로필로 Chrome 실행 (이미 떠 있으면 그대로 씀)."""
    if _alive():
        return None
    PROFILE.mkdir(parents=True, exist_ok=True)
    args = [_chrome(), f"--user-data-dir={PROFILE}", f"--remote-debugging-port={PORT}",
            "--remote-debugging-address=127.0.0.1", "--no-first-run", "--no-default-browser-check"]
    if headless:
        args += ["--headless=new", "--window-size=1400,1000"]
    proc = subprocess.Popen(args + ([ORDERS_URL] if not headless else []),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        if _alive():
            return proc
        time.sleep(0.25)
    raise SystemExit("Chrome 을 띄우지 못했어요")


class _CDP:
    def __init__(self, ws) -> None:
        self.ws, self.n = ws, 0

    async def call(self, method: str, params: dict | None = None, sid: str | None = None, timeout: float = 60):
        self.n += 1
        mid = self.n
        msg = {"id": mid, "method": method, "params": params or {}}
        if sid:
            msg["sessionId"] = sid
        await self.ws.send(json.dumps(msg))
        while True:
            r = json.loads(await asyncio.wait_for(self.ws.recv(), timeout))
            if r.get("id") == mid:
                return r


async def _collect() -> list[dict]:
    import websockets

    ws_url = _alive()
    async with websockets.connect(ws_url, max_size=100_000_000) as ws:
        c = _CDP(ws)
        tid = (await c.call("Target.createTarget", {"url": ORDERS_URL, "background": True}))["result"]["targetId"]
        sid = (await c.call("Target.attachToTarget", {"targetId": tid, "flatten": True}))["result"]["sessionId"]

        async def ev(js: str, t: float = 90):
            r = await c.call("Runtime.evaluate", {"expression": js, "returnByValue": True, "awaitPromise": True}, sid, t)
            return r.get("result", {}).get("result", {}).get("value")

        await asyncio.sleep(8)
        href = await ev("location.href") or ""
        if "login" in href:
            await c.call("Target.closeTarget", {"targetId": tid})
            raise SystemExit("알리에 로그인이 필요해요: .venv/bin/python parcels_import.py login")
        orders = await ev(f"{LIST_JS}({DAYS})", 150) or []
        active = [o for o in orders if _status(o["text"]) not in ("done", "cancel")][:MAX_ORDERS]
        for o in active:
            try:
                await c.call("Page.navigate", {"url": o["track"] or TRACK_URL.format(id=o["id"])}, sid)
                await asyncio.sleep(6)
                o["tracking_text"] = await ev("document.body.innerText.slice(0, 5000)") or ""
            except Exception as e:  # 하나가 실패해도 나머지는 계속
                print(f"배송 조회 실패 {o['id']}: {e}", flush=True)
                o["tracking_text"] = ""
        await c.call("Target.closeTarget", {"targetId": tid})
        return active


def _status(text: str) -> str:
    head = text[:120]
    if re.search(r"처리 완료|완료됨|거래 완료|Completed|Finished", head):
        return "done"
    if re.search(r"취소|Cancel|Closed|환불", head):
        return "cancel"
    if re.search(r"배송 중|Shipped|Awaiting delivery|In transit|배송완료 대기", head):
        return "shipped"
    return "processing"


def _parse(o: dict) -> dict:
    """주문 카드·배송 조회 화면 글에서 상품명·주문일·운송장·예상일·이동 기록 뽑기."""
    lines = [x.strip() for x in o["text"].split("\n") if x.strip()]
    m = re.search(r"(\d{4})[년.\-/ ]\s*(\d{1,2})[월.\-/ ]\s*(\d{1,2})", o["text"])
    ordered = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else ""
    m = None if ordered else re.search(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.? (\d{1,2}), (\d{4})", o["text"])
    if m:
        ordered = f"{m.group(3)}-{MONTHS.index(m.group(1)) + 1:02d}-{int(m.group(2)):02d}"
    title = ""
    for x in lines:  # 상점 이름 다음의 긴 줄 = 상품명
        if len(x) > 14 and not re.search(r"주문|Order|Ref\.|Number|Date|₩|\$|총 금액|Total|배송|delivery|무료|Free|쿠폰|coupon|Store$|스토어$|Confirm|received|Track|Edit address|확인|조회|주소 변경", x):
            title = x
            break
    t = o.get("tracking_text", "")
    no = ""
    for pat in (r"(?:운송장\s*번호|추적\s*번호|송장\s*번호|Tracking\s*(?:number|No\.?))\s*[:：]?\s*([A-Z0-9]{8,30})",
                r"\b((?:LP|AE|CN|SY|YT|UB|LX|RB|RR)[A-Z0-9]{8,26})\b"):
        mm = re.search(pat, t)
        if mm:
            no = mm.group(1)
            break
    eta = eta_end = ""
    mm = re.search(r"(?:Delivery|배송|도착 예정)\s*[:：]\s*([^\n]{3,40})", t)
    if mm:
        span = mm.group(1)
        en = re.findall(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*(\d{1,2})", span)
        ko = re.findall(r"(?:(\d{1,2})월\s*)?(\d{1,2})일", span)
        nums = re.findall(r"[-~–]\s*(\d{1,2})\b", span)
        days: list[tuple[int, int]] = []
        if en:
            days = [(MONTHS.index(m) + 1, int(d)) for m, d in en]
        elif ko:
            mon = 0
            for m, d in ko:
                mon = int(m) if m else mon
                days.append((mon, int(d)))
        if days and len(days) == 1 and nums:  # "Nov 11 - 13" 처럼 끝 날짜에 달이 없으면
            d2 = int(nums[-1])
            days.append((days[0][0] + (1 if d2 < days[0][1] else 0), d2))
        if days and days[0][0]:
            today = date.today()
            def iso(md):
                mon, d = (md[0] - 1) % 12 + 1, md[1]
                y = today.year + (1 if md[0] > 12 or mon < today.month - 6 else 0)
                return f"{y}-{mon:02d}-{d:02d}"
            eta, eta_end = iso(days[0]), iso(days[-1])
    events = []
    lines = [x.strip() for x in t.split("\n")]
    for k, line in enumerate(lines):  # "내용" 다음 줄에 "Sun | Nov. 08 14:49" 형식의 시각
        mm = re.match(r"^\w{2,3}\s*\|\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*(\d{1,2})\s+(\d{1,2}:\d{2})", line) \
            or re.match(r"^(?:\S+\s*\|\s*)?(\d{1,2})월\s*(\d{1,2})일\s+(\d{1,2}:\d{2})", line)
        if mm and k > 0 and lines[k - 1]:
            mon = MONTHS.index(mm.group(1)) + 1 if not mm.group(1).isdigit() else int(mm.group(1))
            events.append((f"{date.today().year}-{mon:02d}-{int(mm.group(2)):02d} {mm.group(3)}", lines[k - 1]))
    mm = re.search(r"Tracking number[^\n]*\n(?:Copy\n)?([^\n]{3,60})\n", t)
    if mm and not events:
        events.append(("", mm.group(1)))
    return {"order_no": o["id"], "title": title[:40], "ordered": ordered, "tracking": no, "eta": eta, "eta_end": eta_end,
            "events": events[:8], "status": _status(o["text"])}


def run() -> list[dict]:
    proc = launch(headless=True)
    try:
        raw = asyncio.run(_collect())
    finally:
        if proc:
            proc.terminate()
    got = [_parse(o) for o in raw]
    with parcels._lock:
        ps = parcels.load()
        by_order = {p.order_no: p for p in ps if p.order_no}
        for g in got:
            p = by_order.get(g["order_no"])
            if not p:
                p = parcels.Parcel(tracking=g["tracking"] or f"ORDER{g['order_no']}", order_no=g["order_no"])
                ps.append(p)
            p.title = g["title"] or p.title
            p.ordered = g["ordered"] or p.ordered
            if g["tracking"]:
                p.tracking = g["tracking"]
            if g["eta"]:
                p.eta, p.eta_end = g["eta"], g["eta_end"]
            if g["events"]:
                p.events = g["events"]
            p.stage = max(p.stage, parcels._stage_of(p.events) if p.events else
                          (parcels.STAGE["발송"] if g["status"] == "shipped" else 0))
        parcels.save(ps)
    return got


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "login":
        if _alive():  # 이미 떠 있으면(창을 닫았거나 화면 없이 도는 중) 새 창으로 로그인 화면 열기
            urllib.request.urlopen(urllib.request.Request(
                f"http://127.0.0.1:{PORT}/json/new?{ORDERS_URL}", method="PUT"), timeout=5).read()
            subprocess.run(["osascript", "-e", 'tell application "Google Chrome" to activate'], capture_output=True)
        else:
            launch(headless=False)
        print("택배 전용 Chrome 창에서 알리에 로그인한 뒤 그 창을 닫아 주세요.")
    else:
        for g in run():
            print(g["status"], g["tracking"] or "-", g["eta"] or "-", g["title"])
