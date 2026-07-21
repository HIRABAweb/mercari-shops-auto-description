# Claude Code entry point

- Read the root `AGENTS.md` before starting. It is the authoritative AI instruction source.
- Follow `README.md`, `PROJECT_STATUS.md`, `TASKS.md`, and `docs/`; deployment safety is in `docs/deployment-safety.md`.
- Run the shared verification with `python scripts/check.py`.
- Unapproved external-service operations and deployments are prohibited. Cloud Run deployment is allowed only after the exact explicit approval process in `AGENTS.md`.
- AI agents must never change IAM, IAP, Secrets, APIs, Projects, or buckets.
- Do not infer unknown requirements.
- Do not explore, edit, stage, or commit unrelated untracked assets.
