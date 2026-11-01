# ADR 002: Layered deterministic guards around the model

Status: accepted
Date: 2026-10-31

## Context

Anyone on the internet can send a question. Prompt injection has no complete fix, so the
goal is to limit what a successful one can do and to measure how often attacks get through.
The model has no tools and no secrets (see the threat model), so the remaining risks are
wrong or manipulated text in the brief, wasted spend, and leaked prompt wording.

## Decision

Three layers, each deterministic and cheap, each measured on its own:

1. **Input guard (no model call).** Normalize Unicode (NFKC), drop control and zero-width
   characters, cap the length, reject our own delimiter tags, and require at least one
   energy or price term.
2. **Model call with structured output.** The question is passed as delimited data. The
   answer must parse into a fixed schema.
3. **Output guard.** Reject a brief that leaks system-prompt wording, echoes a code-like
   token from the question, contains markup or links, or contains any number or clock time
   that is not in the facts. On an *ungrounded* answer only, retry once and tell the model
   which values were not in the facts.

Rejections return a fixed message that never repeats the user's text. Logs record the
reason and the question length, not the question.

## Options considered

- **Model-based guard (a second model classifies the input).** More flexible, but it adds
  cost, latency and its own injection surface. Rejected for now.
- **No topic check, rely on the system prompt.** Cheaper to build, but every off-topic or
  attack request then costs a model call. The input guard is what keeps rejected traffic free.
- **Strict grounding without retry.** Measured: about 3 in 20 legitimate answers for one
  question were rejected, because the model computed a derived figure the facts did not state.
  Fixed by stating the derived value in the facts, plus one retry.

## Consequences

- The topic check is a keyword allowlist. It will reject some legitimate questions phrased
  without any energy word. The message tells the user what to ask.
- The echo check is a heuristic for attacker-style codes (for example `PWNED-7731`). A
  determined attacker can evade it. It exists to catch the cheap, common cases.
- Grounding is strict: a correct figure that is not stated in the facts is rejected. The fix
  is to put derived figures in the facts, not to loosen the check.
- The retry can double the cost of a request. It applies only to ungrounded answers.
- Each layer can be switched off in the evals, so the contribution of each is measurable.
  See `docs/eval-results.md`.

## Update, 1 November: languages

The topic check now carries word stems for English, German, French, Spanish and Dutch, matched
on lower-cased, accent-free text. Before that, 3 of 24 ordinary non-English questions got
through. The stems are deliberately specific (no generic words such as "laden"), and tests check
that off-topic and injection phrases in those languages are still rejected. Other languages are
still treated as off topic. The grounding check also accepts decimal commas and French times, so
correct non-English answers are not rejected. See `docs/eval-results.md`.

## What would change this

If real traffic shows many legitimate questions rejected by the topic check, replace it
with a small classifier and re-run the adversarial evals. If the retry rate is high in
production, fix the prompt or the facts, not the guard.
