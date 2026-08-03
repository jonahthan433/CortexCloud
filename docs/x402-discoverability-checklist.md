# x402 Discoverability — Status Checklist

Ground truth as of 2026-08-03 (verified against repo on CT105 + live site).

- [x] T1 Bazaar diagnosis — payTo wallet: CDP-key-derived (0xab55b97638b202059eec3104c334dfc588018008), matches systemd/.env/CDP secret. EXTENSION-RESPONSES header check: not re-run (was flaky via Cloudflare); pending re-verify.
- [x] T2 discoverable metadata — `discoverable: true` added to 402 challenge extensions.bazaar (middleware/x402.py L466); per-route INPUT_SCHEMAS + bazaar schema/example blocks confirmed live in challenge.
- [x] T3 /.well-known/x402.json — LIVE (200, 27 endpoints, merchant_wallet = CDP wallet). Cloudflare edge intermittently 530s (error 1033); origin OK.
- [x] T4 /llms.txt — LIVE (200 text/plain).
- [ ] T5 dashboard zero-value finding — not written yet.
- [ ] T6 catalog/registration payloads — not started (no branches/PRs found).
