"""Ulanzi 스트림 컨트롤러 HID 탐색 스크립트.

모든 HID 인터페이스를 열고, 들어오는 raw 리포트를 hex로 기록한다.
사용법: .venv/bin/python explore.py [초]  (기본 90초)
"""

import sys
import threading
import time

import hid

VID, PID = 0x2207, 0x0019
DURATION = float(sys.argv[1]) if len(sys.argv) > 1 else 90.0
LOG_PATH = "explore.log"

log_lock = threading.Lock()
log_file = open(LOG_PATH, "w", buffering=1)


def log(msg: str) -> None:
    """콘솔과 로그 파일에 동시에 기록한다."""
    line = f"{time.strftime('%H:%M:%S')}.{int(time.time() * 1000) % 1000:03d} {msg}"
    with log_lock:
        print(line, flush=True)
        log_file.write(line + "\n")


def trim(data: list[int]) -> str:
    """뒤쪽 0 패딩을 잘라 읽기 쉬운 hex로 만든다."""
    end = len(data)
    while end > 0 and data[end - 1] == 0:
        end -= 1
    body = bytes(data[: max(end, 1)]).hex(" ")
    return f"[len={len(data)}, nonzero={end}] {body}"


def reader(info: dict, stop: threading.Event) -> None:
    """한 인터페이스에서 리포트를 계속 읽는다."""
    tag = f"if{info['interface_number']}(up=0x{info['usage_page']:x})"
    dev = hid.device()
    try:
        dev.open_path(info["path"])
    except OSError as e:
        log(f"{tag} OPEN FAIL: {e}")
        return
    log(f"{tag} opened: {dev.get_manufacturer_string()} / {dev.get_product_string()}")
    try:
        desc = dev.get_report_descriptor()
        log(f"{tag} report descriptor ({len(desc)}B): {bytes(desc).hex(' ')}")
    except Exception as e:  # 구버전 hidapi는 미지원
        log(f"{tag} report descriptor 읽기 실패: {e}")

    dev.set_nonblocking(False)
    last = None
    count = 0
    while not stop.is_set():
        data = dev.read(1024, 200)  # 200ms 타임아웃
        if not data:
            continue
        count += 1
        text = trim(data)
        # 같은 패킷이 반복되면(주기적 heartbeat 등) 요약만 남긴다
        if text == last:
            log(f"{tag} #{count} (직전과 동일)")
        else:
            log(f"{tag} #{count} {text}")
        last = text
    dev.close()
    log(f"{tag} closed, 총 {count}개 리포트")


def main() -> None:
    infos = hid.enumerate(VID, PID)
    if not infos:
        log("장치를 찾지 못함. USB 연결과 Ulanzi Studio 종료 여부를 확인하세요.")
        return
    stop = threading.Event()
    threads = [threading.Thread(target=reader, args=(i, stop), daemon=True) for i in infos]
    for t in threads:
        t.start()
    log(f"=== {DURATION:.0f}초 동안 감시합니다. 버튼을 하나씩 천천히 눌러보세요 (다이얼/길게 누르기 포함) ===")
    try:
        time.sleep(DURATION)
    except KeyboardInterrupt:
        pass
    stop.set()
    for t in threads:
        t.join(timeout=1)
    log("=== 종료 ===")


if __name__ == "__main__":
    main()
