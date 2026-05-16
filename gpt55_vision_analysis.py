import os
#!/usr/bin/env python3
"""
Send rendered PNGs to GPT-5.5 via OpenRouter for visual analysis of
「胎儿分娩机转」(mechanism of labor) SVG quality.
"""

import asyncio
import base64
import json
from pathlib import Path

import httpx

API_KEY = os.environ["OPENROUTER_API_KEY"]
MODEL   = "openai/gpt-5.5"
BASE_DIR = Path(__file__).parent

MODELS = [
    "Chatgpt 5.5 thinking",
    "Claude 4.7 Opus",
    "Doubao",
    "GLM 5.1 Thining",
    "Gemini 3 Pro",
    "Grok",
    "Kimi K2.6 Thinking",
    "MiniMax MAX",
]

SYSTEM_PROMPT = """You are an expert obstetrician and medical illustrator.
Evaluate the attached image — an AI-generated SVG rendered as PNG — for how accurately
it depicts the "mechanism of labor" (胎儿分娩机转 / cardinal movements of childbirth).

Score and comment on these 7 criteria (reply in Chinese):

1. **步骤完整性** — 覆盖了哪些分娩机转步骤？（满分：衔接、下降、俯屈、内旋转、仰伸、外旋转、娩出 共7步）
2. **解剖结构准确性** — 骨盆形态、耻骨联合、骶骨是否可辨识？胎头有无解剖细节？
3. **胎儿方向（头朝下）** — 胎儿是否呈头先露（vertex）、头朝向骨盆出口方向？
4. **内旋转的视觉呈现** — 内旋转步骤是否有清晰的视觉图形表达（旋转箭头、俯视图等），而非仅文字标注？
5. **外旋转的视觉呈现** — 外旋转/复位步骤是否有清晰视觉表达？
6. **运动方向标注** — 是否用箭头或其他方式清晰指示各步骤的运动方向？
7. **整体视觉清晰度** — 布局、配色、标注是否易于理解？

For each criterion give:
- 评分：1–5分
- 具体观察（引用图中可见的视觉元素）

End with a one-paragraph 总体评价 (3–4 sentences).
"""

def encode_image(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


async def analyze_image(
    client: httpx.AsyncClient,
    model_dir: str,
    version: str,   # "chat" or "api"
) -> None:
    img_path = BASE_DIR / model_dir / f"{version}.png"
    out_path  = BASE_DIR / model_dir / f"{version}_gpt55.txt"

    if not img_path.exists():
        print(f"[{model_dir}/{version}] SKIP — PNG not found")
        return

    print(f"[{model_dir}/{version}] Sending to GPT-5.5 …")
    b64 = encode_image(img_path)

    payload = {
        "model": MODEL,
        "max_tokens": 1500,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"这是模型「{model_dir}」生成的SVG渲染图（{version}版本）。"
                            "请按照7条评判标准逐一打分并评述。"
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{b64}",
                            "detail": "high",
                        },
                    },
                ],
            },
        ],
    }

    resp = None
    try:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=httpx.Timeout(connect=30.0, read=300.0, write=60.0, pool=30.0),
        )
        resp.raise_for_status()
        data = resp.json()

        if "error" in data:
            raise RuntimeError(data["error"])

        content = data["choices"][0]["message"]["content"]
        out_path.write_text(content, encoding="utf-8")
        print(f"[{model_dir}/{version}] OK ({len(content)} chars)")

    except Exception as e:
        err = resp.text[:1000] if resp is not None else "(no response)"
        print(f"[{model_dir}/{version}] ERROR — {type(e).__name__}: {e}\n  {err[:300]}")
        out_path.write_text(
            f"Error: {type(e).__name__}: {e}\n\n{err}", encoding="utf-8"
        )


async def main() -> None:
    # Process in batches of 4 to avoid rate limits
    tasks = [
        (model_dir, version)
        for model_dir in MODELS
        for version in ("chat", "api")
    ]

    async with httpx.AsyncClient() as client:
        for i in range(0, len(tasks), 4):
            batch = tasks[i : i + 4]
            await asyncio.gather(*[
                analyze_image(client, d, v) for d, v in batch
            ])
            if i + 4 < len(tasks):
                print("  [batch done, continuing…]")

    print("\nAll done.")


if __name__ == "__main__":
    asyncio.run(main())
