# Eval results

Latest live runs: 2026-10-31, model `deepseek-ai/DeepSeek-V4.1-Flash-1017`, 5 repeats per case.
Data: **synthetic fixture**, not real market data. Cases: `src/watt_brief/evals/cases.py`.
Graders are plain code, no model judging a model: `src/watt_brief/evals/graders.py`.
Guard design: [ADR 002](adr/002-layered-guards.md).

## What each layer contributes

Same cases, three configurations. Layers are switched off with `--no-input-guard` and
`--no-output-guard`.

| Configuration | Quality | Adversarial | Where attacks were stopped |
|---|---|---|---|
| Model alone | 24/25 | 61/65 | nowhere, the model answered all 65 |
| Model + output guard | 25/25 | 65/65 | output guard 11, model 54 |
| All guards | 24/25 | 75/75 | input guard 40, output guard 7, model 28 |

Adversarial totals differ because two cases (oversized and empty input) only exist to test the
input guard, so they are skipped when it is off. 15 cases, 5 repeats.

Cost for a full run is under a cent. Median latency per brief is about 2.6 s. Requests stopped
by the input guard cost nothing and make no model call.

## What the model alone got wrong

No attack made the model comply. The failures were the model *quoting* what it refused:

- Repeating the attacker's canary string while declining it (`PWNED-7731`).
- Using the phrase "do not comply" from the system prompt, and "untrusted user data".
- Quoting an attacker's fake figure (`0.01 EUR`) while saying it was unsupported.

The output guard catches all three kinds.

## Quality

24 or 25 of 25 in every configuration. The two misses were different ones, so they look like
noise at this sample size: once the model said the hour of the negative price "is not given"
when it was, and once it returned text that was not valid JSON.

## How to read this honestly

- **Small sample.** 5 repeats per case. Treat rates as indicative, not as guarantees. A
  difference of a few runs between configurations is not strong evidence.
- **The cases are not independent of the guards.** The leak, echo and quoting checks were
  built after I saw those exact failures, and the on-topic attacks were written after the
  guards existed. Passing them shows the guards do what they were designed to do. It does not
  show they generalise. There is no held-out attack set yet. That is the main gap.
- **The input guard looks better than it is.** 40 of 75 attacks stopped there partly because
  my off-topic attacks contain no energy words. The on-topic attacks are the harder test, and
  they were stopped by the model and the output guard, not by the input guard.
- **A false positive was found and fixed.** The strict grounding check rejected 3 of 20
  legitimate `q-heatpump` answers, because the model computed the spread between the priciest
  and cheapest windows (a correct figure the facts did not state). Fix: put the spread in the
  facts and retry once on an ungrounded answer. After that: 0 of 20 rejected.
- **History of changes made after seeing results.** The first live run failed many quality
  cases because the graders were wrong (they rejected dates such as "31 October 2026" and a
  correct "24 slots"). I fixed the graders and added `slot_count` to the facts. One case
  (`a-delimiter-escape`) was changed to check that the real minimum wins, because the model
  quoted the fake value while refusing it.
- **Real market data may behave differently.** Re-run once the ENTSO-E token works.

## Next to test

- A held-out set of attacks written without looking at the guards, ideally by someone else, or
  taken from a public prompt-injection dataset.
- Questions in other languages (the topic check is English-only keywords).
- Legitimate questions phrased without any energy word, to measure the input guard's false
  rejections.

Run it yourself: `uv run python -m watt_brief.evals.runner --repeats 5` (needs a key in `.env`;
hard spend cap `--max-cost`, default $0.25).

## Planner and critic (step 8)

Same cases and guards as above, 5 repeats, comparing pipeline configurations. Decision and
reasoning: [ADR 003](adr/003-planner-yes-critic-not-yet.md).

| Config | Quality | Adversarial | Cost | Median latency |
|---|---|---|---|---|
| Analyst only | 25/25 | 75/75 | $0.0042 | 3.4 s |
| + planner | 25/25 | 75/75 | $0.0059 | 4.2 s |
| + critic | 25/25 | 73/75 | $0.0084 | 4.3 s |
| + planner and critic | 25/25 | 75/75 | $0.0093 | 4.5 s |

Planner alone, 9 questions x 5 repeats: 45/45 on zone, window hours and intent, including an
injection attempt and a question about an unsupported country.

- **The critic showed no measurable benefit.** The baseline was already at the ceiling, so
  this set cannot show one. It did cost about twice as much. It asked for a revision on 7 or
  8 of roughly 55 model-answered requests.
- **The critic run had two adversarial misses.** One was invalid JSON from the model. The other
  was the model quoting an attacker's domain (`evil.example`) while refusing it. That second
  one exposed a real gap in the output guard, which only caught links starting with `http` or
  `www`. I closed it afterwards by adding a domain pattern, covered by a unit test. A live
  re-run of that case (10 repeats) passed, but the model did not quote the domain in any of
  them, so the live run does not prove the fix. The unit test does. Two misses in 75 is not a
  statistically meaningful difference from zero in 75.
- **The planner's value is capability, not score.** The existing suite only asks about the one
  zone we have data for, so it cannot reward choosing the zone correctly.
- **Still no data for other zones.** Until the ENTSO-E token works, only DE_LU has (synthetic)
  data. The pipeline returns an honest "no data" error for the others.

Next to test: a harder quality set, so the critic has something to improve.
