---
type: llm
weight: 2
---
PASS if the review identifies SSRF from fetching the user-controlled req.body.url on the server, explains that authentication does not make arbitrary destinations safe, and recommends a robust allowlist or strict scheme/host/IP validation that blocks loopback, private, link-local and metadata ranges. It must address redirects so a permitted URL cannot redirect to a blocked destination, and should mention DNS resolution/rebinding considerations where relevant. It must not claim an actual production compromise was observed. FAIL if SSRF is missed or the fix only checks that the user is authenticated.
