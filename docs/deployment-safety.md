# Deployment safety design

## Purpose and boundary

This document defines a future application-only Cloud Run deployment path. It does not authorize a deployment and contains no production identifiers or secrets.

Deployment must be split into two independent workflows:

1. **Application deployment**: build or select an already-reviewed artifact, create a Cloud Run revision, inspect it, and perform a separately approved traffic change. An AI agent may perform only this workflow after the exact approval process in `AGENTS.md`.
2. **Infrastructure bootstrap/administration**: API enablement, Project, IAM, IAP, Secret Manager, service accounts/keys, Artifact Registry administration, bucket creation/IAM, Cloud Run revision deletion, and production-data repair. This is human-only and an AI agent must never execute it.

The allowlisted Project IDs, regions, and Cloud Run services have not been confirmed in this repository. Until a human supplies and reviews that allowlist, no deployment is eligible.

Cloud Run revision deletion is never part of the AI-executable application workflow. An AI agent may only identify deletion candidates, explain the reason, report the confirmed traffic state and rollback impact, and hand the operation to a human using Google Cloud Console or a human-only administration environment.

## Required future application-only script

Prefer a new script rather than extending the existing mixed-purpose script. Its interface and implementation must:

- Accept a deployment environment or fixed target alias, not an arbitrary Project ID.
- Resolve Project ID, region, and service name from a reviewed allowlist. Validate all three again inside the script.
- Keep production and staging targets distinct and reject unknown targets.
- Never call `gcloud config set project`; pass `--project`, `--region`, and service explicitly on every command.
- Reject `--allow-unauthenticated` and any option that changes IAM, IAP, API, Secret, service-account, Project, or bucket state.
- Reject any option or subcommand that deletes a Cloud Run revision.
- Run `python scripts/check.py` first and stop on any failure.
- Require the exact source commit and image digest/tag to be visible in the approval request.
- Prefer creating a production revision with no traffic. Treat traffic changes as a separate command and separate human approval.
- Provide a non-mutating preflight/dry-run mode that prints the resolved target and commands without credentials or Secret values.
- Record the previous serving revision as the rollback candidate without changing traffic.
- Report revision, service URL, traffic state, and an approved health-check result after execution.
- Never print Secret values or put them directly on a command line.
- Stop on errors; never grant permissions, change target names, weaken authentication, or auto-rollback.

Before implementing this future script, humans must approve the target allowlist, allowed source/image strategy, build ownership, revision naming, traffic policy, and rollback operator.

## Approval sequence

1. Prepare and review the application change locally.
2. Run `python scripts/check.py`; stop if it fails.
3. Print the exact approval block required by `AGENTS.md`, including project, region, service, artifact, command, traffic percentage, unchanged settings, impact, and rollback.
4. Obtain a direct human approval for that single command and target.
5. Create the new revision, preferably with no traffic.
6. Report the created revision. Any external health check requires explicit approval.
7. If traffic should change, print a second exact command and rollback command and obtain a separate approval.
8. Report final revision, URL, health result, and traffic state.

Past approval cannot be reused. Any change to the target, artifact, command, or traffic percentage invalidates it.

## Existing script classification

The existing scripts are retained unchanged for human review. Neither is safe for AI execution.

| File/lines | Classification | Reason and AI boundary |
|---|---|---|
| `scripts/deploy_review_ui.ps1:43-45` | Project discovery and image target | Reads Project metadata and constructs an image target from arbitrary parameters. Not allowlist-bound. |
| `scripts/deploy_review_ui.ps1:54` | Dangerous default-Project mutation | Runs `gcloud config set project`; always prohibited. |
| `scripts/deploy_review_ui.ps1:56-63` | Infrastructure/API bootstrap | Enables Google Cloud APIs; human-only. |
| `scripts/deploy_review_ui.ps1:65-69` | Bucket bootstrap | Creates a bucket; human-only. |
| `scripts/deploy_review_ui.ps1:71-76` | Artifact Registry bootstrap | Creates infrastructure; human-only. |
| `scripts/deploy_review_ui.ps1:78-82` | Service-account administration | Creates a service account; human-only. |
| `scripts/deploy_review_ui.ps1:84-92` | IAM administration | Grants bucket and token-creator roles; always prohibited for AI. |
| `scripts/deploy_review_ui.ps1:101-104` | Application image build | Submits a remote Cloud Build. It is billable/external and must be part of an explicitly approved, allowlisted future workflow. |
| `scripts/deploy_review_ui.ps1:106-117` | Cloud Run application deployment plus settings | Deploys a revision and changes runtime configuration. It is approval-gated, but is inseparable here from prohibited operations and therefore the current script is excluded from AI execution. |
| `scripts/deploy_review_ui.ps1:119-131` | IAM and IAP administration | Grants invoker/IAP roles; always prohibited for AI. |
| `scripts/deploy_review_ui.ps1:133-138` | Live state/health discovery | Contacts Cloud Run and suggests a health check; external access requires approval. |
| `scripts/apply_iap_oauth_settings.ps1:28-55` | IAP and Secret-bearing configuration | Materializes an OAuth secret in a temporary YAML file and changes IAP settings; always prohibited for AI. |

Because `scripts/deploy_review_ui.ps1` mixes application deployment, build, infrastructure bootstrap, IAM, IAP, and an unsafe default-project mutation, approval for “deploy Review UI” must never be interpreted as approval to run that script.

## Failure and rollback policy

- Permission failures are reported, not fixed with IAM changes.
- Do not change Project ID, region, service, authentication, or public-access settings to retry.
- Do not repeat an identical failure without new evidence.
- If partial success is possible, list known and unknown state. Live revision/traffic inspection is itself an external operation and requires approval.
- Automatic rollback is prohibited unless its exact command and trigger were explicitly approved beforehand.
- A human-approved rollback must target the recorded prior revision and state the resulting traffic split.

## Human-only checklist

Before any production workflow exists, a human must confirm:

- Allowlisted Project IDs, regions, services, and environment separation.
- Which identity may build, deploy, inspect, switch traffic, and roll back, using least privilege.
- Existing IAM, IAP, Secret, service-account, bucket, backup, and recovery configuration.
- Artifact provenance and retention, health criteria, traffic increments, and rollback thresholds.
- The human operator and administration environment responsible for any Cloud Run revision deletion.
- Audit-log ownership and who reviews deployment evidence.
