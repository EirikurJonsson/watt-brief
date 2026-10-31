# ADR 004: A plain HTML page, not a framework

Status: accepted
Date: 2026-10-31

## Context

The service needs a UI: one question box, one result card, a few error messages. It faces
hostile users, so the UI's attack surface matters as much as the API's.

## Decision

One static HTML page, one CSS file and one small vanilla JavaScript file, served by the same
app. No build step, no npm dependencies, no third-party scripts. Everything the server returns
is written to the page with `textContent`, never as HTML.

## Options considered

- **Vue (or React) with a build step.** Familiar and a reasonable choice for a larger app. It
  brings Node tooling and a tree of npm dependencies into the build, which is a supply-chain
  surface for very little gain here.
- **Vue from a script tag, no build.** This needs the runtime template compiler, which uses
  `eval`. That forces `unsafe-eval` into the Content Security Policy and undoes the strictest
  protection against script injection.
- **A Python UI framework (Gradio, Streamlit, Chainlit).** Fast to start, but a large
  dependency with its own endpoints in front of hostile users.
- **A prebuilt chat UI (Open WebUI, LibreChat).** Built for open-ended chat with its own auth
  surface. A poor fit for a structured brief.

## Consequences

- The Content Security Policy is `default-src 'self'` with no `unsafe-inline` and no
  `unsafe-eval`. Tests fail if the page gains inline script, inline style, or any of
  `innerHTML`, `eval` and similar.
- The API requires `Content-Type: application/json`. That forces a CORS preflight that other
  websites cannot pass, so a visitor's browser cannot be tricked into spending our budget.
- A hostile server response (injected `<img onerror>` and `<script>`) is shown as literal text.
  `scripts/ui_check.mjs` proves it in a real browser.
- If the UI grows past one page, or needs shared state, that is the point to adopt a
  framework with a proper build. The JSON API does not change.

## What would change this

More than a couple of views, state shared between them, or a team that is more productive in
a framework than in plain JavaScript.
