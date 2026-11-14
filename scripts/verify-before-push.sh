#!/usr/bin/env bash
# ==============================================================================
# Kịch bản Hook PreToolUse: verify-before-push.sh
# Đường dẫn trong Plugin: scripts/verify-before-push.sh
# Tham chiếu tài liệu:
#   - Claude Code Hooks Reference: https://code.claude.com/docs/en/hooks
#   - Automate Actions with Hooks: https://code.claude.com/docs/en/hooks-guide
#   - Plugin Components Guide: https://code.claude.com/docs/en/plugins/components
#
# Cơ chế hoạt động:
#   1. Nhận payload JSON của sự kiện PreToolUse từ Claude Code qua stdin.
#   2. Chặn (exit 2 kèm thông báo stderr) nếu lệnh git push đẩy thẳng lên nhánh
#      bảo vệ (main / master / production) mà không qua Pull Request.
#   3. Quét nhanh các commit sắp đẩy để phát hiện khóa bí mật (AWS, Private Key,
#      API Token) trước khi cho phép thực thi.
# ==============================================================================

set -euo pipefail
INPUT_JSON="$(cat)"
COMMAND_STR="$(printf '%s' "$INPUT_JSON" | jq -r '.tool_input.command // empty')"

if [[ ! "$COMMAND_STR" =~ git[[:space:]]+push ]]; then
  exit 0
fi

CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")"
if [[ "$COMMAND_STR" =~ [[:space:]](main|master|production)([[:space:]]|$) ]] || \
   [[ "$CURRENT_BRANCH" =~ ^(main|master|production)$ ]]; then
  cat >&2 <<EOF
[SecOps Hook Chặn Lệnh] Không được phép chạy 'git push' trực tiếp lên nhánh bảo vệ (${CURRENT_BRANCH:-main/master}).
Hãy tạo nhánh tính năng (feature branch) và mở Pull Request, sau đó chạy lệnh /secops-review-kit:pr-security-review để kiểm toán trước khi merge.
EOF
  exit 2
fi

SECRET_PATTERN='(AKIA[0-9A-Z]{16}|-----BEGIN (RSA|EC|OPENSSH|PRIVATE) KEY-----|ghp_[0-9a-zA-Z]{36}|sk-ant-[0-9a-zA-Z\\-_]{20,})'
if git diff @{u}..HEAD 2>/dev/null | grep -E -q "$SECRET_PATTERN"; then
  cat >&2 <<'EOF'
[SecOps Hook Chặn Lệnh] Phát hiện chuỗi có định dạng khóa bí mật (AWS Key, Private Key, GitHub/Anthropic Token) trong các commit chuẩn bị push.
Hãy xóa khóa bí mật khỏi lịch sử commit và chuyển sang biến môi trường trước khi đẩy mã nguồn.
EOF
  exit 2
fi
exit 0
