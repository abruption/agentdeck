"""효과음: 덱이 연결된 맥의 스피커로 재생한다 (D200 에는 스피커가 없다).

소리는 처음 쓸 때 파이썬으로 직접 합성해 ~/.cache/d200/sfx/ 에 WAV 로 저장하고, macOS `afplay` 로 튼다.
config.json: "sound": {"enabled": true, "volume": 0.6}  (기본은 꺼짐)
"""

from __future__ import annotations

import math
import random
import re
import struct
import subprocess
import threading
import time
import wave
from pathlib import Path

from config import CFG

_CFG = CFG.get("sound") or {}
ENABLED = bool(_CFG.get("enabled"))
VOLUME = float(_CFG.get("volume", 0.6))
RATE = 22050
VERSION = 6  # 소리를 바꾸면 올려서 캐시를 새로 만든다
DIR = Path.home() / ".cache" / "d200" / "sfx" / f"v{VERSION}"
SIMON = [523, 587, 659, 784, 880, 1047, 1175, 1319, 1568, 1760]  # 순서 기억: 칸마다 다른 음 (펜타토닉)

_lock = threading.Lock()
_last: dict[str, float] = {}


# ---------- 합성 ----------
def _env(i: int, n: int, attack: float = 0.005, release: float = 0.6) -> float:
    t = i / RATE
    a = min(1.0, t / attack) if attack > 0 else 1.0
    r = max(0.0, 1 - (i / n)) ** (1 / max(release, 1e-3))
    return a * r


def _tone(freq: float, dur: float, kind: str = "sine", sweep: float = 0.0, vol: float = 0.5,
          release: float = 0.6) -> list[float]:
    n = int(RATE * dur)
    out, ph = [], 0.0
    for i in range(n):
        f = freq + sweep * i / n
        ph += 2 * math.pi * f / RATE
        if kind == "square":
            v = 1.0 if math.sin(ph) >= 0 else -1.0
        elif kind == "saw":
            v = (ph / math.pi) % 2 - 1
        elif kind == "tri":
            v = 2 * abs((ph / math.pi) % 2 - 1) - 1
        else:
            v = math.sin(ph)
        out.append(v * vol * _env(i, n, release=release))
    return out


def _noise(dur: float, vol: float = 0.5, smooth: float = 0.0, release: float = 0.6, swell: bool = False,
           seed: int = 1) -> list[float]:
    """smooth 0 = 거친 소리(쉭), 0.9 = 낮게 웅웅거리는 소리."""
    rnd = random.Random(seed)
    n = int(RATE * dur)
    out, prev = [], 0.0
    for i in range(n):
        prev = prev * smooth + rnd.uniform(-1, 1) * (1 - smooth)
        e = math.sin(math.pi * i / n) if swell else _env(i, n, release=release)
        out.append(prev * vol * e * (3 if smooth > 0.5 else 1))
    return out


def _seq(*parts: list[float], gap: float = 0.0) -> list[float]:
    out: list[float] = []
    for p in parts:
        out += p + [0.0] * int(RATE * gap)
    return out


def _mix(*parts: list[float]) -> list[float]:
    n = max(len(p) for p in parts)
    return [sum(p[i] for p in parts if i < len(p)) for i in range(n)]


def _arp(freqs: list[float], step: float, kind: str = "square", vol: float = 0.3) -> list[float]:
    return _seq(*[_tone(f, step, kind, vol=vol, release=0.8) for f in freqs])


def _loop(x: list[float], sec: float = 1.5) -> list[float]:
    """끝부분을 앞부분에 겹쳐 섞어서, 반복해도 이음새가 들리지 않게 (길이는 sec 만큼 줄어듦)."""
    n = int(RATE * sec)
    body = x[:len(x) - n]
    tail = x[len(x) - n:]
    for i in range(n):
        k = i / n
        body[i] = body[i] * math.sqrt(k) + tail[i] * math.sqrt(1 - k)
    return body


def _amb_water(dur: float = 21.5) -> list[float]:
    """어항: 낮게 흐르는 물소리 + 가끔 올라가는 기포 '뽀록'."""
    rnd = random.Random(11)
    n = int(RATE * dur)
    out, a, b = [0.0] * n, 0.0, 0.0
    for i in range(n):  # 두 번 걸러 낸 잔잔한 물소리, 천천히 일렁임
        a = a * 0.985 + rnd.uniform(-1, 1) * 0.015
        b = b * 0.9 + a * 0.1
        out[i] = b * 2.2 * (0.75 + 0.25 * math.sin(2 * math.pi * i / RATE * 0.23))
    t = 0.3
    while t < dur - 0.4:  # 기포: 위로 올라가는 짧은 음
        f0, ln = rnd.uniform(260, 520), rnd.uniform(0.04, 0.09)
        for burst in range(rnd.choice((1, 1, 2, 3))):
            st = int(RATE * (t + burst * 0.07))
            m = int(RATE * ln)
            ph = 0.0
            for j in range(m):
                if st + j >= n:
                    break
                ph += 2 * math.pi * (f0 * (1 + 1.6 * j / m)) / RATE
                out[st + j] += math.sin(ph) * 0.16 * math.sin(math.pi * j / m)
        t += rnd.uniform(0.35, 1.4)
    return _loop(out)


def _amb_fire(dur: float = 21.5) -> list[float]:
    """불멍: 낮게 웅웅대는 불 소리 + 타닥타닥 장작 튀는 소리."""
    rnd = random.Random(7)
    n = int(RATE * dur)
    out, a, b = [0.0] * n, 0.0, 0.0
    for i in range(n):
        a = a * 0.996 + rnd.uniform(-1, 1) * 0.004
        b = b * 0.8 + rnd.uniform(-1, 1) * 0.2
        out[i] = a * 7 + b * 0.025 * (0.6 + 0.4 * math.sin(2 * math.pi * i / RATE * 0.4))
    t = 0.1
    while t < dur - 0.2:  # 타닥: 아주 짧은 잡음 덩어리, 몰려서 나기도 함
        for burst in range(rnd.choice((1, 1, 2, 3, 5))):
            st = int(RATE * (t + burst * rnd.uniform(0.02, 0.09)))
            m = int(RATE * rnd.uniform(0.002, 0.012))
            amp = rnd.uniform(0.15, 0.55)
            for j in range(m):
                if st + j < n:
                    out[st + j] += rnd.uniform(-1, 1) * amp * (1 - j / m)
        t += rnd.uniform(0.08, 0.7)
    return _loop(out)


def _amb_rain(dur: float = 21.5) -> list[float]:
    """비멍: 쏴아 하는 빗소리 + 창에 톡톡 떨어지는 빗방울."""
    rnd = random.Random(5)
    n = int(RATE * dur)
    out, a, b = [0.0] * n, 0.0, 0.0
    for i in range(n):
        w = rnd.uniform(-1, 1)
        a = a * 0.55 + w * 0.45  # 높은 쏴아
        b = b * 0.97 + w * 0.03  # 낮은 웅
        out[i] = a * 0.09 + b * 0.5 * (0.85 + 0.15 * math.sin(2 * math.pi * i / RATE * 0.11))
    for _ in range(int(dur * 9)):  # 톡: 짧고 맑은 소리
        st, f = rnd.randrange(n - 800), rnd.uniform(1800, 4200)
        amp = rnd.uniform(0.03, 0.12)
        for j in range(int(RATE * 0.012)):
            out[st + j] += math.sin(2 * math.pi * f * j / RATE) * amp * (1 - j / (RATE * 0.012))
    return _loop(out)


def _amb_waves(dur: float = 29.5) -> list[float]:
    """바다: 파도가 밀려와 부서지고 쓸려 나가는 소리 (약 7초 주기)."""
    rnd = random.Random(9)
    n = int(RATE * dur)
    out, a, b = [0.0] * n, 0.0, 0.0
    period = 7.0
    for i in range(n):
        t = i / RATE
        ph = (t % period) / period
        swell = math.sin(math.pi * min(1.0, ph / 0.55)) ** 2 if ph < 0.55 else 0.0  # 밀려와 부서짐
        wash = max(0.0, 1 - (ph - 0.5) / 0.5) * 0.45 if ph >= 0.5 else 0.0  # 쓸려 나감
        w = rnd.uniform(-1, 1)
        a = a * 0.9 + w * 0.1
        b = b * 0.985 + w * 0.015
        out[i] = a * (0.08 + 0.35 * swell + 0.2 * wash) + b * (0.6 + 1.6 * swell)
    return _loop(out, 2.5)


def _sounds() -> dict[str, list[float]]:
    s = {
        "tap": _tone(1400, 0.035, "sine", vol=0.4),
        "tick": _tone(2200, 0.015, "square", vol=0.15),
        "flip": _noise(0.06, 0.35, 0.2),
        "hit": _tone(330, 0.09, "square", sweep=-200, vol=0.35),
        "coin": _seq(_tone(988, 0.06, "square", vol=0.25), _tone(1319, 0.16, "square", vol=0.25)),
        "bad": _tone(110, 0.28, "saw", vol=0.35),
        "boom": _mix(_noise(0.45, 0.6, 0.85, release=0.4), _tone(80, 0.4, "sine", sweep=-40, vol=0.5)),
        "win": _arp([523, 659, 784, 1047], 0.09),
        "jackpot": _seq(_arp([523, 659, 784, 1047, 784, 1047, 1319, 1568], 0.08), _tone(2093, 0.4, "square", vol=0.25)),
        "lose": _arp([392, 330, 262], 0.14, "tri", 0.35),
        "card": _noise(0.05, 0.3, 0.1),
        "bell": _mix(_tone(880, 0.9, vol=0.3, release=0.35), _tone(1760, 0.6, vol=0.12, release=0.3),
                     _tone(2640, 0.4, vol=0.06, release=0.3)),
        "gallop": _seq(*[_mix(_noise(0.05, 0.6, 0.8, seed=k), _tone(90, 0.05, vol=0.3))
                         for k in range(12)], gap=0.09),
        "whoosh": _mix(_noise(0.7, 0.4, 0.3, swell=True), _tone(200, 0.7, "sine", sweep=-120, vol=0.15)),
        "cheer": _noise(1.8, 0.35, 0.55, swell=True, seed=7),
        "shutter": _seq(_tone(3000, 0.012, "square", vol=0.3), _noise(0.07, 0.4, 0.0)),
        "slash": _noise(0.16, 0.45, 0.05, release=0.3),
        "fire": _mix(_noise(0.45, 0.35, 0.5), _tone(150, 0.45, "saw", sweep=250, vol=0.15)),
        "roar": _mix(_noise(1.3, 0.5, 0.92, release=0.7, seed=3), _tone(70, 1.3, "saw", sweep=-25, vol=0.3)),
        "levelup": _arp([523, 659, 784, 1047, 1319], 0.07),
        "heal": _arp([784, 988, 1175], 0.08, "sine", 0.3),
        "dead": _arp([392, 370, 349, 330, 262], 0.16, "tri", 0.35),
        "crackle": _seq(*[_noise(0.008, 0.5, 0.0, seed=k) + [0.0] * int(RATE * 0.03 * (k % 3 + 1)) for k in range(4)]),
        "intro": _mix(_seq(_tone(392, 0.12, "tri", vol=0.25), _tone(523, 0.12, "tri", vol=0.25),
                           _tone(659, 0.12, "tri", vol=0.25), _tone(784, 0.7, "tri", vol=0.3, release=0.5)),
                      _seq([0.0] * int(RATE * 0.36), _tone(1568, 0.6, "sine", vol=0.12, release=0.4))),
    }
    s["amb_water"] = _amb_water()
    s["amb_fire"] = _amb_fire()
    s["amb_rain"] = _amb_rain()
    s["amb_waves"] = _amb_waves()
    s["thunder"] = _loop(_mix(_noise(2.6, 0.7, 0.97, release=0.5, seed=4), _noise(0.25, 0.4, 0.3, seed=6)), 0.01)
    for k, f in enumerate(SIMON):
        s[f"note{k}"] = _tone(f, 0.28, "tri", vol=0.4, release=0.5)
    return s


def _write(path: Path, samples: list[float]) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1.0, min(1.0, v)) * 32000)) for v in samples))


def _ensure() -> None:
    if (DIR / "done").exists():
        return
    DIR.mkdir(parents=True, exist_ok=True)
    for name, smp in _sounds().items():
        _write(DIR / f"{name}.wav", smp)
    (DIR / "done").write_text("ok")


# ---------- 재생 ----------
def play_file(path: Path, gap: float = 0.0, volume: float = 1.0) -> None:
    """준비된 소리 파일(mp3·wav 등)을 튼다. 같은 파일을 gap 초 안에 또 부르면 무시."""
    if not ENABLED or not Path(path).exists():
        return
    now = time.time()
    with _lock:
        if now - _last.get(str(path), 0) < gap:
            return
        _last[str(path)] = now
    subprocess.Popen(["afplay", "-v", f"{VOLUME * volume:.2f}", str(path)],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def play(name: str, gap: float = 0.04, volume: float = 1.0) -> None:
    """소리 하나를 바로 튼다 (기다리지 않음). 같은 소리를 gap 초 안에 또 부르면 무시."""
    if not ENABLED:
        return
    now = time.time()
    with _lock:
        if now - _last.get(name, 0) < gap:
            return
        _last[name] = now

    def run() -> None:
        try:
            _ensure()
            path = DIR / f"{name}.wav"
            if path.exists():
                subprocess.Popen(["afplay", "-v", f"{VOLUME * volume:.2f}", str(path)],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    threading.Thread(target=run, daemon=True).start()


def _duration(path: Path) -> float:
    try:
        if path.suffix == ".wav":
            with wave.open(str(path)) as w:
                return w.getnframes() / w.getframerate()
        out = subprocess.run(["afinfo", str(path)], capture_output=True, text=True, timeout=5).stdout
        m = re.search(r"estimated duration: ([\d.]+)", out)
        return float(m.group(1)) if m else 0.0
    except Exception:
        return 0.0


class Ambient:
    """배경음 반복 재생 (어항 물소리·불멍 장작 소리). 준비된 파일(sounds/amb_*.mp3)이 있으면 그걸, 없으면 합성음."""

    def __init__(self) -> None:
        self.name: str | None = None
        self.proc: subprocess.Popen | None = None
        self._stop = threading.Event()
        self.thread: threading.Thread | None = None

    def _path(self, name: str) -> Path:
        mine = Path(__file__).parent / "sounds" / f"{name}.mp3"
        if mine.exists():
            return mine
        _ensure()
        return DIR / f"{name}.wav"

    def start(self, name: str, volume: float = 0.45) -> None:
        if not ENABLED or self.name == name:
            return
        self.stop()
        self.name = name
        self._stop = threading.Event()
        stop = self._stop

        def loop() -> None:
            path = self._path(name)
            dur = _duration(path)
            procs: list[subprocess.Popen] = []
            while not stop.is_set():
                p = subprocess.Popen(["afplay", "-v", f"{VOLUME * volume:.2f}", str(path)],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                procs = [q for q in procs if q.poll() is None] + [p]
                self.procs = procs
                # 끝나기 조금 전에 다음 재생을 겹쳐 시작 → 프로그램을 다시 띄우는 사이 끊김이 없다
                stop.wait(max(1.0, dur - 0.12) if dur else 10)
            for q in procs:
                if q.poll() is None:
                    q.terminate()

        self.thread = threading.Thread(target=loop, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self._stop.set()
        for q in getattr(self, "procs", []):
            if q.poll() is None:
                q.terminate()
        self.name = None


ambient = Ambient()


if __name__ == "__main__":  # 전부 한 번씩 들어 보기
    ENABLED = True
    _ensure()
    for n in _sounds():
        print(n, flush=True)
        play(n)
        time.sleep(0.9)
