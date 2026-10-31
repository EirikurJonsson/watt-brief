# Threat model

Draft. Written before the code so the design answers it, not the other way round.

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
| ENTSO-E response | Low risk, but treat it as data, never as instructions |
| Model output | May contain injected content, markup or links. Untrusted until validated |

## Threats and planned mitigations

| Threat | Mitigation |
|---|---|
| Prompt injection to change behaviour or leak the system prompt | No secrets in prompts. Agents get no tools beyond one fixed data fetch. Question and data are passed as clearly delimited data. Critic step checks the draft against the data |
| Injected instructions riding in via fetched data | Fetched data is parsed into numbers by code. Raw text from the source never reaches a prompt |
| Output used for XSS or phishing links | Structured output validated against a schema. Rendered as escaped text. No model-generated links |
| Free-compute abuse (using it as a general chatbot) | Topic check on the question. Rejected requests are logged and cheap |
| Cost exhaustion | Input length cap, max output tokens, per-IP rate limit, daily spend cap with hard stop, kill switch |
| Key theft | Keys only in server env. Never logged. Never in the client. Redacted in logs |
| Access to the home network | Cloudflare Tunnel, no open ports. App runs as non-root in a container with no access to the LAN beyond what it needs |
| Denial of service | Rate limiting at Cloudflare and in the app. Request timeout. Concurrency limit |
| Log injection and sensitive data in logs | Structured logs. User text logged as a field, never interpolated into messages. Retention period decided and documented |

## Honest limits

- Prompt injection has no complete fix. We limit what a successful injection can do
  (no tools, no secrets, schema-checked output) and measure how often attacks work.
- The adversarial evals report a pass rate, not a guarantee.

## Open questions

- Retention period for logged questions, and whether to log them at all
- Whether the live demo needs a login or only rate limits
