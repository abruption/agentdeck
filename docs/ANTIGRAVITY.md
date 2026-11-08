# Antigravity quota via CLI (Draft / 검증 대기)

한국어: 기존 `agy.enabled` / `agy.host` 설정과 SSH·원격 Python 구조를 유지하고,
공식 CLI의 읽기 전용 JSON 명령으로 한도를 조회합니다. 토큰 파일을 직접 읽거나
내부 API로 자동 대체하지 않습니다. CLI와 원격 호스트가 없는 개발 환경에서
작성했으므로 **실제 JSON 스키마와 버전 문자열은 아직 검증하지 못했습니다**.
아래 fixture는 합성 예시이며 실제 CLI 출력의 증거가 아닙니다. 병합 전에
인증된 설치에서 스키마와 5시간·주간 한도, 모델 그룹, 리셋 시각을 확인해야 합니다.

## Interface and requirements

- Keep `agy.enabled` and `agy.host` in the ignored `config.json` as before.
- The existing remote host needs Python 3, an authenticated Antigravity CLI,
  and working noninteractive SSH. agentdeck installs nothing and does not log in.
- The remote process prepends `~/.local/bin` and `/opt/homebrew/bin` to PATH,
  preserving the previous installation locations and inherited PATH.
- It first runs `agy --version` (10 seconds), then, only for a recognized stable
  version >= 1.1.11, `agy -p /usage --output-format json` (60 seconds).
  Recognized version text is `1.2.15`, `v1.2.15`, or `agy v1.2.15` (including
  optional whitespace). Other formats fail closed pending live verification.
- SSH uses BatchMode, no TTY, a 5-second connect timeout and a 90-second total
  subprocess timeout. CLI stdin is closed; stderr is not forwarded or logged.
- Missing CLI, old/unknown version, authentication errors, nonzero exit codes,
  timeouts, invalid JSON and unsupported payloads return `None`. There is no
  credential-file access, `agy models` retry, or private-endpoint fallback.

This is an official **CLI JSON interface**, not a new public REST API.
[CLI changelog](https://antigravity.google/docs/changelog) v1.1.11 (2026-08-07)
announces structured output for read-only print-mode commands without agent
turns, quota consumption or conversation creation. v1.2.15 (2026-10-02) retains
UTC reset timestamps for piped/JSON output.
The [/usage reference](https://antigravity.google/docs/cli/commands/usage/)
describes model quotas; the [headless reference](https://antigravity.google/docs/cli/headless/)
also describes ordinary agent token-count `usage`, which is **not** quota.

## Provisional parser contract — merge blocker

The public docs reviewed do not specify quota JSON fields. The draft parser
retains the existing `groups[].displayName` / `groups[].buckets[]` field shape
as a **hypothesis**, not as a verified official CLI schema. It accepts no guessed
wrapper or text-report fallback. A different actual response will yield `None`.
`tests/fixtures/agy_quota.json` is entirely synthetic, not captured personal data.

Each bucket has `window` (`5h` or `weekly`), a numeric `remainingFraction` in
[0, 1], and optional/null `resetTime`. Zero is exhausted, not missing. Missing or
null fractions, `disabled: true`, and `enabled: false` are omitted. An empty usable
result is unavailable. Invalid fractions, unknown windows, malformed structure,
and invalid or timezone-naive reset values invalidate the result. Aware reset
times, including `Z` and explicit offsets, normalize to UTC. No reset means `None`.
Model-group names and ordering are retained in the existing `list[Bucket] | None`
contract. The unchanged dashboard currently uses the last bucket for each window
across groups; this draft does not add model selection or change that UI policy.

Before considering the draft ready:

1. On an already authenticated supported installation, privately check
   `agy --version` and `agy -p /usage --output-format json`. Use the same
   noninteractive SSH/PATH context as agentdeck. Do not paste raw output in issues.
2. Compare field names, envelopes, fraction units, unavailable/disabled values,
   model groups, both windows, and reset timezone semantics. Update the parser and
   synthetic fixtures to the observed contract and record the CLI version only.
3. Verify actual SSH success/failure and dashboard display; test a real D200
   separately. Do not treat mocked subprocess tests as live CLI/hardware evidence.

## Local checks

`python -B -m unittest discover -s tests -v` runs without third-party packages,
network, SSH, CLI authentication, or hardware. It exercises parsing and both
subprocess layers (the remote script is executed with a mocked `subprocess.run`).

In the development environment, `agy` and a configured remote host were absent.
`python -B demo.py <output-directory>` was attempted but stopped at
`ModuleNotFoundError: No module named 'hid'`; no dependency was installed.
Full demo rendering, native macOS behavior, live CLI/SSH and D200 hardware remain
unverified. The repository did not have a GitHub Actions workflow at the base
commit; local test success is not CI success.
