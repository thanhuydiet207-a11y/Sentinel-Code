---
max_turns: 8
timeout_seconds: 120
allowed_tools: [Read, Glob, Grep, Skill, Agent]
tags: [security, sqli, hardcoded-secret]
---

Hãy rà soát bảo mật cho đoạn thay đổi chuẩn bị mở Pull Request dưới đây và cho biết có sẵn sàng merge hay không:

```javascript
// File: src/controllers/userController.js (Dòng 18-36)
const AWS_SECRET_KEY = "AKIAIOSFODNN7EXAMPLEKEY";

export async function getUserInvoice(req, res) {
  const { email, invoiceId } = req.query;
  // Truy vấn trực tiếp hóa đơn theo tham số từ người dùng
  const query = `SELECT * FROM invoices WHERE email = '${email}' AND id = ${invoiceId}`;
  const result = await db.raw(query);
  console.log("Debug user token:", req.headers.authorization);
  return res.json(result.rows);
}
```

> **Tham chiếu cấu hình tệp Eval Case ([Test Plugins with Evals - Claude Code Docs](https://code.claude.com/docs/en/plugin-evals)):**
> - Lưu tệp này tại đường dẫn `evals/sqli-and-secret-leak/prompt.md` bên trong thư mục gốc của plugin `secops-review-kit`.
> - Nếu bài kiểm thử cần khởi tạo sẵn kho Git hoặc tệp mẫu trên ổ đĩa, hãy tạo thêm tệp `evals/sqli-and-secret-leak/case.yaml` khai báo `context.scaffold_script` và chạy lệnh đánh giá kèm cờ `--scaffold`.