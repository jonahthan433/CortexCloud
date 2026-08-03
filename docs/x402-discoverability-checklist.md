# x402 Discoverability — Status Checklist

Ground truth as of 2026-08-03 (verified against repo on CT105 + live site).

## T1 Bazaar diagnosis — DONE
- payTo wallet kind: **CDP-key-derived** — 0xab55b97638b202059eec3104c334dfc588018008 derives from CDP_WALLET_SECRET (keccak-256 of pubkey, verified MATCH:True against systemd + .env). Not an external EOA.
- EXTENSION-RESPONSES header: **not applicable to merchant**. x402 SDK (v2.14.0) reads it only as an optional *response-side* header (facilitator→client, base64 JSON, allowlist fields status/rejectedReason/reason/code) — see x402/http/facilitator_client.py:98. Merchant discovery surface = inline extensions.bazaar block in the 402 body + `payment-required` base64 header; both present.
- Cloudflare edge intermittently returns 530/error 1033 on .well-known + paid routes (flaky since before changes; origin OK via localhost).

## T2 discoverable metadata — DONE (this session)
- `discoverable: True` added to 402 challenge extensions.bazaar (app/middleware/x402.py L466), verified live in challenge body via origin localhost.
- Per-route INPUT_SCHEMAS (middleware L121+) + INPUT_EXAMPLES/OUTPUT_EXAMPLES + bazaar schema/example blocks confirmed in challenge.
- Committed: "x402: mark endpoints discoverable in bazaar extension + status checklist".

## T3 /.well-known/x402.json — DONE
- Live 200, 8 top keys, 27 endpoints, merchant_wallet = CDP wallet 0xab55…8008, facilitator api.cdp.coinbase.com/platform/v2/x402.
- NOTE: no `discoverable` flag in the well-known manifest itself — that flag lives in per-route 402 challenges. Manifest is complete for discovery.

## T4 /llms.txt — DONE
- Live 200 text/plain; generated from model registry + ROUTE_PRICING.

## T5 dashboard zero-value finding — DONE (this session)
- **REAL GAP, not hydration.** Dashboard analytics (app/api/dashboard/routes.py get_analytics ~L347) queries SQLAlchemy models whose tables DO NOT exist in Postgres:
  - Queried: usage_logs, organizations, organization_members (UsageLog/Organization/OrgMember models)
  - Actual physical tables (CamelCase): UsageRecord, Organization, Membership, Payment, ApiKey, AuditLog, Project, RateLimit, User, Wallet, models
  - Every analytics query on the missing tables raises UndefinedTable → summary zeroed / error.
  - Real tables DO have rows: UsageRecord=3, Organization=1, Payment=1; but APIs/model layer read the snake_case ghosts.
- Fix path (not yet applied): align dashboard models/tables to the real CamelCase schema (UsageRecord with organization_id, Organization, Membership) OR create the expected tables + backfill — decision pending.

## T6 catalog/registration payloads — DONE (this session)
- **None exist.** Verified: no git branches beyond main, no stashes, no untracked payload files (untracked = deployed modules + backups only), GitHub API shows 0 PRs (open/closed/draft) on jonahthan433/CortexCloudAPI. Nothing drafted, nothing unsubmitted — no cleanup needed. If a catalog listing (e.g. Bazaar/MCP directory) is wanted, that's net-new work, not resumption.

---
ALL SIX TASKS RECONCILED. 3/6 needed work this session (T2 flag, T1+T5 findings); 3/6 were already live (T3, T4) or empty (T6).