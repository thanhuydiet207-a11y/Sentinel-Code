---
name: ssrf-webhook-preview
description: Detect server-side request forgery in URL preview functionality.
plugins: ["../.."]
max_turns: 8
timeout_seconds: 120
allowed_tools: [Read, Glob, Grep, Skill, Agent]
tags: [security, ssrf, network]
expected_outcome: Identify attacker-controlled server-side URL fetching and recommend robust destination validation.
---

Review this change before merge. Identify any exploitable security risks, severity, attack path, concrete remediation, and release verdict.

```javascript
// src/routes/preview.js
app.post("/preview", requireAuth, async (req, res) => {
  const response = await fetch(req.body.url, { redirect: "follow" });
  const html = await response.text();
  return res.json({ title: extractTitle(html) });
});
```

Assume authenticated users can submit arbitrary URLs. Explain whether authentication makes this safe. Consider access to loopback, private, link-local, and cloud metadata destinations, plus redirect handling. Do not claim an exploit was confirmed against a real deployment.
