"""Load test the service against a fake model server. Spends nothing.

Usage: uv run python scripts/loadtest.py

Starts scripts/fake_llm.py and the real service, then sends bursts at rising concurrency and
reports outcomes, latency, throughput, memory and CPU per request. It measures OUR service
(limits, overhead, memory), not the model provider's capacity or latency variance.
"""

import asyncio
import os
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
SERVICE = "http://127.0.0.1:8210"
FAKE = "http://127.0.0.1:9100"
DELAY = os.environ.get("FAKE_LLM_DELAY", "2.5")
LEVELS = [1, 2, 4, 8, 16, 32]
ROUNDS = 3  # each worker sends this many requests back to back
QUESTION = {"question": "When is power cheapest tomorrow in Germany?"}


def rss_mb(pid: int) -> float:
    for line in Path(f"/proc/{pid}/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) / 1024
    return 0.0


def cpu_seconds(pid: int) -> float:
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    ticks = int(fields[11]) + int(fields[12])  # utime + stime
    return ticks / os.sysconf("SC_CLK_TCK")


def start(cmd: list[str], env: dict) -> subprocess.Popen:
    return subprocess.Popen(
        cmd,
        cwd=ROOT,
        env={**os.environ, **env},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def wait_ready(url: str) -> None:
    for _ in range(100):
        try:
            if httpx.get(url, timeout=1).status_code < 500:
                return
        except httpx.HTTPError:
            time.sleep(0.2)
    raise RuntimeError(f"{url} did not start")


def wait_port(port: int) -> None:
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=1).close()
            return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"port {port} did not open")


async def worker(client: httpx.AsyncClient, results: list, rounds: int) -> None:
    for _ in range(rounds):
        started = time.perf_counter()
        try:
            r = await client.post(f"{SERVICE}/api/brief", json=QUESTION, timeout=120)
            results.append((r.status_code, time.perf_counter() - started))
        except httpx.HTTPError as exc:
            results.append((type(exc).__name__, time.perf_counter() - started))


async def burst(concurrency: int) -> tuple[list, float]:
    results: list = []
    async with httpx.AsyncClient() as client:
        started = time.perf_counter()
        await asyncio.gather(*(worker(client, results, ROUNDS) for _ in range(concurrency)))
    return results, time.perf_counter() - started


def pct(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(p * len(ordered)))]


def main() -> None:
    tmp = tempfile.mkdtemp(prefix="wb-load-")
    fake = start([sys.executable, "scripts/fake_llm.py"], {"FAKE_LLM_DELAY": DELAY})
    service = start(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "--factory",
            "scripts.loadtest_app:make_app",
            "--host",
            "127.0.0.1",
            "--port",
            "8210",
            "--log-level",
            "warning",
        ],
        {
            "PYTHONPATH": str(ROOT),
            "LLM_BASE_URL": f"{FAKE}/v1",
            "LLM_API_KEY": "sk-loadtest-not-a-real-key",
            "MODEL_PLANNER": "planner-m",
            "MODEL_ANALYST": "analyst-m",
            "MODEL_CRITIC": "critic-m",
            "SPEND_DB_PATH": f"{tmp}/spend.sqlite",
            "KILL_SWITCH_FILE": f"{tmp}/KILL",
            "DAILY_SPEND_CAP_USD": "1000",
            "RATE_LIMIT_PER_MINUTE": "100000",
            "RATE_LIMIT_PER_DAY": "1000000",
        },
    )
    try:
        wait_ready(f"{SERVICE}/healthz")
        wait_port(9100)
        print(
            f"fake model delay {DELAY}s per call, 2 calls per brief, {ROUNDS} requests per worker"
        )
        print(f"service memory at start: {rss_mb(service.pid):.0f} MB\n")
        header = f"{'workers':>7} {'requests':>8} {'ok':>4} {'busy':>5} {'other':>5} {'p50 s':>6} {'p95 s':>6} {'req/s':>6} {'cpu ms/req':>10} {'MB':>5}"
        print(header)
        print("-" * len(header))
        for level in LEVELS:
            cpu_before = cpu_seconds(service.pid)
            results, elapsed = asyncio.run(burst(level))
            cpu_ms = (cpu_seconds(service.pid) - cpu_before) * 1000 / len(results)
            ok = [t for code, t in results if code == 200]
            busy = sum(1 for code, _ in results if code == 503)
            other = len(results) - len(ok) - busy
            p50 = statistics.median(ok) if ok else float("nan")
            p95 = pct(ok, 0.95) if ok else float("nan")
            print(
                f"{level:>7} {len(results):>8} {len(ok):>4} {busy:>5} {other:>5} {p50:>6.1f} {p95:>6.1f} "
                f"{len(ok) / elapsed:>6.2f} {cpu_ms:>10.0f} {rss_mb(service.pid):>5.0f}"
            )
        print("\nbusy = HTTP 503 because the concurrency limit was reached (by design).")
    finally:
        for proc in (service, fake):
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    main()
