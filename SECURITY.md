# Security policy

watt-brief is a public service that takes free text from strangers and passes it to a language
model, so security reports are welcome.

## Reporting a vulnerability

Use GitHub's private reporting: **Security, then "Report a vulnerability"** on this repository.
Please do not open a public issue for something exploitable. Include what you did, what you
expected and what happened. A prompt that makes the service leak its instructions, state a figure
that is not in the data, or spend money outside the daily cap counts as a vulnerability.

You can expect an acknowledgement within a few days. This is a one-person project, so there is no
bug bounty and no guaranteed fix time, but real findings are fixed and credited if you wish.

## What is in scope

The service at the deployed hostname and the code in this repository. Out of scope: Cloudflare,
the model provider, ENTSO-E, and denial of service by sheer traffic volume.

## What we already do

See `docs/threat-model.md` for threats, mitigations and the evidence for each, and
`docs/injection-eval.md` for measured prompt-injection results.
