# Tencent VM automation

This folder manages `43.160.220.9` with Ansible.

## First hardening run

From `infra/`:

```bash
ansible-playbook -i inventory.ini playbooks/bootstrap.yml
```

## App deploy (one command)

From `infra/`:

```bash
ansible-playbook -i inventory.ini playbooks/deploy.yml
```

## Stakeholder URL

- Preferred App: `https://43.160.220.9.sslip.io`
- Alternate App: `https://43.160.220.9.nip.io`
- Health (preferred): `https://43.160.220.9.sslip.io/api/health`

## Handsfree demo notes

- Primary stakeholder narrative is **Live Voice v2** full-duplex on Companion (tap orb or say Hi Pal).
- Text mode uses REST `/turn/text`; Live uses duplex WebSocket (`LIVE_VOICE_V2=true` on API).
- For iPhone/browser tests, use a fresh tab/session when switching domains to avoid stale PWA/service worker state.

## Notes

- Inventory uses SSH key `~/.ssh/tencent_teems_ed25519.pem`.
- Remote user is `teems` with passwordless sudo.
- Deployment playbook syncs this local repo to `/opt/aipal` on the VM.
- Docker-based Ollama stays local-only; Caddy reverse-proxies public HTTPS to `127.0.0.1:8101`.
- Emergency/manual maintenance has also been performed through `root` SSH using the same VM, but Ansible should remain the preferred repeatable deploy path.

## LLM provider switch (Ollama / DeepSeek)

Set these in `infra/group_vars/all.yml` before deploy:

- `aipal_llm_provider`: `ollama` or `deepseek`
- `DEEPSEEK_API_KEY` environment variable in the deploy shell: required when provider is `deepseek`
- `aipal_deepseek_model`: for example `deepseek-chat`

Then redeploy:

```bash
ansible-playbook -i inventory.ini playbooks/deploy.yml
```
