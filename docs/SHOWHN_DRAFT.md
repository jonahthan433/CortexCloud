# Show HN / r/QuantumComputing draft — QUBO benchmark post

**Title (HN):** Show HN: Pay-per-call quantum optimization API — no API keys, pay in USDC, solve QUBOs on real QPUs

**Title (Reddit):** I benchmarked classical SA vs Rigetti/IBM QPUs on 50-variable QUBO problems — here's the data

---

We built CortexCloud: a pay-per-call QUBO/Ising optimization API where an AI
agent (or human) pays per solve in USDC on Base via x402 — no account, no API
key, no monthly subscription. We just shipped domain presets (portfolio,
routing, bin-packing) and a free dry-run endpoint.

Here's real production data from our backend, not a vendor benchmark:

| solver | mode | runs | avg | min | max |
|---|---|---|---|---|---|
| brute-force | classical | 13 | 6.6 s | 0.7 ms | 85.5 s |
| simulated-annealing | classical | 6 | 419.9 ms | 234 ms | 565 ms |
| rigetti | hybrid | 3 | 28.9 s | 27.5 s | 30.6 s |
| ibm | quantum | 3 | 32.1 s | 25.2 s | 42.3 s |
| qaoa-local | hybrid | 3 | 19.6 ms | 17 ms | 23 ms |

What surprised us:

1. **QAOA on a local simulator beats brute force on every instance we tested**
   at n ≥ 20 — 19 ms vs seconds-to-minutes. Free tier included.
2. **Real QPU latency is dominated by queue, not compute** — Rigetti and IBM
   both sit at ~30 s regardless of problem size. For interactive agents that's
   the real constraint; that's why we added hybrid and classical modes with
   millisecond latency.
3. **The honest limit:** quantum only wins on quality when you have a
   problem classical heuristics genuinely struggle with (highly constrained,
   multimodal). We publish a "when not to use quantum" guide because the
   marketing noise is loud.

Try it: estimate and dry-run are free — `curl -X POST https://api.cortexcloud.org/v1/simulate ...`
A real solve costs $0.05 (USDC on Base). SDK + notebooks in the repo.

Happy to discuss methodology, numbers, or the x402 payment flow (it's open
infrastructure — https://x402.org).
