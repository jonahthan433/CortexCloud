# Off-host backup configuration (audit P2-2)

Production backups live in /var/backups/cortexcloud/ on CT105 (on-host,
14-day retention, daily 02:30 UTC via /root/cc_backup.sh).

## Off-host push (truly off-host as of 2026-09-01)

CC_BACKUP_RCLONE_REMOTE in /etc/cortexcloud/cortexcloud.env points
the backup script at an rclone **sftp** remote `cc_ninyi` which
targets the PVE host (ninyi, 192.168.1.11) at
/var/backups/cortexcloud-on-ninyi/cortexcloud/db/. This is a separate
VM (different filesystem, different failure domain) from CT105, so a
total CT105 loss does NOT lose the backup history.

Trust: a dedicated ed25519 keypair (no passphrase) at
/root/.ssh/cc_backup_ed25519 on CT105; public key added to
root@192.168.1.11:/root/.ssh/authorized_keys with comment
"ct105-cortexcloud-backup". rclone config lives in
/root/.config/rclone/rclone.conf (mode 600, root-only).

The earlier `cc_offhost` local remote is preserved as a fallback but
no longer the primary destination.

## Swap to a real cloud (one-line config change)

    # Example: Backblaze B2
    rclone config create cc_b2 b2 account=<id> key=<key>
    sed -i 's|^CC_BACKUP_RCLONE_REMOTE=.*|CC_BACKUP_RCLONE_REMOTE=cc_b2:cortexcloud|' /etc/cortexcloud/cortexcloud.env

    # Example: Synology / Nextcloud WebDAV
    rclone config create cc_nextcloud webdav url=https://nextcloud/remote.php/webdav user=<u> pass=$(rclone obscure <p>)
    sed -i 's|^CC_BACKUP_RCLONE_REMOTE=.*|CC_BACKUP_RCLONE_REMOTE=cc_nextcloud|' /etc/cortexcloud/cortexcloud.env

## Restore test

/root/cc_restore_test_offhost.sh runs the real end-to-end restore:
pulls the latest dump FROM the off-host remote (rclone copy
`cc_ninyi:/var/backups/cortexcloud-on-ninyi/...` -> /tmp stage),
creates a fresh Postgres database, pg_restores, and verifies 4
critical tables (x402_payments, opt_jobs, benchmarks, auto_jobs)
plus a spot-check of the 3 most recent settled payments. Confirmed
manually on 2026-09-01: RESTORE OK with all 4 table counts
matching the live DB exactly (169/30/23/3) and the latest
settled payments correctly tagged `category=automation`.

## Stray .env removed (audit P2-3)

The duplicate secrets file at /opt/CortexCloudAPI/.env was removed on
2026-09-01 (shred -u -n 3). All secrets now live exclusively in
/etc/cortexcloud/cortexcloud.env (mode 600). The systemd unit reads
from /etc/cortexcloud/cortexcloud.env via EnvironmentFile. The
backup script sources the env file itself, so cron runs work without
external setup.
