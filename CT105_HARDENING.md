# CT105 Production Hardening — Baseline Audit & Change Plan

Date: 2026-08-08/09. Read-only audit completed BEFORE any change; rollback
snapshot taken before the first change. Author: Hermes agent.

## 1. Current State (as-audited) — see section 4 log; all findings below addressed

## 2. Rollback Point
- **`pct snapshot 105 pre-hardening`** (2026-08-09 00:54:29 UTC, live fs-thawed).
  Rollback: `pct rollback 105 pre-hardening`. Also cleared a stale `lock: mounted`
  property in 105.conf (pct unlock) that blocked snapshot/backup ops.

## 3. Changes Made (implementation log)
| # | Change | Result |
|---|---|---|
| 1 | PG bound to loopback only (`listen_addresses=127.0.0.1`), auth verified with .env password | `ss` shows 127.0.0.1:5432 only; AUTH_OK after restart |
| 2 | docker-compose.yml POSTGRES_PASSWORD aligned to actual (strong, existing) password | metadata only |
| 3 | Removed duplicate crash-looping docker redis (system redis serves the app); volume retained staged | `docker ps`: only cortexcloud-db |
| 4 | Disabled legacy cortexcloud-gateway.service (:8080, dead MCP, no tunnel ingress) + postfix | one instance per service |
| 5 | systemd hardening cortexcloud.service + cortexcloud-mcp.service: MemoryMax 1G/512M, MemoryHigh 768M/384M, CPUQuota 300%/100%, NoNewPrivileges, PrivateTmp, ProtectHome, ProtectSystem=full, TimeoutStopSec 30/20, RestartSec 5, StartLimit 600s/8 | both active, API 200, MCP up |
| 6 | nftables on CT105: INPUT drop-policy allowlist (loopback, established, icmp, ssh from LAN, :8000/:3100 from ninyi only); OUTPUT open | public API + MCP still 200 via tunnel; local paths OK |
| 7 | sshd hardening ninyi + CT105: PasswordAuthentication no, PermitRootLogin prohibit-password, MaxAuthTries 3 | key logins verified on both |
| 8 | journald cap CT105: SystemMaxUse=200M, SystemKeepFree=512M, vacuumed | bounded |
| 9 | PG daily backup `/root/cc_backup.sh` (pg_dump -Fc, 14-day retention) cron 02:30 | first dump 52K OK |
| 10 | Weekly verified restore test `/root/cc_restore_test.sh` (scratch container, row-count compare) cron Sun 03:30 | **PASS: benchmarks 1=1, x402_payments 0=0, opt_jobs 2=2** |
| 11 | Weekly maintenance `/root/cc_maintenance.sh` (PG vacuum/analyze, git gc w/ stale-lock guard) cron Sun 04:30 | installed |
| 12 | Weekly CT-level backup on ninyi: `vzdump 105 --mode snapshot --compress zstd` cron Mon 01:15 + rotation (keep 3) | test run completed (see backup list) |
| 13 | Infra watchdog `cc_infra_watch.py` (Hermes cron `cc-infra-watch` every 10m, silent-ok): disk 70/80/90, RAM<256MB, service restarts, docker health, API 5xx/402 bursts, WAL growth, payments | verified silent-ok + alert paths |
| 14 | hermes-gateway.service StartLimit 600s/8 (applies next restart) | shown 10min/8 |

## 4. Public Exposure (post-hardening)
- **Public internet (via cloudflared tunnel only):** api.cortexcloud.org/mcp* -> :3100,
  api.cortexcloud.org + cortexcloud.org -> :8000. TLS at Cloudflare edge. Everything else 404.
- **LAN (192.168.1.0/24):** CT105 ssh :22 (keys only), nothing else (firewall drops;
  PG/redis loopback-only). ninyi: ssh :22 (keys), Proxmox :8006, tailscale.
- **Not reachable from anywhere:** PG :5432, redis :6379, old gateway :8080 (disabled),
  docker API (unix socket).

## 5. Backup Locations
- PG dumps: CT105 `/var/backups/cortexcloud/db/cortexcloud-*.dump` (daily 02:30, 14 kept)
- Restore test log: CT105 `/var/log/cc_restore_test.log`
- Full CT backups: ninyi `/var/lib/vz/dump/vzdump-lxc-105-*.tar.zst` (weekly Mon 01:15, 3 kept)
- Rollback snapshot: `pre-hardening` (until manually removed)
- Hermes side: hermes db snapshots (~/.hermes/backups), cron cc-state-refresh

## 6. Recovery Procedures
- **App down:** `ssh root@192.168.1.11 "pct exec 105 -- systemctl restart cortexcloud"` (auto-restarts anyway; 5s backoff, 8/600s cap)
- **PG container down:** `pct exec 105 -- docker restart cortexcloud-db` (restart=always)
- **PG data loss:** restore latest dump:
  `pct exec 105 -- bash /root/cc_restore_test.sh` (validates) then
  `docker exec -i cortexcloud-db pg_restore -U postgres -d cortexcloud --clean --no-owner < /var/backups/cortexcloud/db/<latest>.dump`
- **Whole CT lost:** `pct restore 105 /var/lib/vz/dump/vzdump-lxc-105-<latest>.tar.zst` (RTO ~10-20 min) or `pct rollback 105 pre-hardening`
- **Revert any hardening change:** `pct rollback 105 pre-hardening` (pre-change state)
- **Redis:** system redis 127.0.0.1:6379, restart: `pct exec 105 -- systemctl restart redis-server`
- **Hermes gateway:** `systemctl --user restart hermes-gateway` (limits: 8 restarts/600s)

## 7. Remaining Risks (accepted / noted)
- RPO for PG = up to 24h (daily dumps; WAL archiving not enabled). Acceptable at this scale;
  enable `archive_mode=on` if sub-24h RPO needed.
- Backup storage is on the SAME physical host (ninyi local disk) — protects against
  accidental deletion/corruption, NOT against host loss. Off-site copy is the next step
  (e.g. rclone to cloud storage) if 3-2-1 is required.
- Legacy gateway code remains on disk (/opt/cortexcloud-gateway, disabled) — reclaim
  when confirmed unused.
- Proxmox :8006 + rpcbind :111 on ninyi are LAN/tailscale-reachable (no public IP) — ok.
- Docker redis volume (cortexcloudapi_redis_data) retained staged — remove when confirmed stale.
- systemd has no native exponential backoff; RestartSec=5 + StartLimit 600s/8 caps crash loops.
