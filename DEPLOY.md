# CortexCloud — private/enterprise deployment

A self-contained module: FastAPI (api), the 4-tool MCP server (mcp),
PostgreSQL (postgres), and local classical/hybrid solvers. Two modes:

- **public** — x402/USDC settlement on Base, exactly like api.cortexcloud.org
- **private** — single-tenant, static API key (`x-api-key` header),
  no blockchain, no public queues, data never leaves your server

## Requirements

- Linux server (x86_64), Docker Engine ≥ 24 + Compose v2
- 2 GB RAM minimum, 4 GB recommended; ~10 GB disk
- An A record (e.g. `opt.yourdomain.com`) if you want TLS at the edge

## Install (one command flow)

```bash
git clone https://github.com/jonahthan433/CortexCloudAPI.git
cd CortexCloudAPI
cp .env.example .env
# edit .env — at minimum:
#   PRIVATE_API_KEY / X402_ENABLED toggle
#   POSTGRES_PASSWORD
openssl rand -hex 24          # -> paste into PRIVATE_API_KEY
docker compose up -d --build
```

First boot runs `db-init` (creates the schema), then starts `api` and `mcp`.

Verify:

```bash
curl -s http://localhost:8000/health          # {"status":"ok",...}
curl -s -H "x-api-key: $YOUR_KEY" \
  -X POST http://localhost:8000/v1/estimate \
  -H "content-type: application/json" \
  -d '{"problem_type":"qubo","n":6,"data":{"linear":[1,-2,3,-4,2,-1]}}'
# 200 — free estimate. Without the key you get 401.
```

## Mode switch

### Private single-tenant (recommended for enterprises)

```dotenv
X402_ENABLED=false
PRIVATE_API_KEY=<openssl rand -hex 24>
```

- Every request except `/health` must send `x-api-key: <key>`; wrong or
  missing key = `401`.
- The x402 paywall is disabled: `/v1/optimize` runs immediately after the
  key check. No wallet, no USDC, no facilitator.
- Put the instance behind your VPC / corporate ingress; the key is the
  second layer for any accidental exposure.
- Client example:

```bash
curl -X POST https://opt.yourdomain.com/v1/optimize \
  -H "x-api-key: $KEY" -H "content-type: application/json" \
  -d '{"mode":"auto","problem":{"problem_type":"qubo","n":4,
       "data":{"0,0":1,"0,1":-1,"1,1":1}}}'
```

### Public x402 gateway mode

```dotenv
X402_ENABLED=true
PRIVATE_API_KEY=            # must be empty
WALLET_ADDRESS=0x…          # settlement wallet
X402_FACILITATOR_API_KEY_ID=…
X402_FACILITATOR_API_KEY_SECRET=…
X402_RESOURCE_BASE=https://opt.yourdomain.com
```

Paid routes then issue real 402 challenges; the CDP facilitator verifies
EIP-3009 USDC transfers on Base before any solver runs.

## Private mode + MCP

The shipped MCP bundle predates the API-key gate. Options:

1. API only — clients call the REST endpoints with `x-api-key` (see above).
2. MCP over the public gateway (`CORTEXCLOUD_BASE` default).
3. Ask us for a key-aware MCP build (`CORTEXCLOUD_API_KEY` env) — a
   three-line change in the bundle's HTTP client, shipped on request.

If you run MCP against this instance, set:

```dotenv
CORTEXCLOUD_BASE=http://api:8000
```

## TLS (recommended)

The stack itself serves HTTP; put Caddy or a cloud LB in front:

```caddyfile
opt.yourdomain.com {
    reverse_proxy 127.0.0.1:8000
}
```

## Operations

```bash
docker compose ps                 # status
docker compose logs -f api        # logs
docker compose up -d --build      # apply updates
docker compose down               # stop (data persists in the pgdata volume)
docker run --rm -v cortexcloudapi_pgdata:/data alpine tar czf - /data \
  > backup-$(date +%F).tar.gz     # DB backup
```

## Costs & limits

- Private mode: no per-call fees; pricing is the license agreement.
- `MAX_OPTIMIZE_VARS=5000` caps problem size; raise at your own memory risk.
- Quantum backends stay off unless you add provider tokens — the local
  classical (exact n≤20, simulated-annealing to 5,000 vars) and hybrid QAOA
  solvers need no external services.

Questions: hello@cortexcloud.org
