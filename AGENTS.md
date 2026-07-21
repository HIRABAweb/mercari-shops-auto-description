# AI development instructions

This file is the authoritative instruction source for AI agents working in this repository. Read it before inspecting or changing files. `CLAUDE.md` and `CODEX.md` are entry points only; if they differ from this file, stop and ask a human.

## Project overview

- Language: Python 3.12 for local verification and CI.
- Frameworks: Functions Framework for two event-driven services and Flask for the review UI.
- `image-to-description/`: receives the GCS completion marker, reads product images and notes, calls Vertex AI Gemini, and writes `_description.txt`.
- `yahuoku-to-mercarishops/`: consumes `_description.txt`, extracts listing attributes, maps category/brand data, and writes Mercari Shops/Yahoo CSV, review data, JSON, and completion artifacts. Google Sheets sync is optional.
- `review-ui/`: Flask UI for reviewing, editing, approving, and exporting approved Mercari Shops CSV rows.
- Primary state stores: GCS objects and, when enabled, Google Sheets. Flask session state is used for CSRF protection.
- External services: GCS, Google Sheets, Vertex AI/Gemini, Secret Manager at runtime, and Cloud Run/Cloud Run Functions. Local tests must replace them with fakes or mocks.
- Source and deployment roots: the three component directories above. Shared tests are in `tests/`; the image-description component also has `image-to-description/test_image_description.py`.
- Operational documentation: `README.md`, `PROJECT_STATUS.md`, `TASKS.md`, `docs/ROADMAP.md`, `docs/operations_runbook.md`, and `docs/deployment-safety.md`.
- Optional task roles: `.agents/glammer.agent.md` is the implementation role and `.agents/ras.agent.md` is the independent review role. Their workflow is described in `.agents/README.md`; these role prompts never override this file.

## Repository boundaries

- Change only the component, test, documentation, or automation files required by the accepted task.
- Changes to `image-to-description/` must preserve its GCS event and `_description.txt` contract.
- Changes to `yahuoku-to-mercarishops/` must preserve its inputs, output object names, CSV schemas, batch isolation, and optional Sheets boundary.
- Changes to `review-ui/` must preserve server-side authorization, CSRF protection, batch scoping, and the approved-CSV contract.
- Treat CSV headers/order/encoding, GCS object naming, shared Sheet columns/status values, function entry points, environment-variable names, and cross-component payloads as shared contracts. Obtain explicit human approval before changing any of them, then update documentation and contract tests together.
- Do not explore, edit, delete, move, stage, or commit unrelated untracked assets. In particular, workspace attachments, `portfolio/`, and the separate apparel-retouch project are outside this repository's development scope.
- Never use `git add .`. Select changed files explicitly after reviewing `git status` and `git diff`.
- Commit, push, open/modify a PR, or merge only when the current task explicitly authorizes it. A main merge always requires human approval.
- Do not add, remove, or upgrade dependencies or generated lock files without explicit human approval and a documented reason.
- Do not infer missing requirements. Mark them as unconfirmed and ask a human when the choice affects behavior or a shared contract.
- Do not broadly format, refactor, or reorganize files outside the task.

## Development commands

Run commands from any directory; `scripts/check.py` resolves the repository root itself.

```text
# Install the existing test dependencies
python -m pip install -r requirements-dev.txt

# Standard test suite
python -m pytest -p no:cacheprovider tests

# Full test suite (includes the component-local image test)
python -m pytest -q -p no:cacheprovider tests image-to-description/test_image_description.py

# Shared verification used by humans, agents, and CI
python scripts/check.py

# Windows wrapper for the shared verification
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check.ps1

# Component-focused tests
python -m pytest -p no:cacheprovider image-to-description/test_image_description.py tests/test_image_description.py
python -m pytest -p no:cacheprovider tests/test_main.py tests/test_listing_content_parser.py tests/test_listing_data.py tests/test_mappers.py tests/test_csv_export.py tests/test_sheets_workflow.py
python -m pytest -p no:cacheprovider tests/test_review_ui.py tests/test_sheets_workflow.py

# Diff whitespace validation
git diff --check
```

The shared verification performs tracked-Python syntax checks, the full test suite, `python -m pip check`, and Git whitespace checks without contacting external services. Do not replace its tests with live GCP, Sheets, GCS, Gemini, email, notification, or marketplace calls.

When a task explicitly authorizes a commit, stage only the reviewed paths and rerun `python scripts/check.py` before committing; Git diff checks do not inspect untracked files.

## Invariants and safety requirements

- Never include AI-generated output in the uploadable Mercari Shops CSV before human approval.
- Do not change CSV column count, order, header text, encoding, quoting, or file format without an approved contract change.
- Do not change GCS object naming conventions without an approved contract change.
- Preserve isolation between batches in storage, Sheets, the UI, and generated CSVs.
- Preserve CSRF protection and server-side authentication/authorization; never weaken or bypass either.
- Replace external I/O with fakes or mocks in local tests.
- Never put secrets in source, logs, command lines, fixtures, screenshots, or generated documentation.
- After an approval state changes, do not leave a stale previously approved CSV available. A failure to invalidate it must fail closed and be reported.
- Treat user input and AI-generated text as data when writing to Google Sheets; never allow it to be evaluated as a formula.
- Concurrent processing of the same or different products must not cause duplicates, omissions, cross-batch mixing, or overwrites.
- Processing locks must have a reviewed stale-lock recovery path and must not remain permanent after abnormal termination.

The last four requirements are documented safety requirements. Known gaps are tracked in `TASKS.md`; do not silently claim they are implemented or change the business logic without a separate approved task.

## Operation classes

### Autonomous local work

An agent may perform the following without additional approval only when the work stays inside this workspace and does not contact an external service:

- Read code and documentation; inspect Git status, diffs, and history.
- Edit task-scoped local files.
- Run tests that use fakes/mocks, syntax checks, lint/type/build commands already present in the repository, and the shared verification command.
- Draft deployment commands, deployment plans, rollback plans, pull-request text, and code reviews without executing external operations.

Any GCP, Google Sheets, GCS, Gemini/Vertex AI, GitHub API, marketplace, email, notification, or other external operation is outside autonomous local work.

### Cloud Run deployment: explicit approval required

Cloud Run deployment is not categorically forbidden, but an agent may execute one only after every condition below is met:

- The Google Cloud project is on the human-maintained allowlist, and its exact Project ID is shown.
- Exact region, Cloud Run service, source or image, and complete command are shown.
- `python scripts/check.py` has succeeded for the proposed change.
- The change and impact are explained.
- The traffic percentage to the new revision is explicit.
- A rollback method is shown.
- A human explicitly approves that one command and target after seeing the final request.

Until a project/service/region allowlist is confirmed by a human, no deployment is eligible. Immediately before execution, present exactly:

```text
対象Project ID:
対象リージョン:
対象Cloud Runサービス:
デプロイ対象:
実行コマンド:
デプロイ前検証結果:
新Revisionへのトラフィック割合:
変更されない設定:
想定される影響:
ロールバック方法:
```

- Never reuse approval from an earlier conversation or deployment. Approval covers only the displayed command and target once.
- Obtain new approval if the project, region, service, source/image, command, or traffic percentage changes.
- A vague instruction such as “proceed” is not standing deployment permission; it is valid only as a direct response to the complete request above.
- If pre-deployment verification fails, stop without requesting deployment approval.
- Do not resolve deployment errors by expanding permissions, changing project/service names, weakening public-access settings, or switching traffic without approval.
- Do not automatically roll back unless the exact rollback was separately approved in advance.
- After deployment, report the revision, URL, health-check result, and traffic state. External health checks also require approval.
- Traffic changes and external pre/post-deployment health checks each require their own exact command and explicit human approval.

The existing `scripts/deploy_review_ui.ps1` combines application deployment with infrastructure and privilege changes. It is not an approved application-only deploy script and an AI agent must not execute it. See `docs/deployment-safety.md`.

### Always prohibited for AI agents

An AI agent must not execute the following in this project, even when a human gives conversational approval. It may only prepare a recommendation for a human operator:

- `gcloud config set project`.
- Enable or disable Google Cloud APIs; create or delete projects.
- Add, remove, or change IAM roles or IAP configuration.
- Create/delete service accounts, change their permissions, or create/retrieve service-account keys.
- Create, view, update, or delete Secret values.
- Create/delete GCS buckets or change bucket IAM.
- Delete Cloud Run revisions. If deletion is needed, only identify the candidate revisions, deletion reason, confirmed traffic state, and rollback impact; a human must perform the deletion in Google Cloud Console or a human-only administration environment.
- Repair or delete production data or manually repair production Google Sheets.
- Register, list, publish, or otherwise act on real products.
- Disable authentication/authorization or add `--allow-unauthenticated`.
- Operate on a project outside the confirmed allowlist or expand permissions to fix an error.
- Change production IAM, IAP, Secret, or bucket configuration for investigation.
- Run billable external-service experiments.
- Execute `scripts/deploy_review_ui.ps1` or `scripts/apply_iap_oauth_settings.ps1` without exception; both contain operations outside the AI execution boundary.

When one of these operations is required, do not run it. Give the human the required work, reason, recommended command, expected impact, required permissions, rollback method, and checks the human must perform.

## Deployment failure handling

- Do not fix permission errors by changing IAM.
- Do not silently change Project ID or service name and retry.
- Do not alter public access settings.
- Do not place Secret values directly on a command line.
- Do not repeat the same failed command without a specific reason and new evidence.
- If partial success is possible, report it. Checking live revision or traffic state requires explicit approval because it is external access.
- Report the error, commands already executed, confirmed current state, unknown state, and next safe step.
- Do not run an automatic rollback unless it was explicitly approved in advance.

## Definition of Done

- The acceptance criteria are met and externally observable behavior has been verified where safe.
- Relevant tests are added or updated, and `python scripts/check.py` succeeds.
- `git diff --check` succeeds.
- No unrelated file is changed, and no unrelated untracked asset is added.
- Approved shared-contract changes update documentation and contract tests together.
- Security, authorization, and data integrity are not weakened.
- The final report lists every verification command and result and explains any omitted check.
- Any external connection is reported with its target, purpose, approval, and result.
- Any deployment is reported with revision, URL, traffic, verification result, and rollback method.
