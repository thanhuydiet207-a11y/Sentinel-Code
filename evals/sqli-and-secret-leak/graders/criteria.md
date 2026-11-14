---
type: llm
weight: 1.0
---

PASS if câu trả lời phát hiện đầy đủ cả 4 vấn đề bảo mật nghiêm trọng trong đoạn mã (`src/controllers/userController.js`):
1. Lộ khóa bí mật đặt cứng trong mã nguồn (`AWS_SECRET_KEY` theo chuẩn [OWASP Top 10:2025](https://top10.owasp.org/2025/0x00_2025-Introduction/)).
2. Lỗ hổng tiêm mã SQL (SQL Injection) do nối chuỗi trực tiếp biến `email` và `invoiceId` vào `db.raw(query)` mà không dùng truy vấn tham số hóa theo [SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html).
3. Lỗi kiểm soát truy cập hỏng (Broken Access Control / IDOR) khi truy vấn `invoiceId` trực tiếp từ `req.query` mà không đối chiếu quyền sở hữu của người dùng đang đăng nhập theo [OWASP Top 10 Index](https://cheatsheetseries.owasp.org/IndexTopTen.html).
4. Rò rỉ thông tin xác thực nhạy cảm (`req.headers.authorization`) ra nhật ký hệ thống (`console.log`) theo [REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html), đồng thời đưa ra kết luận chặn phát hành (`CHẶN PHÁT HÀNH` / `BLOCKER` / không cho phép merge).

FAIL if câu trả lời bỏ sót lỗi SQL Injection hoặc lỗi lộ `AWS_SECRET_KEY`, không cảnh báo việc in `authorization` token ra log, hoặc kết luận đoạn mã đã an toàn để merge.

---

> **Ghi chú mở rộng bộ chấm điểm ([Test Plugins with Evals - Claude Code Docs](https://code.claude.com/docs/en/plugin-evals)):**
> - Lưu tệp này tại `evals/sqli-and-secret-leak/graders/criteria.md`.
> - Để kiểm tra tự động (không tốn phí gọi mô hình chấm điểm) việc Claude có kích hoạt đúng kỹ năng `pr-security-review` hay không, hãy tạo thêm một tệp thứ hai tại `evals/sqli-and-secret-leak/graders/skill-invoked.md` chỉ chứa phần frontmatter sau:
>
> ```yaml
> ---
> type: tool_used
> tool: Skill
> input_match: pr-security-review
> ---
> ```