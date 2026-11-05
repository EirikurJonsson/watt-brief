# syntax=docker/dockerfile:1
FROM python:3.15-slim AS build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
RUN pip install --no-cache-dir uv==0.12.9
WORKDIR /app
# dependencies first, so this layer is cached until the lockfile changes
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY tests/fixtures ./tests/fixtures
RUN uv sync --frozen --no-dev

FROM python:3.15-slim
# Fixed uid so the bind-mounted data directory on the host can be owned by the same user.
RUN useradd --uid 1000 --no-create-home --shell /usr/sbin/nologin app \
    && mkdir -p /app/data && chown app:app /app/data
# The app runs from /opt/venv and installs nothing at runtime, so the base image's package
# installer is dead weight with its own vulnerable bundled libraries. Remove it.
RUN python -m pip uninstall -y pip setuptools wheel
# The base image can lag Debian's security fixes. Upgrade only apt (CI's Trivy scan failed on
# CVE-2026-109518, fixed in apt 3.0.4), then drop the package lists again.
RUN apt-get update \
    && apt-get install -y --no-install-recommends --only-upgrade apt libapt-pkg7.0 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /opt/venv /opt/venv
COPY --from=build /app /app
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 SERVE_HOST=0.0.0.0
WORKDIR /app
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).status == 200 else 1)"
CMD ["python", "-m", "watt_brief.serve"]
