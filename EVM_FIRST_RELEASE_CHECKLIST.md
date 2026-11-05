# EVM-First Production Release Checklist

Status: preparation only. This checklist does not authorize production changes.
Target: CortexCloud On-Chain Data API on Base x402, with EVM data/intelligence routes only.
Explicitly out of scope for this release: Solana enablement, Helius provisioning, production migration, merge, and deployment until separately approved.

## Evidence already present in the repository
- Latest CI run on head c86e55d: PostgreSQL service started, Alembic upgrade passed, test suite passed (208 passed, 5 skipped, 0 failed).
- Operator reports a funded-buyer x402 staging transaction completed using an operator-controlled wallet. Attach transaction/settlement reference, paid response evidence, and matching payment/billing ledger row to the release record before calling this gate independently verified.
- The opt-in CI smoke module tests x402 challenge shape only; it is not the funded settlement proof.

## EVM-only release scope
- Enable only the advertised EVM chains: Ethereum, Base, Arbitrum, Polygon, and Optimism.
- Confirm DATA_ENABLED=true and a valid Alchemy provider credential in the production secret manager.
- Confirm x402 is enabled for Base USDC settlement and the configured recipient/facilitator values match the intended production deployment.
- Keep HELIUS_VERIFIED=false and do not configure/enable Solana. Verify /v1/capabilities omits Solana or reports it as not configured.
- Verify the public route catalog, pricing, OpenAPI, llms.txt, agentsearch, bazaar, and MCP catalog agree with the actual EVM-only routes.

## Required production preflight
- [ ] Funded staging proof recorded: Base USDC transaction hash, settlement result, successful paid API response, and matching payment ledger entry. Never store private keys or secrets in this repository.
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
