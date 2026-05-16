import os
#!/usr/bin/env python3
"""Call OpenRouter models with the 'mechanism of labor' SVG prompt."""

import asyncio
import re
import httpx
from pathlib import Path

API_KEY = os.environ["OPENROUTER_API_KEY"]
BASE_DIR = Path(__file__).parent
PROMPT = "Generate SVG description of the process of \"mechanism of labor\""

# Full list — edit to limit retries
MODELS = [
    ("Chatgpt 5.5 thinking", "openai/gpt-5.5"),
    ("Claude 4.7 Opus",       "anthropic/claude-opus-4.7"),
    ("Doubao",                 "bytedance-seed/seed-2.0-lite"),
    ("GLM 5.1 Thining",       "z-ai/glm-5.1"),
    ("Gemini 3 Pro",           "google/gemini-3.1-pro-preview"),
    ("Grok",                   "x-ai/grok-4.3"),
    ("Kimi K2.6 Thinking",    "moonshotai/kimi-k2.6"),
    ("MiniMax MAX",            "minimax/minimax-m2.7"),
]

# Only retry these
RETRY_ONLY = {"Doubao", "GLM 5.1 Thining", "Kimi K2.6 Thinking", "Gemini 3 Pro"}

def extract_svg(text: str) -> str:
    """Extract the first <svg …>…</svg> block from text (handles code fences)."""
    # Strip optional ```xml or ``` fences
    stripped = re.sub(r'```(?:xml|svg)?\s*', '', text)
    m = re.search(r'(<svg[\s\S]*?</svg>)', stripped, re.IGNORECASE)
    return m.group(1) if m else ""


async def call_model(client: httpx.AsyncClient, dir_name: str, model_id: str) -> None:
    out_dir = BASE_DIR / dir_name
    out_dir.mkdir(exist_ok=True)

    print(f"[{dir_name}] Calling {model_id} …")
    resp = None
    try:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://xiaopingfeng.com/deepdive/",
                "X-Title": "Mechanism of Labor Benchmark",
            },
            json={
                "model": model_id,
                "messages": [{"role": "user", "content": PROMPT}],
                "max_tokens": 8192,
            },
            timeout=httpx.Timeout(connect=30.0, read=300.0, write=30.0, pool=30.0),
        )
        resp.raise_for_status()
        data = resp.json()

        if "error" in data:
            raise RuntimeError(f"API error: {data['error']}")

        content = data["choices"][0]["message"]["content"]
        svg = extract_svg(content)

        (out_dir / "api.txt").write_text(content, encoding="utf-8")
        if svg:
            (out_dir / "api.svg").write_text(svg, encoding="utf-8")
            print(f"[{dir_name}] OK — SVG {len(svg)} chars")
        else:
            print(f"[{dir_name}] WARNING — no <svg> found; saved api.txt only")

    except Exception as e:
        err_body = resp.text[:3000] if resp is not None else "(no response)"
        print(f"[{dir_name}] ERROR — {type(e).__name__}: {e}\n  body: {err_body[:300]}")
        error_info = f"Model: {model_id}\nError: {type(e).__name__}: {e}\n\n{err_body}"
        (out_dir / "api.txt").write_text(error_info, encoding="utf-8")


async def main() -> None:
    targets = [(d, m) for d, m in MODELS if d in RETRY_ONLY]
    async with httpx.AsyncClient() as client:
        tasks = [call_model(client, d, m) for d, m in targets]
        await asyncio.gather(*tasks)
    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
