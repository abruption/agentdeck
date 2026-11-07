#!/bin/bash
# Claude Code statusline 래퍼: 입력 JSON(rate_limits 포함)을 대시보드용으로 저장한 뒤,
# 인자로 받은 기존 statusline 명령에 그대로 넘긴다. 인자가 없으면 저장만 하고 아무것도 출력하지 않는다.
#
# ~/.claude/settings.json 예:
#   "statusLine": {"type": "command", "command": "/path/to/statusline-tee.sh <기존 statusline 명령>"}
input=$(cat)
dir="$HOME/.cache/d200"
mkdir -p "$dir"
tmp="$dir/.claude_status.$$"
printf '%s' "$input" > "$tmp" && mv -f "$tmp" "$dir/claude_status.json"
if [ $# -gt 0 ]; then
  printf '%s' "$input" | "$@"
fi
