# watt-brief

Energy decisions, not energy dashboards.

Ask a question about European power prices. Get a one-page brief that ends in a
recommended decision, with the reasoning and the cost of producing it.

> Example question: *Should a flexible consumer in Germany shift load to tomorrow's
> cheapest hours?*

**Status: early scaffold. Nothing here works yet.** See [docs/status.md](docs/status.md).

## Why this exists

A model is a component. The product is a changed decision. Most AI demos stop at the
chart. This repo goes the rest of the way: agents, evals, cost tracking, a live
deployment, and a record of what broke.

It is the open companion to the series *Past the Demo* at https://cpa-intel.tech.

## How it works (planned)

```
question ──► planner ──► analyst ──► critic ──► brief
                │           │           │
                └───── ENTSO-E day-ahead prices (public)
                        every step logs tokens, cost, latency
```

- **Planner:** turns the question into the data it needs.
- **Analyst:** pulls the prices, does the numbers, drafts the recommendation.
- **Critic:** attacks the draft. Is the data stale? Is the claim bigger than the evidence?
- **Brief:** one page, recommendation first.

Whether the planner and critic actually help is an open question. The eval harness
decides, and the answer goes in an ADR either way.

## Data

[ENTSO-E Transparency Platform](https://transparency.entsoe.eu/) day-ahead prices.
Public. Needs a free API token (register, then request one by email to their support).

## Models

Any OpenAI-compatible endpoint. Development runs on [DeepInfra](https://deepinfra.com/).
Model names and base URL live in config, not in code. See
[ADR 001](docs/adr/001-openai-compatible-provider.md).

## Run it

```
cp .env.example .env     # add your keys
# nothing to run yet
```

Keys stay in `.env` and in the server's environment. Never in the repo, never in the client.

Smoke test your model endpoint before anything else:

```
curl "https://api.deepinfra.com/v1/openai/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $LLM_API_KEY" \
  -d '{
      "model": "deepseek-ai/DeepSeek-V4.1-Flash-1017",
      "messages": [
        {
          "role": "user",
          "content": "Hello!"
        }
      ]
    }'
```

## Decisions

All architecture decisions are in [docs/adr/](docs/adr/).

## Licence

TBD.
