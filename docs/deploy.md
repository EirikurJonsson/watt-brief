# Deploying to the home server

Ingress is the existing Cloudflare Tunnel (the `cloudflared` container in the n8n compose
stack). No ports are opened. Deploys reuse the pattern that ships cpa-intel.tech: GitHub
Actions joins Tailscale, SSHes in, pulls the image from GHCR and runs `docker compose up`.

```
push to main -> tests -> image to ghcr.io -> Tailscale + SSH -> compose pull/up -> health gate
browser -> Cloudflare -> tunnel -> cloudflared --(watt-net)--> watt_brief:8000
```

Nothing sensitive lives in this repo. The model key lives in an env file on the server only.

Placeholders: `<HOSTNAME>` is the public name you pick (for example `watt-brief.cpa-intel.tech`),
`<COMPOSE_DIR>` is the directory that holds the n8n compose file (the cpa-intel workflow uses
`/home/eirikur/n8n`).

> **Current state (8 Nov):** automatic deploy is not enabled. CI builds, scans and publishes the
> image to GHCR on every push to `main`; the server is updated by hand (see Rollback in
> operations.md for the pull and `docker compose up -d` commands). Follow this page only when you
> turn automatic deploy on.

## 1. GitHub, once (repo Settings, Secrets and variables, Actions)

Secrets. The first five are the same values cpa-intel already uses:

| Secret | What |
|---|---|
| `TS_OAUTH_CLIENT_ID`, `TS_OAUTH_SECRET` | Tailscale OAuth client allowed to use `tag:cpa-intel` |
| `SSH_DEPLOY_KEY` | private key authorised on the server |
| `GHCR_USERNAME`, `GHCR_TOKEN` | a token with `read:packages`, so the server can pull the image |
| `DEPLOY_HOST`, `DEPLOY_PORT`, `DEPLOY_USER` | the server's Tailscale address, SSH port and user |

Variables:

| Variable | Value |
|---|---|
| `DEPLOY_DIR` | `<COMPOSE_DIR>` |
| `SMOKE_URL` | Optional, e.g. `https://<HOSTNAME>`. After each deploy, `scripts/smoke.sh` runs against it through Cloudflare, including one real brief. |
| `DEPLOY_ENABLED` | `true`. Set this **last**, after step 2 and 3. Until then CI builds and pushes the image but does not deploy. |

The deploy key can run commands on your server, and anyone who can push to `main` can use it.
Keep branch protection on and do not add collaborators lightly. A tighter option for later:
a dedicated key restricted in `authorized_keys` to the `docker compose` commands.

## 2. Server, once (over SSH)

```
cd <COMPOSE_DIR>

# data directory, owned by the container user (uid 1000)
mkdir -p watt-brief-data && sudo chown 1000:1000 watt-brief-data

# env file: you type the key, it never goes through GitHub or a chat
umask 077
read -rsp "DeepInfra key: " K; echo
cat > watt-brief.env <<EOF
LLM_API_KEY=$K
LLM_BASE_URL=https://api.deepinfra.com/v1/openai
MODEL_PLANNER=deepseek-ai/DeepSeek-V4.1-Flash-1017
MODEL_ANALYST=deepseek-ai/DeepSeek-V4.1-Flash-1017
MODEL_CRITIC=deepseek-ai/DeepSeek-V4.1-Flash-1017
DAILY_SPEND_CAP_USD=1.0
METRICS_TOKEN=$(openssl rand -hex 24)
EOF
unset K
chmod 600 watt-brief.env
```

Also set a spend limit in the DeepInfra dashboard. It is the backstop if everything else fails.

Merge `deploy/docker-compose.watt-brief.yml` into the compose file, and add `watt-net` to the
`cloudflared` service's networks (the comments in that file show how).

Log in to GHCR once, then start it (after the first CI run has pushed the image, see step 4):

```
echo "<GHCR_TOKEN>" | docker login ghcr.io -u <GHCR_USERNAME> --password-stdin
docker compose pull watt_brief
docker compose up -d watt_brief cloudflared    # recreates cloudflared: cpa-intel.tech blips for a few seconds
docker compose ps watt_brief                   # wait for "healthy"
```

## 3. Cloudflare, once

Zero Trust, Networks, Tunnels, pick the tunnel your `cloudflared` container runs.

- **If it has a "Public hostnames" tab** (remotely managed): add a hostname. Subdomain and
  domain give `<HOSTNAME>`, service type `HTTP`, URL `watt_brief:8000`. The DNS record is
  created for you.
- **If it is managed by a local `config.yml`**: add an `ingress` rule for `<HOSTNAME>` pointing
  at `http://watt_brief:8000`, above the catch-all rule, restart `cloudflared`, and run
  `cloudflared tunnel route dns <tunnel> <HOSTNAME>`.

Recommended before you announce it, in the Cloudflare dashboard for the zone:

- A rate limiting rule for `POST /api/brief` (the free plan allows one). The app limits per
  client too, but Cloudflare sees abuse first and absorbs it for free.
- Bot Fight Mode on.

## 4. First deploy and verification

Push to `main` (or re-run the workflow). Tests, then the image, then the deploy job if
`DEPLOY_ENABLED` is `true`. The deploy job fails if the container is not healthy within about a
minute, and prints its last log lines.

Then, from any machine:

```
scripts/smoke.sh https://<HOSTNAME>
```

It checks the page, the headers, that docs and metrics are hidden, that wrong content types and
off-topic questions are refused, and makes one real brief request (a fraction of a cent).

Read the metrics with the token from `watt-brief.env`:

```
curl -H "Authorization: Bearer <METRICS_TOKEN>" https://<HOSTNAME>/metrics
```

## Day to day

| Task | How |
|---|---|
| Deploy a change | merge to `main` |
| Stop all model calls now | `touch <COMPOSE_DIR>/watt-brief-data/KILL_SWITCH` (delete the file to resume) |
| Roll back | automatic if the new container is unhealthy or runs the wrong commit; by hand: in the compose file set `image: ghcr.io/eirikurjonsson/watt-brief:<good-sha>`, then `docker compose up -d watt_brief` |
| Rotate the model key | edit `watt-brief.env`, then `docker compose up -d --force-recreate watt_brief` |
| See today's spend | `curl https://<HOSTNAME>/healthz` shows the percent of the cap used |
| Logs | `docker logs -f watt_brief` (structured JSON; alerts are `WARNING` and `ERROR` lines) |

## When something is wrong

| Symptom | Likely cause |
|---|---|
| Cloudflare 502 | `cloudflared` is not on `watt-net`, or the route URL is wrong. It must be `watt_brief:8000`. |
| `denied` when pulling the image | not logged in to GHCR on the server, or the token lacks `read:packages` |
| Deploy job fails on health | `docker logs watt_brief`. Usually a missing or misspelled variable in `watt-brief.env`. |
| Everyone gets rate limited together | the app sees one client IP. Check `TRUST_CF_CONNECTING_IP` is `true` and that traffic really comes through Cloudflare. |
| `/metrics` returns 404 | `METRICS_TOKEN` is not set in `watt-brief.env`, or the bearer token is wrong. That is by design. |
| Write errors on the data volume | `watt-brief-data` is not owned by uid 1000 |

## Safety notes

- The service trusts the `CF-Connecting-IP` header for rate limits. That is only safe because
  `watt_brief` shares a network with `cloudflared` and nothing else. Do not publish port 8000
  and do not attach other containers to `watt-net`.
- The container is read-only, drops all capabilities, cannot gain privileges, and is limited to
  512 MB and 128 processes.
- Data is synthetic until the ENTSO-E token works. Every response says so.
