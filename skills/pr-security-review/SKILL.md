---
name: pr-security-review
description: Quét thay đổi Git hiện tại để kiểm tra lỗ hổng bảo mật (OWASP Top 10, lộ secret, lỗi phân quyền), hiệu năng truy vấn và độ phủ kiểm thử. Sử dụng khi người dùng yêu cầu review PR, kiểm tra diff trước khi commit, hoặc gõ lệnh /pr-security-review.
license: Apache-2.0
compatibility: Claude Code, Cursor, OpenAI Codex, GitHub Copilot (Agent Skills Open Standard)
allowed-tools: Read, Grep, Glob, Bash(git diff *), Bash(git status *), Bash(git log *)
argument-hint: "[base-branch-hoặc-đường-dẫn-file]"
---

# Quy trình rà soát bảo mật và chất lượng mã nguồn (PR Security & Quality Review)

Tài liệu kỹ năng này tuân thủ chuẩn mở [Agent Skills Specification](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview) và tích hợp các tính năng mở rộng của [Claude Code Skills](https://code.claude.com/docs/en/skills) như nạp ngữ cảnh động và phê duyệt công cụ theo lượt.

> **Lưu ý khả năng tương thích đa nền tảng:**
> - Nếu bạn dùng file này trên claude.ai hoặc qua Claude Skills API, hãy giữ lại các trường chuẩn và xóa trường mở rộng riêng của CLI là `argument-hint`.
> - Có thể thêm `context: fork` và `agent: security-auditor` vào frontmatter nếu muốn chạy trong Subagent độc lập.

## 1. Ngữ cảnh Git tự động nạp trước khi phân tích (Dynamic Context Injection)

Khi kỹ năng được kích hoạt trong Claude Code, các lệnh dưới đây sẽ tự động chạy trước và chèn kết quả trực tiếp vào prompt:

- **Trạng thái nhánh và tệp đang thay đổi:**
  !`git status --short --branch`
- **Danh sách tệp thay đổi kèm thống kê dòng mã:**
  !`git diff HEAD --stat`

## 2. Tham số đầu vào (`$ARGUMENTS`)

- Tham số người dùng truyền vào qua lệnh `/pr-security-review`: `$ARGUMENTS`
- Nếu `$ARGUMENTS` có giá trị (ví dụ: `main`, `origin/develop`, hoặc đường dẫn thư mục `src/auth/`), hãy ưu tiên đối chiếu diff theo phạm vi đó bằng lệnh `git diff $ARGUMENTS`.
- Nếu `$ARGUMENTS` để trống, hãy kiểm tra toàn bộ thay đổi chưa commit (`git diff HEAD`) hoặc commit gần nhất (`git show HEAD`).

## 3. Quy trình thực thi chuẩn (Progressive Disclosure)

Thực hiện tuần tự 4 bước dưới đây. Để tiết kiệm token, chỉ đọc các tệp tham chiếu khi phát hiện dấu hiệu liên quan:

1. **Phân loại phạm vi thay đổi:**
   - Lọc các tệp nhạy cảm liên quan đến xác thực, phân quyền, cấu hình hạ tầng, migration cơ sở dữ liệu và xử lý đầu vào của người dùng.
   - Bỏ qua các tệp lockfile (`package-lock.json`, `pnpm-lock.yaml`, `poetry.lock`) hoặc tài nguyên tĩnh trừ khi có thay đổi bất thường về nguồn gói.
2. **Kiểm tra an toàn thông tin và lỗ hổng mã nguồn:**
   - Rà soát khóa bí mật (API key, JWT secret, chuỗi kết nối DB), lỗi tiêm mã (SQL Injection, Command Injection, XSS, SSRF) và lỗi kiểm soát truy cập (IDOR, thiếu middleware xác thực).
   - Nếu dự án có thư mục `.claude/skills/pr-security-review/references/owasp-checklist.md`, hãy dùng công cụ `Read` để nạp danh mục kiểm tra chi tiết tương ứng với ngôn ngữ lập trình của dự án.
3. **Chạy kịch bản kiểm tra tự động (nếu có):**
   - Nếu có tệp `.claude/skills/pr-security-review/scripts/scan-secrets.sh`, hãy thực thi qua Bash và chỉ đưa kết quả tóm tắt vào báo cáo.
4. **Đánh giá độ phủ kiểm thử (Test Coverage Gap):**
   - Kiểm tra xem các nhánh logic mới hoặc bản vá lỗi đã có unit test / integration test đi kèm hay chưa.

## 4. Định dạng báo cáo đầu ra

Trình bày kết quả ngắn gọn, đi thẳng vào vị trí tệp và dòng mã (`đường_dẫn_tệp:số_dòng`):

| Mức độ | Vị trí (`File:Line`) | Vấn đề phát hiện | Cách khắc phục đề xuất |
| :--- | :--- | :--- | :--- |
| **[CRITICAL / HIGH]** | `src/...:42` | Mô tả ngắn gọn cơ chế gây lỗi hoặc lộ dữ liệu | Đoạn mã hoặc cấu hình sửa lỗi cụ thể |
| **[MEDIUM / LOW]** | `src/...:108` | Rủi ro hiệu năng (N+1 query, thiếu timeout) hoặc thiếu kiểm thử | Hướng tối ưu hoặc kịch bản test cần bổ sung |

- **Kết luận phát hành (Verdict):** Nêu rõ `SẴN SÀNG MERGE`, `CẦN SỬA LỖI TRƯỚC KHI MERGE`, hoặc `CHẶN PHÁT HÀNH (BLOCKER)` kèm tối đa 3 hành động ưu tiên nhất.
