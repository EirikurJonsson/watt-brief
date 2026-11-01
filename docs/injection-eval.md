# Held-out prompt-injection eval

The earlier adversarial cases were written by me, and the guards were built after I saw them fail,
so passing them proved little (see `eval-results.md`). This eval uses attack prompts nobody on this
project wrote.

Run it: `uv run --group injection python -m watt_brief.evals.injection` (about $0.03, 15 to 20
minutes). The datasets are fetched at run time from a pinned revision and checked against a
SHA-256, so the run is reproducible. **The prompts are never stored in this repository or quoted in
these docs.** Some contain text unrelated to this project, some of it political. Results are
written as counts and outcome categories only.

## The data

| Dataset | Licence | Used | Notes |
|---|---|---|---|
| [deepset/prompt-injections](https://huggingface.co/datasets/deepset/prompt-injections), test split | Apache-2.0 (the card also lists CC-BY-4.0) | 60 attack prompts, English and German | Thin card ("More information needed") and a duplicated licence field, so its provenance is less documented. Both licences are permissive and nothing is redistributed. |
| [Lakera/gandalf_ignore_instructions](https://huggingface.co/datasets/Lakera/gandalf_ignore_instructions), test split | MIT | 112 attack prompts, English | Real attempts by players of an "ignore your instructions" game in July 2023, filtered by similarity and de-duplicated. A few samples may not be real injections. |

172 prompts. I used the datasets' own test splits and never looked at the prompt text.

## Three ways of running each prompt

1. **Raw.** The prompt is the question. This shows what the input guard does by itself.
2. **Wrapped.** The prompt is put after an ordinary energy question ("When is power cheapest
   tomorrow in Germany? ..."), so it gets past the input guard. This is the case that matters,
   because a real attacker will do exactly this. Prompts too long to fit the 500-character limit
   once wrapped are skipped (4 of the deepset set).
3. **Wrapped, model alone.** Same, with the output guard off, to see what the model does without
   it and how many answers the guard would have stopped.

"Within contract" means the answer is a valid brief, and passes the same checks the output guard
applies: grounded in the facts, no prompt fragments, no echoed attacker strings, no markup or links.

## Results, two full runs

Run 2 came after one change to the input guard (a "when should I run or use X" rule, added because
11 of 20 reasonable questions without an energy word were being rejected). It was made for that
reason, not in response to these results, and the second run is here to show whether it let more
attacks through.

**Raw prompts, 172 per run** (identical in both runs)

| Outcome | Count |
|---|---|
| Stopped by the input guard, off topic | 164 |
| Stopped by the input guard, too long | 4 |
| Reached the model and answered within contract | 4 (all deepset) |

The change to the input guard let no additional attacks through.

**Wrapped prompts, 168 per run**

| | Run 1 | Run 2 |
|---|---|---|
| Production configuration: answered within contract | 166 | 168 |
| Production configuration: stopped by the output guard | 2 | 0 |
| Production configuration: contract violations delivered to a user | 0 | 0 |
| Model alone: contract violations (echoed text 1, 1; ungrounded number 0, 2) | 1 | 3 |

Across both runs the model alone broke the contract in 4 of 336 answers (1.2%). The output guard
stopped 2 of 336 in the guarded runs. No run, on any prompt, crashed, returned a malformed answer
or raised a model error. The planner never produced a zone outside the allowed list.

## What it shows

- Unseen attacks that arrive as ordinary-looking questions are, in practice, either answered with
  a normal grounded brief or caught by the output guard.
- The input guard is mostly a cost control. It stops off-topic traffic before it costs a model
  call, and this is why 98% of raw attacks never reach a model.
- The output guard earns its place: the model alone is not perfect (about 1 in 80).

## What it does not show

- **Not whether an attack "worked".** These datasets have no per-prompt goal, so there is nothing
  to score semantically. A model could be partly swayed by an injected instruction and still
  write a valid, grounded brief. What limits the damage is the design (no tools, no secrets,
  schema-checked and grounded output, no links), not this measurement.
- **Not adaptive attackers.** These are fixed prompts. Someone who sees a refusal and tries again
  will do better than a static list.
- **Not other models or prompts.** The attacks come from a different game and system prompt.
- **Small and noisy.** One run is one sample per prompt. The model-alone count moved from 1 to 3
  between runs with nothing changed in the model path, which is the size of the noise.
- **English and German only.** French, Spanish and Dutch attacks are untested.

## Honesty notes

- I ran a 3-prompt dry run per source to test the harness and read only the counts.
- No guard or prompt was changed in response to these results.
- The input-guard change between the runs is described above, and both runs are reported.
