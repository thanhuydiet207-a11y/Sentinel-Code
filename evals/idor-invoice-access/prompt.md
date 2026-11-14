---
name: idor-invoice-access
description: Detect missing object-level authorization on invoice access.
plugins: ["../.."]
max_turns: 8
timeout_seconds: 120
allowed_tools: [Read, Glob, Grep, Skill, Agent]
tags: [security, idor, authorization]
expected_outcome: Identify IDOR/BOLA because the query trusts a user-supplied account identifier without binding it to the authenticated principal.
---

Review this proposed API change for security issues. Explain exploitability, severity, exact vulnerable operation, remediation, and merge verdict.

```javascript
// src/routes/invoices.js
app.get("/users/:userId/invoices/:invoiceId", requireAuth, async (req, res) => {
  const { userId, invoiceId } = req.params;
  const result = await db.query(
    "SELECT id, total, status FROM invoices WHERE id = $1 AND user_id = $2",
    [invoiceId, userId]
  );
  return res.json(result.rows[0] ?? null);
});
```

The route authenticates the caller, but the request controls userId. Determine whether authentication alone proves the caller may read that user's invoice. Do not invent missing code or claim SQL injection when parameters are bound.
