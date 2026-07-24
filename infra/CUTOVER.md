# Blue-green cutover: MVP → v2

## Current state

| Service | Path / port |
|---------|-------------|
| v1 MVP | `/opt/aipal` → `:8101` |
| v2 API | `/opt/aipal-v2` → `:8102` (after deploy) |

## Cutover steps

1. Deploy v2: `ansible-playbook -i inventory.ini playbooks/deploy-v2.yml`
2. Run migration dry-run: `python3 scripts/migrate_from_mvp.py --sqlite /var/lib/aipal/app.db`
3. Update Caddy to route `/api/v2` → `8102` (or replace `8101` after validation)
4. Upload Flutter AAB v2.0.0 (versionCode 6) to Play Internal
5. Validate auth, Live session, tasks, morning/evening payloads
6. Decommission v1 `main.py` static mount when mobile v2 validated

## Rollback

Point Caddy back to `:8101`; mobile `.env` can target v1 `/api/*` temporarily.
