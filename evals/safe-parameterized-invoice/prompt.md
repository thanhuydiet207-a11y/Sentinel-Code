---
name: safe-parameterized-invoice
description: Negative control for secure parameterized query and ownership check.
plugins: ["../.."]
max_turns: 8
timeout_seconds: 120
allowed_tools: [Read, Glob, Grep, Skill, Agent]
tags: [security, negative-control, false-positive]
expected_outcome: Do not report SQL injection or IDOR; identify the parameterized query and principal-bound ownership check as positive controls.
---

Review this change for security and code-quality issues. Be precise and do not invent vulnerabilities.

```javascript
// src/routes/invoices.js
app.get("/invoices/:invoiceId", requireAuth, async (req, res) => {
  const result = await db.query(
    "SELECT id, total FROM invoices WHERE id = $1 AND user_id = $2",
    [req.params.invoiceId, req.user.id]
  );
  return res.json(result.rows[0] ?? null);
});
```

State whether the shown query has SQL injection or broken object-level authorization. Mention any limitations that cannot be established from this snippet, and avoid claiming that the entire application is secure.
