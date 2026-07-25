<!--
Write the complete English description first, then provide an equivalent
complete Japanese description after the separator. Keep every fact,
verification result, risk, and external-evidence record aligned.
-->

## Summary

<!-- What changed and why. -->

## Related issue and acceptance criteria

- Related:
- [ ] The mapping between acceptance criteria, changes, and tests is documented below.

| Acceptance criterion | Changed area | Verification evidence |
|---|---|---|
|  |  |  |

## Scope and impact

- Changed files:
- Areas intentionally unchanged:
- Shared-contract impact (CSV/GCS/Sheets/entrypoint/env/payload):
- Dependency changes: None / Yes (include the reason and review result)

## Verification

| Command | Result |
|---|---|
| `python scripts/check.py` |  |
| `git diff --check` |  |

- Screenshots or other verification evidence:
- Verification not performed and why:

## External evidence and deployment

- [ ] No external service was contacted, or the target, purpose, approval, and result are recorded below.
- [ ] GCP was not contacted, or the target, purpose, approval, and result are recorded below.
- [ ] Cloud Run was not deployed, or the specific approval required by `AGENTS.md` is recorded below.
- [ ] No Cloud Run revision was deleted. If deletion is needed, the AI identifies the candidates, reason, traffic state, and rollback impact, and a human performs it in a human-only environment.
- Approval record:
- Revision:
- Traffic percentage to the new revision:
- URL and health-check result:

## Permissions and infrastructure

- [ ] IAM was not changed.
- [ ] IAP was not changed.
- [ ] Secrets were not changed.
- [ ] Google Cloud APIs were not changed.
- [ ] No Project was created, deleted, or switched.
- [ ] No bucket was created or deleted, and bucket IAM was not changed.

## Risks and recovery

- Security risk:
- Data-integrity risk:
- Rollback method:
- Residual risk:

## Human review

- [ ] Acceptance criteria and evidence
- [ ] Shared-contract impact
- [ ] Security and data integrity
- [ ] Omitted verification and residual risks
- [ ] For a deployment: separate approval of the target, command, traffic, and rollback

---

## 概要

<!-- 何を、なぜ変更したか。 -->

## 関連Issueと受け入れ条件

- Related:
- [ ] 受け入れ条件と変更・テストの対応を以下に記載した

| 受け入れ条件 | 変更箇所 | 検証証拠 |
|---|---|---|
|  |  |  |

## 変更範囲と影響

- 変更ファイル:
- 変更していない領域:
- 共有契約への影響（CSV/GCS/Sheets/entrypoint/env/payload）:
- 依存関係変更: なし / あり（理由とレビュー結果を記載）

## 検証

| 実行したコマンド | 結果 |
|---|---|
| `python scripts/check.py` |  |
| `git diff --check` |  |

- スクリーンショットまたはその他の検証証拠:
- 未実施の検証と理由:

## 外部証跡・デプロイ

- [ ] 外部サービスへ接続していない、または接続先・目的・承認・結果を以下に記録した
- [ ] GCPへ接続していない、または対象・目的・承認・結果を以下に記録した
- [ ] Cloud Runへデプロイしていない、または `AGENTS.md` で必要な個別承認を以下に記録した
- [ ] Cloud Run Revisionを削除していない。必要な場合は、AIが候補・理由・トラフィック状態・ロールバック影響を提示し、人間専用環境で人間が実施する
- 承認記録:
- Revision名:
- 新Revisionへのトラフィック割合:
- URL・ヘルスチェック結果:

## 権限・インフラ確認

- [ ] IAMを変更していない
- [ ] IAPを変更していない
- [ ] Secretを変更していない
- [ ] Google Cloud APIを変更していない
- [ ] Projectを作成・削除・切替していない
- [ ] bucketを作成・削除しておらず、bucket IAMも変更していない

## リスクと復旧

- セキュリティリスク:
- データ整合性リスク:
- ロールバック方法:
- 残存リスク:

## 人間が確認すべき事項

- [ ] 受け入れ条件と証拠
- [ ] 共有契約への影響
- [ ] セキュリティ・データ整合性
- [ ] 未実施検証と残存リスク
- [ ] デプロイがある場合、対象・コマンド・トラフィック・ロールバックの個別承認
