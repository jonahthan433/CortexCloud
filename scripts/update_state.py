#!/usr/bin/env python3
"""Regenerate the Live Snapshot section of CORTEXCLOUD_STATE.md (weekly cron).

Runs on CT105 with the cortexcloud venv. Read-only: git SHA, service states,
prices from app.x402.pricing, DB counts (benchmarks/payments/revenue).
"""
import asyncio
import subprocess
import sys
from pathlib import Path

ROOT = Path("/opt/CortexCloudAPI")
STATE = ROOT / "CORTEXCLOUD_STATE.md"
MARKER = "## Live snapshot"
sys.path.insert(0, str(ROOT))


def sh(cmd: str) -> str:
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()


def main() -> None:
    sha = sh("git -C /opt/CortexCloudAPI rev-parse --short HEAD")
    date = sh("date -u +%Y-%m-%dT%H:%MZ")
    svcs = {s: sh(f"systemctl is-active {s}") for s in ("cortexcloud", "cortexcloud-mcp")}

    from app.x402.pricing import MARKUP, MODE_PRICE_USD, PROVIDER_COST_USD, effective_price_usd

    prices = {
        m: {"list": MODE_PRICE_USD[m], "est_cost": PROVIDER_COST_USD.get(m, 0.0), "effective": effective_price_usd(m)}
        for m in MODE_PRICE_USD
    }

    from sqlalchemy import func, select

    from app.database.session import AsyncSessionLocal
    from app.models import Benchmark, Payment

    async def counts():
        async with AsyncSessionLocal() as db:
            b = (await db.execute(select(func.count(Benchmark.id)))).scalar() or 0
            p = (await db.execute(select(func.count(Payment.id)))).scalar() or 0
            rev = (await db.execute(select(func.coalesce(func.sum(Payment.amount_usd), 0.0)))).scalar() or 0.0
            return int(b), int(p), float(rev)

    b, p, rev = asyncio.run(counts())

    lines = [
        f"- commit: `{sha}` ({date} UTC)",
        f"- services: API={svcs[.cortexcloud.]} MCP={svcs[.cortexcloud-mcp.]}",
        "- prices (list / est provider cost / effective): "
        + "; ".join(f"{m} ${v['list']:.2f} / ${v['est_cost']:.2f} / ${v['effective']:.2f}" for m, v in prices.items()),
        f"- markup: {MARKUP}x",
        f"- benchmark_rows: {b}   payments: {p}   revenue_usd: {rev:.6f}",
        "- live QPU execution: off by default (QUANTUM_LIVE_EXECUTION=false)",
    ]
    text = STATE.read_text()
    STATE.write_text(text.split(MARKER)[0] + MARKER + "\n\n" + "\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
