"""페이지를 PNG 로 그려본다 (장치 없이). 사용: .venv/bin/python preview.py <출력폴더>"""

from __future__ import annotations

import io
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from PIL import Image, ImageDraw, ImageFont

from d200 import FONT_PATH, render_icon
from dashboard import collect_llms
from pages import nav, page_grid, page_studio, page_summary
from remote_herdr import studio_state


def sheet(buttons, title: str, out: str) -> None:
    pad, cell = 10, 196
    img = Image.new("RGB", (5 * (cell + pad) + pad, 3 * (cell + pad) + pad + 40), "#000")
    d = ImageDraw.Draw(img)
    d.text((pad, 8), title, font=ImageFont.truetype(FONT_PATH, 24), fill="#c0caf5")
    for i, b in buttons.items():
        img.paste(Image.open(io.BytesIO(render_icon(b))), (pad + (i % 5) * (cell + pad), 40 + pad + (i // 5) * (cell + pad)))
    x, y = pad + 3 * (cell + pad), 40 + pad + 2 * (cell + pad)
    d.rounded_rectangle((x, y, x + 2 * cell + pad, y + cell), 16, fill="#0f0f14", outline="#2a2a3a")
    d.text((x + cell + pad / 2, y + cell / 2), datetime.now().strftime("%H:%M  %m/%d"),
           font=ImageFont.truetype(FONT_PATH, 48), fill="#c0caf5", anchor="mm")
    img.save(out)


if __name__ == "__main__":
    out = sys.argv[1]
    now = datetime.now(timezone.utc)
    llms, studio = collect_llms(ThreadPoolExecutor(4)), studio_state()
    sheet({**page_summary(llms, studio, now), **nav(1, 3, 80)}, "1 · 요약", f"{out}/p1.png")
    sheet({**page_grid(llms, now), **nav(2, 3, 80)}, "2 · 한도 그리드", f"{out}/p2.png")
    sheet({**page_studio(studio), **nav(3, 3, 80)}, "3 · 스튜디오 (Herdr 실데이터)", f"{out}/p3.png")
