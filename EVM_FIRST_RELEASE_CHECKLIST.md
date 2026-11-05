# EVM-First Production Release Checklist

Status: preparation only. This checklist does not authorize production changes.
Target: CortexCloud On-Chain Data API on Base x402, with EVM data/intelligence routes only.
Explicitly out of scope for this release: Solana enablement, Helius provisioning, production migration, merge, and deployment until separately approved.

## Evidence recorded
- [x] Funded staging buyer completed a Base USDC x402 transaction on CT105 staging.
- [x] On-chain settlement: `0xe0cf8be4826bfe70fb4eee9ffad527d1224b40332b7627ba65fa7de1525a412b`, success status `0x1`, block 53553894, 2026-11-05 16:45:35 UTC; 4,000 atomic USDC = $0.004 transferred.
- [x] Paid API response: HTTP 200 from `POST /v1/data/token-price`; decoded `X-PAYMENT-RESPONSE` reports success on `eip155:8453` and references the same settlement transaction.
- [x] Billing ledger: `x402_payments` row id 294, settled, $0.004, endpoint `/v1/data/token-price`, timestamp 2026-11-05 16:45:38 UTC.
- [x] Strong cross-link: the ledger nonce matches the EIP-3009 `AuthorizationUsed` log topic in the settlement receipt. Buyer balance moved exactly from 0.103977 to 0.099977 USDC.
- Evidence was supplied by the operator. No secrets or key material are stored in this repository; raw evidence artifacts were not committed.
- Isolation caveat: no dedicated staging subdomain exists. `api.cortexcloud.org` is the only ingress and fronts CT105. This proves the staging transaction flow, not independent staging/production isolation.
- Earlier CI run #254 on head `5f13d1b` passed. The documentation update below triggers fresh CI; confirm it on the final head.

## EVM-only release scope
- Enable only the advertised EVM chains: Ethereum, Base, Arbitrum, Polygon, and Optimism.
- Confirm DATA_ENABLED=true and a valid Alchemy provider credential in the production secret manager.
- Confirm x402 is enabled for Base USDC settlement and the configured recipient/facilitator values match the intended production deployment.
- Keep HELIUS_VERIFIED=false and do not configure/enable Solana. Verify /v1/capabilities omits Solana or reports it as not configured.
- Verify the public route catalog, pricing, OpenAPI, llms.txt, agentsearch, bazaar, and MCP catalog agree with the actual EVM-only routes.

## Required production preflight
- [ ] Latest CI green on the exact release head; migration upgrade succeeds against PostgreSQL.
- [ ] Production config reviewed without exposing secrets: ENV, DATA_ENABLED, X402_ENABLED, WALLET_ADDRESS, facilitator credentials, X402_NETWORK=eip155:8453, ALCHEMY_API_KEY, DATABASE_URL, and webhook signing secret.
- [ ] Confirm no placeholder/default database password and no test/staging credentials in production.
- [ ] Cloudflare edge redirects HTTP to HTTPS; HSTS is enabled and verified on the public hostname.
- [ ] Authentication and authorization checks pass for internal endpoints, billing APIs, metrics, and key revocation. Internal metrics must remain token-gated.
- [ ] Rate limits, request validation, CORS allowlist, security headers, and webhook signature verification are reviewed against the production hostname and intended browser clients.
- [ ] Outbound operational alert destination configured and a test alert received.
- [ ] Confirm a fresh PostgreSQL backup exists, verify restore procedure, confirm disk capacity, and record the exact rollback commit/artifact.
- [ ] Review Alembic current revision vs target head; rehearse upgrade and rollback on a production-like copy. Do not assume a downgrade is safe without testing.
- [ ] Confirm service restart order and health checks for API, database, and MCP; verify /health, /v1/capabilities, /openapi.json, discovery endpoints, and MCP.
- [ ] Run a production paid smoke test with a controlled low-value request only after explicit deployment approval; verify USDC settlement, paid response, and ledger entry.
- [ ] Confirm dashboards/alerts cover 4xx/5xx, provider failures, payment settlement failures, latency, database health, and revenue/ledger discrepancies.

## Release sequence (approval-gated)
1. Finish code review and attach staging transaction evidence.
2. Complete infrastructure preflight and rehearse migration/rollback.
3. Obtain explicit approval for merge to main.
4. Obtain separate explicit approval for production migration/deployment.
5. Back up production, deploy the approved commit, apply migration, and run production smoke checks.
6. Publish the EVM-only launch announcement after production checks pass.

## Stop conditions
Stop and roll back the release plan (not automatically the database) if payment settlement/ledger diverges, paid handlers return incorrect data, the database migration is not reversible/recoverable, security headers or HTTPS fail, critical provider health fails, or the service health checks degrade.
