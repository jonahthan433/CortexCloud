# Off-host backup configuration (audit P2-2)

Production backups live in /var/backups/cortexcloud/ on CT105 (on-host,
14-day retention, daily 02:30 UTC via /root/cc_backup.sh).

## Off-host push

CC_BACKUP_RCLONE_REMOTE in /etc/cortexcloud/cortexcloud.env points
the backup script at an rclone remote. Current value is a local
PLACEHOLDER (cc_offhost:/var/backups/cortexcloud/offhost) -- same
disk as on-host, so it does NOT provide true CT-loss safety yet.

## Swap to a real cloud (one-line config change)

    # Example: Backblaze B2
    rclone config create cc_b2 b2 account=<id> key=<key>
    sed -i 's|^CC_BACKUP_RCLONE_REMOTE=.*|CC_BACKUP_RCLONE_REMOTE=cc_b2:cortexcloud|' /etc/cortexcloud/cortexcloud.env

    # Example: Synology / Nextcloud WebDAV
    rclone config create cc_nextcloud webdav url=https://nextcloud/remote.php/webdav user=<u> pass=$(rclone obscure <p>)
    sed -i 's|^CC_BACKUP_RCLONE_REMOTE=.*|CC_BACKUP_RCLONE_REMOTE=cc_nextcloud|' /etc/cortexcloud/cortexcloud.env

## Restore test

/root/cc_restore_test.sh (weekly Sun 03:30 UTC via cron) restores the
most recent off-host dump into a fresh Postgres database and verifies
critical tables (x402_payments, opt_jobs, benchmarks, auto_jobs)
exist with matching row counts. Confirmed manually on 2026-09-01:
RESTORE OK with all 4 table counts matching the live DB exactly
(164/29/22/3).
