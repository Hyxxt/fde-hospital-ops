"""Measure streaming TTFT and generated-token throughput against a vLLM service."""
import argparse
import json
import math
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter
from urllib.request import Request, urlopen

PROMPTS = [
    "用两句话说明报修登记时记录设备资产编号的用途。",
    "简要说明什么时候应该复核采购申请的规格。",
    "介绍盘点和库存账目核对的区别，输出约五十字。",
    "用中文列出三条设施巡检交接注意事项。",
    "用三句话介绍为什么保留原审批记录。",
    "给一个后勤维修超时登记的简短示例。",
    "用两句话解释科室签收耗材时如何核对数量。",
    "列举三个仓库管理日常使用的记录字段。",
]


def generate(url, model, prompt):
    data = {
        "model": model, "messages": [{"role": "user", "content": prompt}],
        "temperature": 0, "max_tokens": 64, "stream": True,
        "stream_options": {"include_usage": True},
        "chat_template_kwargs": {"enable_thinking": False},
    }
    request = Request(f"{url}/chat/completions", json.dumps(data).encode(),
                      {"Content-Type": "application/json"})
    first = None
    tokens = None
    done = False
    start = perf_counter()
    with urlopen(request, timeout=120) as response:
        for line in response:
            if not line.startswith(b"data: "):
                continue
            if line.strip() == b"data: [DONE]":
                done = True
                break
            chunk = json.loads(line[6:])
            if chunk.get("usage"):
                tokens = chunk["usage"]["completion_tokens"]
            if first is None and any(choice["delta"].get("content") for choice in chunk["choices"]):
                first = perf_counter()
    if first is None or not tokens or not done:
        raise RuntimeError("Incomplete stream, token usage or response")
    return (first - start) * 1000, (perf_counter() - start) * 1000, tokens


def p95(values):
    return round(sorted(values)[math.ceil(len(values) * 0.95) - 1], 1)


def benchmark(url, model, concurrency):
    start = perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        observations = list(pool.map(lambda prompt: generate(url, model, prompt), PROMPTS))
    elapsed = perf_counter() - start
    ttft, latency, tokens = zip(*observations)
    return {
        "concurrency": concurrency, "requests": len(observations),
        "p95_ttft_ms": p95(ttft), "p95_e2e_ms": p95(latency),
        "output_tokens": sum(tokens),
        "output_tokens_per_second": round(sum(tokens) / elapsed, 2),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--model", default="qwen-hospital")
    options = parser.parse_args()
    endpoint = options.url.rstrip("/")
    generate(endpoint, options.model, "用一句话介绍医院后勤。")
    results = [benchmark(endpoint, options.model, workers) for workers in (1, 4)]
    print(json.dumps({"model": options.model, "runs": results}, indent=2))
