"""A fake OpenAI-compatible model server for load tests. Costs nothing.

Answers the planner and the analyst with fixed, valid JSON after a delay, so the whole service
can be exercised without a real model. Usage: python scripts/fake_llm.py (FAKE_LLM_DELAY seconds,
default 2.5, FAKE_LLM_PORT, default 9100).
"""

import asyncio
import json
import os

import uvicorn
from fastapi import FastAPI, Request

DELAY = float(os.environ.get("FAKE_LLM_DELAY", "2.5"))
PORT = int(os.environ.get("FAKE_LLM_PORT", "9100"))

PLAN = {"zone": "DE_LU", "window_hours": 3, "intent": "cheapest_window"}
BRIEF = {
    "recommendation": "Run from 10:00 to 13:00 UTC at an average of 3.0 EUR/MWh.",
    "reasoning": "The day mean is 69.25 EUR/MWh, so this window is far cheaper.",
    "caveats": ["Day-ahead prices only."],
}

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.post("/v1/chat/completions")
async def completions(request: Request):
    body = await request.json()
    await asyncio.sleep(DELAY)
    is_planner = body["model"] == "planner-m"
    content = json.dumps(PLAN if is_planner else BRIEF)
    return {
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 500, "completion_tokens": 120, "estimated_cost": 0.0001},
    }


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
