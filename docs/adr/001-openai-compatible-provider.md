# ADR 001: Talk to models through an OpenAI-compatible interface

Status: accepted
Date: 2026-10-30

## Context

Development runs on a short-lived DeepInfra API key. When it expires, the project must
not break. We also want to compare models per step (planner, analyst, critic) and
record what each costs.

## Decision

All model calls go through one thin client that speaks the OpenAI-compatible chat API.
Base URL, API key and model name per step come from configuration.

## Options considered

- **Provider SDK directly.** Less code today. Locks the repo to one vendor, and the
  repo dies with the key.
- **Heavy abstraction layer (LangChain and similar).** Broad provider support, but a
  large dependency for a small need, and it hides the calls we want to measure.
- **Thin OpenAI-compatible client (chosen).** DeepInfra, other hosted providers, and
  local servers such as Ollama or llama.cpp all expose this shape.

## Consequences

- Swapping provider or model is a config change.
- Provider-specific features (special tool formats, reasoning modes) are out of reach
  unless the endpoint exposes them the same way.
- Cost per call is computed from the token counts the response reports, with prices
  held in config so they can be updated.

## What would change this

If a model we need is only reachable through a non-compatible API, we add one adapter
and write a new ADR.
