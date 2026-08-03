#!/usr/bin/env python3
"""Add 200 response schemas (content+example) to paid x402 ops in openapi.json."""
import json

SPEC = "/opt/CortexCloudAPI/openapi.json"

EXAMPLES = {
    "/x402/v1/chat/completions": {"id": "chatcmpl-abc", "object": "chat.completion", "choices": [{"index": 0, "message": {"role": "assistant", "content": "..."}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}},
    "/x402/v1/responses": {"id": "resp_abc", "object": "response", "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "..."}]}]},
    "/x402/v1/embeddings": {"id": "emb_abc", "object": "list", "data": [{"object": "embedding", "embedding": [0.01, -0.02], "index": 0}], "usage": {"prompt_tokens": 8, "total_tokens": 8}},
    "/x402/v1/data/prices": {"bitcoin": {"usd": 67000.0, "eur": 62000.0}},
    "/x402/v1/data/coins/search": {"coins": [{"id": "bitcoin", "symbol": "btc", "name": "Bitcoin"}]},
    "/x402/v1/data/dex/search": {"pairs": [{"chainId": "ethereum", "dexId": "uniswap-v2", "baseToken": {"symbol": "WETH"}, "quoteToken": {"symbol": "USDC"}}]},
    "/x402/v1/data/dex/pairs": {"pairs": [{"chainId": "ethereum", "dexId": "uniswap-v2", "priceUsd": "3500.12"}]},
    "/x402/v1/data/base/balance": {"address": "0x...", "balance": "1234567890123456789", "network": "base"},
    "/x402/v1/data/base/token-balance": {"address": "0x...", "token": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "network": "base", "raw": "5000000", "note": "balance is in token base units (USDC has 6 decimals)"},
    "/x402/v1/data/base/nonce": {"address": "0x...", "nonce": 7},
    "/x402/v1/search": {"results": [{"id": "result-id", "title": "Example result", "url": "https://example.com"}]},
    "/x402/v1/search/contents": {"results": [{"id": "result-id", "text": "Full content of the result", "url": "https://example.com"}]},
}

with open(SPEC) as f:
    spec = json.load(f)

changed = []
for path, ops in spec.get("paths", {}).items():
    for method, op in ops.items():
        if not op.get("x-payment-info"):
            continue  # paid ops only
        resp200 = op.setdefault("responses", {}).setdefault("200", {})
        if resp200.get("content"):
            continue
        resp200.setdefault("description", "Result (after valid x402 payment)")
        resp200["content"] = {
            "application/json": {
                "schema": {
                    "type": "object",
                    "example": EXAMPLES.get(path, {"ok": True}),
                }
            }
        }
        changed.append(f"{method.upper()} {path}")

with open(SPEC, "w") as f:
    json.dump(spec, f, indent=2)

print(f"updated {len(changed)} ops:")
for c in changed:
    print(" ", c)
