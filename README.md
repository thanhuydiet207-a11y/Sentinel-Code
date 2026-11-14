# SecOps PR & Security Auditor Kit (`secops-review-kit`)

Gói mở rộng ([Claude Code Plugin](https://code.claude.com/docs/en/plugins/overview)) chuẩn hóa quy trình rà soát bảo mật Pull Request, kiểm toán mã nguồn độc lập theo chuẩn [OWASP Top 10:2025](https://top10.owasp.org/2025/0x00_2025-Introduction/) và tự động chặn các thao tác đẩy mã không an toàn ngay trong [Claude Code](https://code.claude.com/docs/en/overview).

## 1. Các thành phần tích hợp trong Plugin

Plugin được đóng gói theo chuẩn [Plugin Manifest Specification](https://code.claude.com/docs/en/plugins/manifest-reference) và bao gồm 4 nhóm thành phần phối hợp chặt chẽ:

| Thành phần | Định danh / Đường dẫn trong Plugin | Chức năng chính | Tài liệu kỹ thuật |
| :--- | :--- | :--- | :--- |
| **Skill** | `/secops-review-kit:pr-security-review` (`skills/pr-security-review/SKILL.md`) | Tự động nạp `git status`, `git diff` và đối chiếu danh mục lỗ hổng theo cơ chế nạp ngữ cảnh lũy tiến (Progressive Disclosure). | [Claude Code Skills](https://code.claude.com/docs/en/skills) |
| **Subagent** | `secops-review-kit:security-auditor` (`agents/security-auditor.md`) | Chạy trong cửa sổ ngữ cảnh cô lập với quyền chỉ đọc (`Read`, `Grep`, `Glob`) để truy vết luồng dữ liệu từ điểm đầu vào đến điểm thực thi mà không làm đầy phiên chính. | [Claude Code Subagents](https://code.claude.com/docs/en/sub-agents) |
| **Lifecycle Hooks** | `PreToolUse` & `PostToolUse` (`hooks/hooks.json` + `scripts/verify-before-push.sh`) | Chặn đẩy trực tiếp lên nhánh `main`/`master`/`production`, quét khóa bí mật rò rỉ trước khi `git push` và tự động chạy Prettier sau khi sửa tệp. | [Claude Code Hooks](https://code.claude.com/docs/en/hooks) |
| **MCP Servers** | `github`, `sentry`, `postgres-readonly` (`.mcp.json`) | Cung cấp kết nối chuẩn hóa tới GitHub PRs, nhật ký lỗi Sentry và truy vấn cơ sở dữ liệu chỉ đọc phục vụ kiểm toán. | [Claude Code MCP](https://code.claude.com/docs/en/mcp) |

## 2. Cấu trúc thư mục hoàn chỉnh

```text
secops-review-kit/
├── .claude-plugin/ (plugin.json, marketplace.json)
├── .github/workflows/claude-secops-review.yml
├── agents/security-auditor.md
├── skills/pr-security-review/SKILL.md
├── skills/pr-security-review/references/owasp-checklist.md
├── hooks/hooks.json
├── hooks/register.js
├── scripts/verify-before-push.sh
├── evals/sqli-and-secret-leak/ (prompt and graders)
├── tests/secops-mod.test.ts
├── .mcp.json
└── README.md
```

## 3. Cài đặt từ GitHub Marketplace nội bộ

```text
/plugin marketplace add Thanhuydiet207-a11y/Sentinel-Code
/plugin install secops-review-kit@internal-secops-marketplace
```

Hoặc từ Terminal:

```bash
claude plugin marketplace add Thanhuydiet207-a11y/Sentinel-Code
claude plugin install secops-review-kit@internal-secops-marketplace --scope project
```

Cấp quyền thực thi cho hook và khai báo các biến môi trường cần thiết cho MCP:

```bash
chmod +x scripts/verify-before-push.sh
export GITHUB_PERSONAL_ACCESS_TOKEN="<your-token>"
export SECOPS_READONLY_DATABASE_URL="<read-only-postgres-connection>"
```

## 4. Chạy thử và kiểm thử

```bash
claude plugin validate --strict .
claude --plugin-dir .
claude plugin eval . --judge-model sonnet
```

Workflow GitHub Actions cần secret `ANTHROPIC_API_KEY` trong Settings → Secrets and variables → Actions. Không lưu token hoặc thông tin kết nối thật trong repository.
