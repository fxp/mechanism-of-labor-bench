import os
#!/usr/bin/env python3
"""Retry Gemini 3 Pro and GLM 5.1 with correct settings."""

import asyncio
import re
import httpx
from pathlib import Path

API_KEY = os.environ["OPENROUTER_API_KEY"]
BASE_DIR = Path(__file__).parent
PROMPT = "Generate SVG description of the process of \"mechanism of labor\""

TARGETS = [
    # GLM is a reasoning model — needs very high token limit
    ("GLM 5.1 Thining", "z-ai/glm-5.1",                32000),
    # Gemini wraps in ```xml...``` fences
    ("Gemini 3 Pro",    "google/gemini-3.1-pro-preview", 16000),
]


def extract_svg(text: str) -> str:
    """Extract the first <svg…>…</svg> block, handles code fences."""
    # Remove all code-fence markers (opening and closing)
    stripped = re.sub(r'```[a-z]*\n?', '', text)
    m = re.search(r'(<svg[\s\S]*?</svg>)', stripped, re.IGNORECASE)
    return m.group(1) if m else ""


async def call_model(client: httpx.AsyncClient, dir_name: str, model_id: str,
                     max_tokens: int) -> None:
    out_dir = BASE_DIR / dir_name
    out_dir.mkdir(exist_ok=True)

    print(f"[{dir_name}] Calling {model_id} (max_tokens={max_tokens}) …")
    resp = None
    try:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": model_id,
                "messages": [{"role": "user", "content": PROMPT}],
                "max_tokens": max_tokens,
            },
            timeout=httpx.Timeout(connect=30.0, read=480.0, write=30.0, pool=30.0),
        )
        resp.raise_for_status()
        data = resp.json()

        if "error" in data:
            raise RuntimeError(f"API error: {data['error']}")

        content = data["choices"][0]["message"]["content"]
        if content is None:
            # Some reasoning models put output in reasoning field only when truncated
            reasoning = (data["choices"][0]["message"].get("reasoning") or
                         data["choices"][0]["message"].get("reasoning_content") or "")
            finish = data["choices"][0].get("finish_reason", "")
            raise RuntimeError(
                f"content=None, finish_reason={finish}. "
                f"Reasoning preview: {reasoning[:200]}"
            )

        svg = extract_svg(content)
        (out_dir / "api.txt").write_text(content, encoding="utf-8")

        if svg:
            (out_dir / "api.svg").write_text(svg, encoding="utf-8")
            print(f"[{dir_name}] OK — SVG {len(svg)} chars")
        else:
            print(f"[{dir_name}] WARNING — no <svg> found; api.txt saved")

    except Exception as e:
        err_body = resp.text[:3000] if resp is not None else "(no response)"
        print(f"[{dir_name}] ERROR — {type(e).__name__}: {e}")
        print(f"  body[:300]: {err_body[:300]}")
        (out_dir / "api.txt").write_text(
            f"Model: {model_id}\nError: {type(e).__name__}: {e}\n\n{err_body}",
            encoding="utf-8"
        )


async def main() -> None:
    async with httpx.AsyncClient() as client:
        tasks = [call_model(client, d, m, t) for d, m, t in TARGETS]
        await asyncio.gather(*tasks)
    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
