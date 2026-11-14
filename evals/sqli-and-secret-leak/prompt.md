---
name: sqli-and-secret-leak
description: Detect SQL injection and sensitive-data logging without misclassifying an explicit fake key.
plugins: ["../.."]
max_turns: 8
timeout_seconds: 120
allowed_tools: [Read, Glob, Grep, Skill, Agent]
tags: [security, sqli, secret-leak, regression]
expected_outcome: Identify SQL injection and authorization-token logging; treat the AWS-looking value as an explicit test placeholder, not a proven live credential.
---

Hãy rà soát bảo mật đoạn code chuẩn bị mở Pull Request dưới đây. Nêu mức độ nghiêm trọng, vị trí, đường khai thác, cách sửa và kết luận có nên merge hay không.

```javascript
// src/controllers/userController.js
// This is a deliberately fake test marker, not a production credential.
const AWS_SECRET_KEY = "AKIAIOSFODNN7EXAMPLEKEY";

export async function getUserInvoice(req, res) {
  const { email, invoiceId } = req.query;
  const query = `SELECT * FROM invoices WHERE email = '${email}' AND id = ${invoiceId}`;
  const result = await db.raw(query);
  console.log("Debug user token:", req.headers.authorization);
  return res.json(result.rows);
}
```

Không được khẳng định chuỗi AWS mẫu là credential đang hoạt động. Hãy phân biệt rõ dữ liệu giả dùng trong test với hai vấn đề bảo mật thực sự trong đoạn code.
