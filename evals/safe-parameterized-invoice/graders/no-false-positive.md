---
type: llm
weight: 2
---
PASS if the review correctly states that the shown SQL query uses bound parameters and ties invoice ownership to req.user.id, so this snippet does not demonstrate SQL injection or IDOR. It should avoid a blanket claim that the whole application is secure and may note that middleware and database behavior are outside the snippet. FAIL if it reports SQL injection or IDOR in the shown query, or asserts full-application security without evidence.
