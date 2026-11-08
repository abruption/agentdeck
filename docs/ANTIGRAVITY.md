# Antigravity quota via CLI (Draft / 검증 대기)

한국어: 기존 `agy.enabled` / `agy.host` 설정과 SSH·원격 Python 구조를 유지하고,
공식 CLI의 읽기 전용 JSON 명령으로 한도를 조회합니다. 토큰 파일을 직접 읽거나
내부 API로 자동 대체하지 않습니다. 사용자 제공 성공 스크린샷에서 확인한
`status: SUCCESS`, `command.data.groups[].name`, `remaining_fraction`, `reset_time` 구조를
반영했습니다. 이미지에는 동일 명령과 성공 상태가 보이며, 버전과 종료 코드는
보이지 않습니다. 버전은 별도 실행으로 확인했습니다.
Mac에서 agy 1.5.3은 확인했지만 자동 실행 두 번은 모두 exit 1이었습니다.
첫 실행은 stdout이 비었고 후속 실행은 JSON 파싱이 가능했으나 실패 원인은
미확정입니다. 스크린샷 구조 증거와 자동 실행 성공 검증은 다릅니다.
fixture의 모든 값은 합성이며 사용자 출력·이미지는 저장하거나 게시하지 않습니다.

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

## Screenshot-derived parser contract — end-to-end validation pending

The user-provided success screenshot shows root `status: "SUCCESS"` and
`command.data.groups`, alongside `command.name` and `command.data.description`,
with group `name` / `description` / `buckets` and bucket `id` / `name` / `window` /
`remaining_fraction` / `reset_time`. This replaces the earlier camelCase hypothesis.
The screenshot directly shows `agy -p /usage --output-format json` and SUCCESS.
It does not show a CLI version or exit code; version 1.5.3 was confirmed separately.
This is field-structure evidence, not a successful automated collector run.
`tests/fixtures/agy_quota.json` uses those field names with entirely synthetic
values; the screenshot and personal response were not committed.

The parser requires root `status == "SUCCESS"`, no `error` key, and a `command.data.groups` list. Root-level groups are not a fallback.
It ignores unrelated `conversation_id`, `response`, `duration_seconds`,
`num_turns`, and `usage` metadata rather than requiring them. In
particular, response text and token usage are never alternate quota sources.
Command name/description, group descriptions and bucket IDs/names are not needed by the existing Bucket
interface and may be omitted. Group names, bucket lists and known windows are
validated. These sparse/disabled-value policies are defensive adapter behavior,
not claims that every such variation appeared in the screenshot.

Each bucket has `window` (`5h` or `weekly`), a numeric `remaining_fraction` in
[0, 1], and optional/null `reset_time`. Zero is exhausted, not missing. Missing or
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

Automated macOS checks confirmed agy 1.5.3. The first /usage invocation exited 1
with empty stdout; one subsequent invocation also exited 1 but its stdout parsed
as JSON. JSON parseability does not mean success. The cause is undetermined;
workspace trust, permissions and authentication are not established diagnoses.
Nonzero exits are rejected even if stdout contains valid JSON. The separate
success screenshot supplies the schema evidence described above.
`python -B demo.py <output-directory>` was attempted but stopped at
`ModuleNotFoundError: No module named 'hid'`; no dependency was installed.
Full demo rendering, successful automated quota retrieval, end-to-end macOS
dashboard behavior, actual SSH execution and D200 hardware remain unverified. The repository did not have a GitHub Actions workflow at the base
commit; local test success is not CI success.
