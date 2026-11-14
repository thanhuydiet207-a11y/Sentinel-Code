---
name: xss-profile-render
description: Detect stored cross-site scripting from unsafe HTML rendering.
plugins: ["../.."]
max_turns: 8
timeout_seconds: 120
allowed_tools: [Read, Glob, Grep, Skill, Agent]
tags: [security, xss, frontend]
expected_outcome: Identify stored XSS from rendering untrusted profile content as raw HTML.
---

Review this frontend change for security. Explain the source-to-sink path, severity, remediation, and whether it should merge.

```tsx
// src/components/ProfileBio.tsx
export function ProfileBio({ profile }: { profile: { bio: string } }) {
  return <section dangerouslySetInnerHTML={{ __html: profile.bio }} />;
}
```

Assume profile.bio is user-editable and stored in the database. Distinguish this raw HTML sink from ordinary React text interpolation, which is escaped by default. Do not claim all React rendering is vulnerable.
