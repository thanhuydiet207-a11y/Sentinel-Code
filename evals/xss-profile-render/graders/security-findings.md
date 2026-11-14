---
type: llm
weight: 2
---
PASS if the review identifies stored XSS because user-editable profile.bio reaches React dangerouslySetInnerHTML without sanitization, explains that an attacker can store executable markup/script payloads that execute in viewers' browsers, and recommends avoiding raw HTML rendering or applying a vetted allowlist HTML sanitizer before the sink. It must distinguish this from ordinary JSX text interpolation, which React escapes by default. FAIL if the raw HTML sink is missed or the review claims normal JSX text interpolation is inherently XSS.
