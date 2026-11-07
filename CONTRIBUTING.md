# 기여 가이드 / Contributing

agentdeck은 계속 기능을 늘려가는 오픈소스 프로젝트예요. **새 페이지, 데이터 소스, 번역, 버그 제보, 문서 수정** 모두 환영합니다.
agentdeck keeps growing, and contributions of every size are welcome: **new pages, data sources, translations, bug reports, docs**. (English below.)

## 한국어

### 시작하기
1. 저장소를 포크하고 클론한 뒤 [가이드](docs/GUIDE.md)대로 설치하세요.
2. 장치가 없어도 **화면 작업은 할 수 있어요.** `.venv/bin/python demo.py /tmp/out`을 실행하면 가짜 데이터로 모든 페이지를 PNG와 GIF로 그려줍니다.
3. 브랜치를 만들어 작업하고 PR을 보내주세요.

### 구조 한눈에 보기
| 파일 | 하는 일 |
|---|---|
| `d200.py` | 장치 드라이버. 버튼 하나는 `Button`(header, title, sub, 색, 게이지 등)으로 표현해요 |
| `pages.py` | 페이지 함수: 데이터를 받아 `{칸 번호: Button}`을 돌려줘요. 칸 0~9는 내용, 10~12는 하단 버튼 |
| `dashboard.py` | 갱신 루프, 버튼 입력 처리, 페이지 전환 |
| `clock.py` | 오른쪽 아래 넓은 칸(458×196) 이미지 |
| `i18n.py` | 화면 문구 번역 (`ui_lang`) |
| `config.py` | `config.json` 읽기. 선택 기능은 여기서 켜고 꺼요 |

### 새 페이지 추가하기
1. `pages.py`에 `def page_xxx(data) -> dict[int, Button]` 함수를 만드세요. 칸 0~9만 채우면 돼요.
2. `dashboard.py`의 `render()`에 페이지 번호 분기를 추가하고 `PAGES`를 늘리세요.
3. 데이터를 가져오는 부분은 별도 모듈로 분리하고, 실패하면 예외 대신 `None`을 돌려주세요. 대시보드가 멈추면 안 돼요.
4. 화면 문구는 한국어로 쓰고 `i18n.py`의 `WORDS`에 영어를 추가하세요.
5. `demo.py`에 가짜 데이터 예시를 추가하면 README 이미지도 함께 만들어져요.

### 지켜주세요
- **개인 정보나 시크릿을 코드에 넣지 마세요.** 컴퓨터 이름, 계정, 토큰은 `config.json`에 둡니다(git 제외).
- **지우거나 되돌릴 수 없는 동작**은 반드시 "길게 두 번 눌러 확인"을 거치게 해주세요.
- 공식 문서가 없는 API를 쓴다면 README에 그 사실을 적어주세요.
- 커밋 메시지는 `feat:`, `fix:`, `docs:` 같은 [Conventional Commits](https://www.conventionalcommits.org) 형식을 권장해요.

## English

### Getting started
1. Fork and clone, then install following the [guide](docs/GUIDE.en.md).
2. **No device? You can still work on screens.** `.venv/bin/python demo.py /tmp/out` renders every page as PNG/GIF from mock data.
3. Work on a branch and open a PR.

### Layout at a glance
| File | Role |
|---|---|
| `d200.py` | Device driver. One key is a `Button` (header, title, sub, colours, gauges…) |
| `pages.py` | Page functions: data in, `{tile index: Button}` out. Tiles 0-9 are content, 10-12 the bottom buttons |
| `dashboard.py` | Refresh loop, input handling, page switching |
| `clock.py` | The wide bottom-right tile (458×196) |
| `i18n.py` | On-device translations (`ui_lang`) |
| `config.py` | Reads `config.json`; optional features are toggled here |

### Adding a page
1. Add `def page_xxx(data) -> dict[int, Button]` to `pages.py`. Fill tiles 0-9.
2. Add a branch for the page number in `render()` in `dashboard.py` and bump `PAGES`.
3. Put data fetching in its own module and return `None` on failure instead of raising; the dashboard must never stop.
4. Write labels in Korean and add the English to `WORDS` in `i18n.py`.
5. Add mock data to `demo.py` so the README images get generated too.

### Please
- **Never commit personal info or secrets.** Hostnames, accounts and tokens belong in `config.json` (git-ignored).
- Anything **destructive or irreversible** must go through the "hold twice to confirm" pattern.
- If you rely on an undocumented API, say so in the README.
- [Conventional Commits](https://www.conventionalcommits.org) (`feat:`, `fix:`, `docs:`) are preferred.
