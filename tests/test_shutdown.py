"""A deploy sends SIGTERM mid-request: the answer must still arrive and the process must stop by itself.

Runs the real service and a slow fake model as subprocesses, so it checks uvicorn's shutdown, the
lifespan cleanup (warm-up task, databases) and the request thread pool together.
"""

import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_until_up(url: str, timeout: float = 20) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            if httpx.get(url, timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            time.sleep(0.2)
    raise AssertionError(f"{url} did not come up")


@pytest.mark.skipif(sys.platform == "win32", reason="needs POSIX signals")
def test_sigterm_during_a_request_lets_it_finish_and_exits_cleanly(tmp_path):
    llm_port, port = free_port(), free_port()
    llm = subprocess.Popen(
        [sys.executable, str(ROOT / "scripts/fake_llm.py")],
        env={**os.environ, "FAKE_LLM_PORT": str(llm_port), "FAKE_LLM_DELAY": "2.5"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    service = subprocess.Popen(
        [sys.executable, "-m", "watt_brief.serve"],
        cwd=ROOT,
        env={
            **os.environ,
            "FACTS_SOURCE": "fixture",
            "SERVE_PORT": str(port),
            "SPEND_DB_PATH": str(tmp_path / "spend.sqlite"),
            "HISTORY_DB_PATH": str(tmp_path / "history.sqlite"),
            "KILL_SWITCH_FILE": str(tmp_path / "KILL"),
            "LLM_BASE_URL": f"http://127.0.0.1:{llm_port}/v1",
            "LLM_API_KEY": "x",
            "MODEL_PLANNER": "planner-m",
            "MODEL_ANALYST": "analyst-m",
            "MODEL_CRITIC": "analyst-m",
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_until_up(f"http://127.0.0.1:{port}/healthz")
        reply: dict = {}

        def ask() -> None:
            reply["response"] = httpx.post(
                f"http://127.0.0.1:{port}/api/brief",
                json={"question": "When is power cheapest tomorrow in Germany?"},
                timeout=30,
            )

        asker = threading.Thread(target=ask)
        asker.start()
        time.sleep(1.0)  # the request is now waiting on the slow model
        service.send_signal(signal.SIGTERM)
        asker.join(timeout=30)
        assert reply["response"].status_code == 200
        # uvicorn re-raises the signal once it has shut down cleanly, so a clean stop is either 0
        # or "ended by SIGTERM" (Docker shows 143). A hang or a crash would be neither.
        assert service.wait(timeout=15) in (0, -signal.SIGTERM)
    finally:
        for proc in (service, llm):
            if proc.poll() is None:
                proc.kill()
