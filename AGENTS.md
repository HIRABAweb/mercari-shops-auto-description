# AI development instructions

This file is the sole authoritative execution-rule source for Codex in this repository. Codex must read and follow it before inspecting or changing files. Mandatory safety constraints, change rules, verification steps, and deployment approval conditions belong here and must not be duplicated in another AI instruction file. Human-facing documentation may explain workflows but never overrides this file.

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

Any GCP, Google Sheets, GCS, Gemini/Vertex AI, GitHub API, marketplace, email, notification, or other external operation is outside autonomous local work unless it is an allowlisted read-only operation defined below.

### Allowlisted read-only external operations

The currently approved read-only targets are:

```text
Project ID: gen-lang-client-0122735738
Region: asia-northeast1
Cloud Run service: mercari-review-ui
Artifact Registry repository: review-ui
Cloud Run Function: image-to-description
```

An agent may perform read-only status and metadata checks against these exact targets without asking for additional approval. This includes describing the Cloud Run service or revisions, reading traffic and readiness state, describing the `review-ui` Artifact Registry repository or image metadata, reading Cloud Build status for a build initiated under an approved workflow, sending a GET request to the service `/healthz` endpoint, and describing the `image-to-description` function's state, runtime, entry point, memory, timeout, concurrency, runtime service account, and Eventarc trigger metadata.

These read-only checks must:

- Use explicit `--project`, `--region` or `--location`, and service/repository identifiers on every command.
- Request only the minimum fields needed and avoid output that can contain environment-variable values, credentials, tokens, user data, or Secret values.
- Never read or modify Google Sheets rows, GCS object contents, production product data, IAM policies, IAP policies, Secret values, service-account keys, or logs that may contain sensitive data.
- Never change traffic, configuration, IAM, IAP, APIs, Secrets, service accounts, buckets, revisions, builds, images, or production data.
- Stop if the resolved Project, region, service, repository, command scope, or output differs from the allowlist or could expose sensitive data.

Adding or changing an allowlisted target requires an explicit human-approved edit to this file. Read-only operations outside this exact allowlist still require explicit human approval.

### Billable external-service tests: explicit approval required

Billable external-service tests, including GCS writes that can trigger Cloud Run Functions, Gemini, Vertex AI, or other paid processing, are not categorically forbidden. An agent may execute one only after every condition below is met:

- The exact Project ID, account, service, bucket, source prefix, destination prefix, and affected object set are shown.
- A read-only preflight confirms the source object count, product count, trigger-file count, destination collision state, and any generated artifacts that must be excluded.
- The complete command or command sequence is shown in execution order.
- Event-triggering files such as `_SUCCESS.txt` are copied only after all non-trigger inputs have been copied and verified.
- The maximum number of products, expected external invocations, possible billable services, expected impact, stop conditions, and cost exposure are explained.
- The rollback or cleanup method is shown. If cleanup would delete or repair production data, the agent must not perform it; identify the exact prefix for a human operator instead.
- Existing IAM, IAP, API, Secret, service-account, bucket, authentication, and public-access settings are unchanged.
- A human explicitly approves the displayed command or command sequence and exact target after seeing the final request.

Immediately before execution, present exactly:

```text
実行アカウント:
対象Project ID:
対象サービス・バケット:
コピー元:
コピー先:
対象商品数・オブジェクト数:
除外対象:
実行コマンド:
実行順序:
事前確認結果:
起動し得る外部処理:
想定される課金・影響:
停止条件:
変更されない設定:
ロールバック・後片付け:
実行後確認:
```

- Approval covers only the displayed command or command sequence and target once. Never reuse approval from an earlier request or a different preflight result.
- Obtain new approval if the Project, account, service, bucket, source, destination, object set, command, execution order, or product count changes.
- Stop before any write if the preflight count differs from the displayed count, the destination is not in the displayed state, or an overwrite is possible.
- Stop after partial failure; do not retry, repair, delete, or broaden permissions automatically.
- This approval class does not permit any operation listed under “Always prohibited for AI agents”.

### Cloud Run deployment: explicit approval required

Cloud Run deployment is not categorically forbidden, but an agent may execute one only after every condition below is met:

- The Google Cloud project is on the human-maintained allowlist, and its exact Project ID is shown.
- Exact region, Cloud Run service, source or image, and complete command are shown.
- `python scripts/check.py` has succeeded for the proposed change.
- The change and impact are explained.
- The traffic percentage to the new revision is explicit.
- A rollback method is shown.
- A human explicitly approves the displayed command or command sequence and target after seeing the final request.

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
デプロイ後確認:
```

- A single approval may cover one displayed sequence that builds the reviewed source, pushes the resulting image, deploys that exact image to the allowlisted Cloud Run service, applies the displayed traffic percentage, and performs the displayed GET request to `/healthz`.
- Every command in the sequence must be shown in execution order. The source commit, image tag or digest, Project, region, service, traffic percentage, health-check URL, expected response, and rollback method must be explicit.
- The approved sequence may not contain IAM, IAP, API, Secret, service-account, bucket, Project, authentication, or public-access changes.
- Never reuse approval from an earlier conversation or deployment. Approval covers only the displayed command or command sequence and target once.
- Obtain new approval if the project, region, service, source/image, command, or traffic percentage changes.
- A vague instruction such as “proceed” is not standing deployment permission; it is valid only as a direct response to the complete request above.
- If pre-deployment verification fails, stop without requesting deployment approval.
- Do not resolve deployment errors by expanding permissions, changing project/service names, weakening public-access settings, or switching traffic without approval.
- Do not automatically roll back unless the exact rollback was separately approved in advance.
- Deployment always requires explicit approval. A deployment command or sequence that sends 100% of traffic to a new revision must state that impact explicitly and receive explicit approval before execution.
- Traffic changes not already included exactly in the approved deployment sequence require a new approval for the exact traffic command and target.
- The post-deployment `/healthz` GET may be included in the deployment approval when its exact URL, command or browser action, and expected response are displayed in advance. If it was not included, the allowlisted read-only rule permits the `/healthz` GET without another approval.
- Rollback is never covered by deployment approval. Before rollback, show the exact rollback command, source and destination revisions, resulting traffic percentage, impact, and verification step, then obtain a separate explicit approval.
- After deployment, report the revision, URL, health-check result, and traffic state.

The existing `scripts/deploy_review_ui.ps1` combines application deployment with infrastructure and privilege changes. It is not an approved application-only deploy script and an AI agent must not execute it. See `docs/deployment-safety.md`.

### Cloud Run Functions deployment: explicit approval required

The only currently approved Cloud Run Functions deployment target is:

```text
Project ID: gen-lang-client-0122735738
Region: asia-northeast1
Cloud Run Function: image-to-description
Deployment account: hirabaaiwork@gmail.com
```

An agent may execute one deployment to this exact target only after every condition below is met:

- The deployment source is a clean worktree at an explicitly displayed reviewed commit.
- `python scripts/check.py` has succeeded in that exact worktree.
- A read-only preflight has confirmed the current function state, runtime, entry point, memory, timeout, concurrency, runtime service account, and Eventarc trigger metadata.
- The complete deployment command, changed settings, unchanged settings, expected impact, stop conditions, post-deployment checks, and exact rollback command are displayed.
- A human explicitly approves the displayed deployment command and exact target after seeing the final request.

Immediately before execution, present exactly:

```text
対象Project ID:
対象リージョン:
対象Cloud Run Function:
実行アカウント:
デプロイ対象:
ソースcommit:
現在設定:
実行コマンド:
デプロイ前検証結果:
変更される設定:
変更されない設定:
想定される影響:
停止条件:
ロールバック方法:
デプロイ後確認:
```

- Approval covers only the displayed deployment command and target once. Never reuse approval from an earlier request, read-only check, edit approval, deployment, or different preflight result.
- The approved deployment may execute either the displayed direct `gcloud functions deploy` command or the displayed deployment script command, never both.
- Obtain new approval if the Project, region, function, account, source path, source commit, command, memory, concurrency, timeout, runtime, or entry point changes.
- The deployment command must not include trigger, runtime service-account, environment-variable, Secret, IAM, IAP, API, bucket, authentication, or public-access changes. Existing values for those settings must remain unchanged.
- Stop before deployment if the clean-worktree check or shared verification fails, the source commit differs, or the live function state or configuration differs from the displayed preflight.
- Stop after a failed or partially successful deployment. Do not retry, change permissions, change the trigger, or roll back automatically.
- The deployment approval does not include GCS writes, `_SUCCESS.txt` replay, production-data repair, or a Gemini/Vertex AI product test. Those actions remain governed by the billable external-service test and production-data rules.
- Post-deployment verification may read only the allowlisted function metadata fields needed to confirm state, runtime, entry point, memory, timeout, concurrency, runtime service account, and Eventarc trigger metadata.
- Rollback is never covered by deployment approval. Before rollback, display the exact rollback source commit, source path, command, settings, impact, and verification step, then obtain separate explicit human approval.
- After deployment, report the function state, update time, deployed source commit, memory, concurrency, timeout, trigger state, and verification result.

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
- Execute `scripts/deploy_review_ui.ps1` or `scripts/apply_iap_oauth_settings.ps1` without exception; both contain operations outside the AI execution boundary.

When one of these operations is required, do not run it. Give the human the required work, reason, recommended command, expected impact, required permissions, rollback method, and checks the human must perform.

## Deployment failure handling

- Do not fix permission errors by changing IAM.
- Do not silently change Project ID or service name and retry.
- Do not alter public access settings.
- Do not place Secret values directly on a command line.
- Do not repeat the same failed command without a specific reason and new evidence.
- If partial success is possible, report it. Live revision, readiness, and traffic checks against the exact allowlisted read-only target may be performed without additional approval; checks outside the allowlist require explicit approval.
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
