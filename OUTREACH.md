# Outreach Drafts — PREPARED, NOT SENT

Positioning: CortexCloud On-Chain Data API - api.cortexcloud.org

Posting requires Jonathan's accounts/approval. Each draft is written to be
legitimate (no spam, no fabricated metrics). Measure clicks via
utm_source links (tracked by /v1/track).

## E3 — Show HN (Hacker News)
Title: Show HN: CortexCloud — pay-per-call on-chain data API for agents (x402, USDC on Base)

> I built CortexCloud On-Chain Data API — a pay-per-call blockchain data API at
> api.cortexcloud.org, settled by x402 (USDC on Base, no API keys).
>
> Agents read token prices, ERC-20 balances, NFT ownership, transaction
> history, blocks, gas, wallet profiles, whale alerts, and a token-intel
> endpoint that returns deployment, metadata, price, and risk evidence in one
> call. Prices run $0.004–$0.070 per call; whale-alert webhook registration is
> $0.100 plus $0.020 per delivered alert.
>
> Every paid response is evidence-backed: each fact carries its source, a
> checked_at timestamp, and an explicit missing-data indicator when a value
> could not be resolved. Data comes from Alchemy and CoinGecko across
> ethereum, base, arbitrum, polygon, and optimism.
>
> Agent flow: GET /v1/capabilities (free) lists routes and prices; a paid call
> returns an x402 challenge; the agent signs with a Base wallet and retries.
> No signup, no API keys — the wallet is the account. MCP server for
> Claude/Cursor/Codex:
> `claude mcp add cortexcloud --transport http https://api.cortexcloud.org/mcp`
>
> Free to probe: https://api.cortexcloud.org/?utm_source=hn
>
> Why x402: agents need micropayments without accounts. Happy to discuss the
> evidence model, the batch aggregate routes, or the MCP tooling.

## E4a — r/ethereum or r/ethfinance
Title: [P] Pay-per-call on-chain data API for agents — token intel, whale alerts, balances over x402

> CortexCloud On-Chain Data API serves token prices, ERC-20 balances, NFT
> ownership, transaction history, blocks, gas, wallet profiles, and whale
> alerts for ethereum, base, arbitrum, polygon, and optimism. Agents pay per
> call with x402 micropayments (USDC on Base) — $0.004 to $0.070.
>
> Every response carries source attribution, a checked_at timestamp, and
> explicit missing-data indicators; nothing is fabricated. Free to probe:
> https://api.cortexcloud.org/?utm_source=reddit_eth
> MCP: https://api.cortexcloud.org/mcp

## E4b — r/algotrading / r/cryptodevs
Title: [P] An on-chain data API agents can pay per call — whale alerts, token risk, cross-chain comparison

> CortexCloud On-Chain Data API exposes large-transfer whale alerts, token
> risk verdicts with per-claim evidence, and cross-chain contract comparison
> as per-call endpoints. Settlement is x402 (USDC on Base), so an agent wallet
> is the only account needed. Prices are $0.004–$0.070 per call.
>
> Data is sourced from Alchemy and CoinGecko; responses are evidence-backed
> with source and checked_at on every fact. Free route list:
> https://api.cortexcloud.org/?utm_source=reddit_algo
> MCP: https://api.cortexcloud.org/mcp

## E8 — X post (#x402 #aiagents #web3)
> On-chain data infrastructure for AI agents is live.
> Token intel, whale alerts, balances, tx history — $0.004 to $0.070 per call, paid over x402 (USDC on Base).
> Evidence-backed responses: source + checked_at on every fact.
> MCP-ready: claude mcp add cortexcloud --transport http https://api.cortexcloud.org/mcp
> https://api.cortexcloud.org/?utm_source=x
