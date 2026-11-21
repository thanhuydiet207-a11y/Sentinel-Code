# Danh mục tham chiếu kiểm toán bảo mật OWASP (Progressive Disclosure Reference)

Tài liệu tham chiếu này được nạp theo cơ chế lũy tiến khi kỹ năng `pr-security-review` hoặc subagent `security-auditor` phát hiện thay đổi mã nguồn liên quan đến xác thực, cơ sở dữ liệu, API hoặc cấu hình hạ tầng. Các tiêu chí dưới đây đối chiếu trực tiếp từ [OWASP Top 10:2025](https://top10.owasp.org/2025/0x00_2025-Introduction/), [OWASP Top 10:2021](https://owasp.org/Top10/), [OWASP API Security Top 10](https://api-security.owasp.org/) và bộ tài liệu [OWASP Cheat Sheet Series](https://cheatsheetseries.owasp.org/).

## 1. Bảng ánh xạ nhanh rủi ro theo loại tệp thay đổi

| Hạng mục rủi ro OWASP | Dấu hiệu nhận diện trong mã nguồn (Code Smells) | Tiêu chuẩn kiểm tra & Cách khắc phục bắt buộc | Tài liệu tham chiếu chuẩn |
| :--- | :--- | :--- | :--- |
| **A01: Kiểm soát truy cập hỏng (Broken Access Control)** | Truy vấn bản ghi trực tiếp bằng `req.params.id` hoặc `req.body.userId` mà không kiểm tra chủ sở hữu (`owner_id == current_user.id`); thiếu middleware phân quyền trên route quản trị. | Áp dụng nguyên tắc từ chối mặc định (Deny by Default) và xác minh quyền sở hữu tài nguyên ở tầng dịch vụ hoặc cơ sở dữ liệu trên mọi điểm cuối. | [OWASP Top 10 Index](https://cheatsheetseries.owasp.org/IndexTopTen.html) |
| **A02 & A04: Lỗi cấu hình và Mật mã học (Misconfiguration & Crypto)** | Bật `CORS: *` đi kèm `credentials: true`; lưu mật khẩu bằng MD5/SHA1; khóa bí mật hoặc JWT secret đặt cứng trong mã nguồn. | Dùng thuật toán băm thích ứng (Argon2id hoặc bcrypt), ép buộc giao thức TLS và đọc khóa bí mật từ trình quản lý biến môi trường. | [OWASP Top 10:2025](https://top10.owasp.org/2025/0x00_2025-Introduction/) |
| **A03 & A05: Lỗi tiêm mã (SQL / Command / Template Injection)** | Nối chuỗi trực tiếp vào câu lệnh SQL (`SELECT * FROM users WHERE email = '${email}'`), hoặc truyền biến người dùng vào `exec()`, `spawn()`, `eval()`. | Bắt buộc sử dụng truy vấn tham số hóa (Parameterized Queries / Prepared Statements) và xác thực đầu vào theo danh sách trắng (Allow-list). | [SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html) |
| **A07: Lỗi định danh và xác thực (Authentication Failures)** | Token không có thời hạn (`exp`), không thu hồi phiên sau khi đổi mật khẩu, hoặc trả về thông báo lỗi tiết lộ tài khoản nào tồn tại trong hệ thống. | Xoay vòng phiên đăng nhập (Session Rotation) sau khi xác thực lại và chuẩn hóa thông báo lỗi đăng nhập chung. | [Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html) |
| **API Security & REST Endpoints** | Truyền API key hoặc token xác thực trên chuỗi truy vấn URL (`?api_key=...`); thiếu giới hạn tần suất (Rate Limiting) hoặc trả về toàn bộ trường nhạy cảm của đối tượng DB. | Chỉ truyền thông tin xác thực qua HTTP Header trên kết nối HTTPS và lọc trường đầu ra bằng DTO/Schema tường minh. | [REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html) |
| **Kiểm tra đầu vào và Chống XSS / SSRF** | Chèn trực tiếp dữ liệu người dùng vào DOM (`dangerouslySetInnerHTML`, `v-html`) hoặc gọi `fetch(userProvidedUrl)` tới dải mạng nội bộ (`127.0.0.1`, `169.254.169.254`). | Mã hóa đầu ra theo ngữ cảnh (Context-aware Output Encoding) và chặn truy cập tới địa chỉ IP nội bộ/metadata đám mây khi gọi URL bên ngoài. | [Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html) |

## 2. Quy tắc kiểm tra theo mẫu biểu thức chính quy (Grep Patterns)

Trong quá trình thực thi kỹ năng hoặc kiểm toán qua Subagent, hãy dùng công cụ `Grep` với các mẫu dưới đây trên những tệp vừa thay đổi:

1. **Phát hiện nối chuỗi truy vấn SQL và ORM thô:**
   - Mẫu tìm kiếm: `(query|execute|raw)\s*\(\s*[`"'].*\$\{` hoặc `SELECT .* FROM .* \+`
   - Yêu cầu: Chuyển toàn bộ sang biến ràng buộc (`$1`, `?`, `:param`) hoặc phương thức truy vấn an toàn của ORM.
2. **Phát hiện thực thi lệnh hệ thống nguy hiểm:**
   - Mẫu tìm kiếm: `(child_process\.exec|os\.system|subprocess\.Popen\(.*shell\s*=\s*True|eval\()`
   - Yêu cầu: Thay bằng phương thức truyền mảng đối số không qua shell (`execFile`, `spawn` với mảng tham số) và kiểm tra kiểu dữ liệu nghiêm ngặt.
3. **Phát hiện lộ thông tin nhạy cảm trên URL hoặc Log:**
   - Mẫu tìm kiếm: `(console\.log|logger\.(info|debug|error)).*(password|token|secret|authorization)`
   - Yêu cầu: Che dấu (mask/redact) toàn bộ trường nhạy cảm trước khi ghi nhật ký hệ thống.
