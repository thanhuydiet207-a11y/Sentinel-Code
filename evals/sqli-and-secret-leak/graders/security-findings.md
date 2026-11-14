---
type: llm
weight: 2
---
PASS only if the review identifies both (1) SQL injection caused by interpolating untrusted email and invoiceId into db.raw, and (2) disclosure of the Authorization header through logging. It must recommend parameterized queries and must not log bearer credentials. It must explicitly avoid claiming that the AWS-looking value is a live credential because the prompt labels it as a deliberately fake test marker. It should recommend verifying/removing any real credential if one is ever substituted. FAIL if either real issue is missed, the fix is materially incorrect, or the fake marker is asserted to be an active key.
