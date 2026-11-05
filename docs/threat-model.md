# Threat model

First written before the code, so the design answered it. Reviewed against the built system on
1 November 2026. The status column says what is done, what is only partly done, and what depends
on something outside this repository.

## What we protect

- The model API key and the ENTSO-E token
- The spend budget
- The home server and network
- The integrity of the brief: it must not say what an attacker wants it to say

## Who the attacker is

Anyone on the internet who can reach the endpoint. Assume they are curious, bored,
or after free compute. Assume they read this file.

## Untrusted inputs

| Input | Risk |
|---|---|
| User question | Prompt injection, jailbreaks, off-topic use, giant inputs |
| ENTSO-E response | Low risk, but treated as data, never as instructions |
| Model output | May contain injected content, markup or links. Untrusted until validated |
| Public datasets used for testing | Contain text unrelated to this project. Kept out of the repository; only counts are stored |

## Threats, mitigations as built, and evidence

| Threat | Mitigation as built | Evidence | Status |
|---|---|---|---|
| Prompt injection to change behaviour or leak the system prompt | The model has no tools and no secrets. Question and data are passed as delimited data. Output must parse into a fixed schema, then pass the output guard (leaks, echoes, markup, ungrounded numbers). See ADR 002 | Adversarial suite 75/75; 172 held-out prompts, 0 contract violations reached a user, model alone broke the contract 4 times in 336 answers (`docs/injection-eval.md`) | Done, measured. Limit: no measure of partial semantic influence |
| Injection in French, Spanish, Dutch | Topic check carries stems for those languages; the same output guard applies | Hand-written attacks, pure and embedded in an energy question (`docs/eval-results.md`) | Done for those languages and German; other languages are rejected as off topic |
| Injected instructions riding in via fetched data | Fetched data is parsed into numbers by code. Raw text from the source never reaches a prompt | Parser tests, hardened against malformed XML (`docs/what-broke.md`) | Done |
| Output used for XSS or phishing links | Schema-checked output, links and markup rejected, rendered as escaped text, strict CSP | Output guard tests; UI check in a real browser | Done |
| Cross-site requests spending our money | The API accepts only `application/json` | Found and fixed (`docs/what-broke.md`) | Done |
| Free-compute abuse (used as a general chatbot) | Input guard rejects off-topic questions before any model call | Rejections cost nothing; adversarial and multilingual suites | Done. Cost: some legitimate questions are rejected (see ADR 002) |
| Cost exhaustion | 500-character input cap, max output tokens, per-visitor rate limit (6 a minute, 100 a day), temporary bans, concurrency limit, persisted daily spend cap ($1), kill switch file | Load test: overload returns 503 at once, memory flat (`docs/load-test.md`) | Done in the app. **Not confirmed:** a spend limit set at the model provider |
| Key theft | Keys only in the server env file. Redacted in logs. Never in the client, the repository or the image. gitleaks in CI | Secret scan before every push | Done |
| Access to the home network | Cloudflare Tunnel, no open ports. Container runs as non-root, read-only, capabilities dropped, no new privileges, on its own network | `deploy/docker-compose.watt-brief.yml` | Done in the repository. The running server is only as safe as its last update |
| Denial of service | Rate limit and concurrency limit in the app. Model calls run inside a time budget (40 s each, retries included) | Load test | App side done. **Not confirmed:** a Cloudflare rate-limit rule in front |
| Metrics or alert data exposed | `/metrics` returns 404 unless a token is set and sent. Alerts hold counts and percentages, never question text | Blank-token bug found and fixed | Done. The alert topic on ntfy.sh is the only secret protecting it, so it is treated like a key |
| Sensitive data in logs | Structured logs. Questions are never logged, only their length | Privacy page says the same; log redaction tests | Done |
| Vulnerable or hijacked dependencies | Actions pinned by commit, Trivy scan before an image is published, Dependabot, runtime image without pip | Trivy found HIGH issues in the base image once; fixed | Done. Branch protection **not confirmed** |
| The service is down and nobody knows | Alerts go to a phone through ntfy. They cannot fire if the service is down | Test alerts received | Partial: an outside uptime check is still open |

## Decisions that were open

- **Logging questions:** decided not to log them. Logs record the question's length, the outcome and
  the reason. This removes the need for a retention period for question text. Container logs rotate
  at 3 files of 10 MB.
- **Login or only rate limits:** rate limits only, for now. A login would add accounts, personal
  data and friction to a demo, and the spend cap bounds the worst case at $1 a day. This is the
  owner's call; change it if real traffic shows abuse the limits do not handle.

## Honest limits

- Prompt injection has no complete fix. We limit what a successful injection can do (no tools, no
  secrets, schema-checked and grounded output) and measure how often attacks get through.
- The evals report rates, not guarantees. The held-out datasets are non-adaptive and mostly
  English and German.
- Questions are sent to the model provider, who handles them under its own terms. The privacy page
  says so.
- The ENTSO-E response is untrusted input too. It is parsed with a hardened XML parser, size
  checked, and fuzzed with Hypothesis (`tests/test_fuzz.py`). The stored history holds numbers only.
- Rate limits and bans are in memory and reset on restart; there is one instance.
- Some protections live outside this repository and are not verified here: the provider spend
  limit, Cloudflare rules, branch protection, and the state of the running server.
