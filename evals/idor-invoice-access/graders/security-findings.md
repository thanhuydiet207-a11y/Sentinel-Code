---
type: llm
weight: 2
---
PASS if the review identifies broken object-level authorization (IDOR/BOLA): an authenticated caller can replace userId with another account's identifier and retrieve that invoice because the query trusts req.params.userId rather than req.user.id or an authorization check. The recommended fix must bind invoice ownership to the authenticated principal (for example WHERE id = $1 AND user_id = $2 with req.user.id), or perform an equivalent explicit authorization check. It must not incorrectly label the parameterized query as SQL injection. FAIL if the ownership flaw is missed or the remediation still trusts the request-supplied userId.
