# What broke

Everything here was found by tests, evals, a browser check or a person looking, before or
shortly after it mattered. Newest first within each group. Dates are 2026.

## Things that would have hurt

- **Anyone could burn the budget from a visitor's browser (1 Nov).** The API parsed any body as
  JSON, whatever its content type. A page on another site could make a visitor's browser send a
  plain form post to us with no preflight. Now it must be `application/json`, which forces a
  preflight that other sites cannot pass.
- **A blank `METRICS_TOKEN=` would have opened `/metrics` (1 Nov).** An empty token matched a
  request that sent no credentials. Blank optional secrets now mean "not set".
- **A question about Sweden got German prices (31 Oct).** The planner had no way to say "not
  covered", so the pipeline fell back to Germany. Now there is an explicit "unsupported" answer
  and the user is told.
- **The spend cap would have undercounted (31 Oct).** Cost was added after a successful brief,
  so a request the output guard rejected still spent money that was never counted. Cost is now
  counted per model call, at the moment it happens.
- **A bare domain slipped past the output guard (31 Oct).** The model refused an attack but
  quoted `evil.example`. The guard only caught links starting with `http` or `www`. Fixed with a
  domain pattern and a test. The live re-run did not reproduce it, so the unit test is the proof.
- **`< / Facts >` got through the delimiter check (31 Oct).** A test caught the missing
  whitespace case before release.

- **A malformed ENTSO-E response would have crashed the parser (1 Nov).** It assumed every XML
  element existed, so a missing `position`, `resolution` or `price.amount` raised an
  `AttributeError` and became a generic 500. A response claiming a period of years would also
  have looped over every slot. Found by the type checker, not by a test. The parser now raises a
  clean `EntsoeError` for each case, caps a response at 400 slots, and has 13 tests for it. 11 of
  them fail against the old parser.

- **Non-English users were locked out (1 Nov).** The topic check knew only English, so 21 of 24
  ordinary German, French, Spanish and Dutch questions were rejected as off topic. Fixed with
  word stems per language and accent folding. A reverse test makes sure off-topic and injection
  phrases in those languages are still rejected.
- **The planner guessed the country from the language (1 Nov).** A French question with no
  country got `FR`. A prompt change reduced it and did not remove it, so a code check now drops
  any zone that is not named in the question.
- **The image scan blocked the first build (1 Nov).** Five fixable high-severity findings, all in
  the base image's system Python (pip's bundled libraries and setuptools), none in the app's own
  environment. The installer is removed from the runtime image.

## Things that made the measurements wrong

- **The first eval run failed on correct answers (31 Oct).** The graders rejected "31 October
  2026" and a correct "24 slots". The time regex also failed to find times inside timestamps
  like `T10:00Z`, so every correct brief would have been marked wrong. The unit tests caught the
  regex bug before any live run. Graders fixed, `slot_count` added to the facts, results rerun.
- **The strict grounding check rejected good answers (31 Oct).** About 3 in 20 `q-heatpump`
  answers were rejected because the model computed the gap between the cheapest and priciest
  windows, a correct number the facts did not state. The spread is now in the facts, and an
  ungrounded answer gets one retry. After that: 0 of 20.
- **The guard results flattered the guards (31 Oct).** The leak and echo checks were built after
  seeing those exact failures, and the on-topic attacks were written after the guards existed.
  `docs/eval-results.md` says so. A held-out attack set is still an open task.
- **The critic looked useful and was not (31 Oct).** It doubled the cost and improved nothing the
  evals could measure. It stays off. ADR 003.

## Things I got wrong while building

- **I said a push would deploy to the live site (1 Nov).** The deploy job is off until
  `DEPLOY_ENABLED` is set. The site stayed on the old UI until the image was pulled by hand.
- **The first UI was generic (1 Nov).** It worked and was safe, and it was a text box in an empty
  page. It hid the answer behind a model call and left the price chart, the most characteristic
  thing in the subject, off the page entirely. It was redesigned around the chart.
- **The redesign's headline was too big (1 Nov).** The chart fell below the fold. Found by looking
  at a screenshot, not by a test.
- **Two bracket labels printed on top of each other on a phone (1 Nov).** They were measured
  while the chart was still hidden, so every size was zero and no collision was detected. A new
  browser check now fails on this.
- **`.env.example` had a blank `DAILY_SPEND_CAP_USD=` (1 Nov).** Anyone copying it would have
  crashed at startup, because a blank value does not parse as a number.
- **The grounding check rejected correct non-English answers (1 Nov).** `69,25` read as two
  invented numbers and French `10h00` as an invented 0. Found by the first multilingual live
  run, where 2 of 72 answers were wrongly rejected. Fixed, with tests that invented numbers in
  those formats are still caught.
- **Briefs showed raw timestamps (1 Nov).** The model copied `2026-10-31T10:00Z` out of its facts.
  The prompt now asks for `10:00 UTC` and `31 October`. Evals rerun: no regression.
