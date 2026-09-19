# LLM-Manager

LLM-Manager は、ローカル Linux PC または既存の OpenSSH 接続先について、ハードウェア、OS、Ollama、OpenCode を診断し、用途別の最適化案を安全にレビュー・適用するデスクトップ GUI アプリケーションです。

Phase 0〜6を完了し、MVP [v0.1.0](https://github.com/NBE03xxx/LLM-Manager/releases/tag/v0.1.0)を公開しました。release setの再現build、SBOM、Ubuntu 26.04／Debian 13 lifecycle、通常GUI、security、checksum、OpenPGP署名、signed tag、公開後の認証なし再取得検証まで44/44項目を完了しています。詳細は[MVP Release Checklist](docs/release-checklist.md)と[公開後再取得検証](docs/validation/phase6-public-release-verification-2026-09-19.md)を参照してください。

MVP releaseのmutation scopeはこの4経路で固定しています。非公開経路の内部実装は将来検証用であり、現行MVPの実行権限ではありません。

- Apply: local user OpenCode、SSH user OpenCode
- Manual restore: local user OpenCode、local root Ollama

MVP の正式対象は Ubuntu 26.04 と Debian 13 で、Python 3.14.4、Ollama 0.33.2、OpenCode 1.18.25 を初期検証基準とする。Debian 13のsystem Pythonを含めるためapplication/runtimeのsupported minimumはPython 3.13、cryptography 43.0.0、SecretStorage 3.3.3とし、Debian 13 stock desktop Gateで全単体テストと暗号・Secret Service・helper境界を検証した。製品の周辺バージョンは互換性確認後に対応範囲へ追加する。開発中はソース起動を許容し、一般ユーザー向けにはdebパッケージを提供する。

UIはユーザーlocaleを初期値として日本語・英語を提供し、未対応localeは英語へフォールバックする。

## Download、検証、install

配布物の保存先は、リポジトリ直下の **`release/v0.1.0/`** です。トップdirectoryで次のscriptを実行すると、[GitHub Release v0.1.0](https://github.com/NBE03xxx/LLM-Manager/releases/tag/v0.1.0)の11配布物をそのdirectoryへdownloadし、公開鍵fingerprint、manifest署名、全checksumを自動検証します。

```bash
./release/download-v0.1.0.sh
```

成功時だけ`release/v0.1.0/`が保持されます。既存directoryは上書きしません。完全なrelease setはlocal／remote helperのdeb、source archive、直接依存SBOM、3環境のresolved-environment SBOM、公開鍵、checksum、署名の11 fileです。scriptの詳細は[`release/README.md`](release/README.md)を参照してください。

自動検証で照合するfingerprintは次のとおりです。短いkey IDだけでは判定しません。

- primary fingerprint: `353F4D4F55175F537FBCD07C3E2532969B404FFD`
- signing subkey fingerprint: `034DA1601E14BE534254BA4DD8F253C086BE34C2`

local GUI packageは、download完了後に次の具体的なdirectoryからAPTへ渡します。

```bash
cd release/v0.1.0
sudo apt install ./llm-manager_0.1.0_all.deb
```

SSH user経路を利用する場合は、`release/v0.1.0/llm-manager-remote-helper_0.1.0_all.deb`を接続先hostへ安全に転送し、そのhost上で管理者が事前導入します。local packageがSSH先へhelperを自動install／upgradeすることはありません。

```bash
sudo apt install ./llm-manager-remote-helper_0.1.0_all.deb
```

upgrade、remove、purge、既知制限、復旧時の注意は[v0.1.0 Release Notes](docs/release-notes-0.1.0-draft.md)と[Backup・Rollback・Recoveryガイド](docs/recovery-guide.md)を参照してください。

## MVP の価値

- 1 台のローカルまたは SSH ホストを read-only で診断する
- Balanced / Coding / Agent の用途別に、明示的なルールで推奨を生成する
- 現在値、推奨値、理由、影響、リスク、差分を承認前に提示する
- Backup → Apply → Validate を経て成功を確定し、失敗時は Rollback する
- Ollama と OpenCode の設定を対象とし、GUI 自体は root で動かさない

## 設計原則

診断、推奨生成、変更計画、実行を分離します。GUI はユースケースを呼び出すだけで、OS コマンドや SSH を直接扱いません。外部処理の結果は構造化し、将来の CLI や別 UI でも core を再利用できる構造にします。

## 文書

- [GitHub Release v0.1.0](https://github.com/NBE03xxx/LLM-Manager/releases/tag/v0.1.0)
- [v0.1.0 Release Notes](docs/release-notes-0.1.0-draft.md)
- [公開後再取得検証](docs/validation/phase6-public-release-verification-2026-09-19.md)
- [要件](docs/requirements.md)
- [MVP スコープ](docs/mvp-scope.md)
- [アーキテクチャ](docs/architecture.md)
- [データモデル](docs/data-model.md)
- [診断設計](docs/diagnostics.md)
- [最適化設計](docs/optimization.md)
- [安全な設定変更](docs/safe-apply.md)
- [Backup・Rollback・Recoveryガイド](docs/recovery-guide.md)
- [MVP Release Checklist](docs/release-checklist.md)
- [Third-party runtime dependencies](THIRD_PARTY_NOTICES.md)
- [deb packaging](docs/packaging.md)
- [GUI 設計](docs/gui.md)
- [ロードマップ](docs/roadmap.md)
- [Phase 0 技術調査](docs/phase-0.md)
- [Version matrix](docs/version-matrix.md)
- [Setting allowlist](docs/setting-allowlist.md)
- [Threat model](docs/threat-model.md)
- [Local read-only validation](docs/validation/local-readonly-2026-08-29.md)
- [Secret Service desktop validation](docs/validation/secret-service-desktop-2026-08-30.md)
- [PolicyKit desktop validation](docs/validation/policykit-desktop-2026-08-30.md)
- [SSH remote helper read-only validation](docs/validation/ssh-remote-helper-readonly-2026-08-30.md)
- [SSH remote helper positive validation](docs/validation/ssh-remote-helper-positive-2026-08-30.md)
- [Remote helper deb lifecycle validation](docs/validation/remote-helper-deb-lifecycle-2026-08-30.md)
- [Local deb and desktop positive validation](docs/validation/local-deb-desktop-positive-2026-08-31.md)
- [Debian 13 desktop packaging validation](docs/validation/debian13-desktop-packaging-2026-08-31.md)
- [Debian 13 PolicyKit/systemd validation](docs/validation/debian13-policykit-systemd-2026-08-31.md)
- [Phase 5 Qt runtime validation](docs/validation/phase5-qt-runtime-2026-09-01.md)
- [Phase 5 OpenSSH identity validation](docs/validation/phase5-openssh-identity-2026-09-02.md)
- [Phase 5 ControlMaster integration validation](docs/validation/phase5-controlmaster-integration-2026-09-02.md)
- [Phase 5 Recommendations runtime validation](docs/validation/phase5-recommendations-runtime-2026-09-02.md)
- [Phase 5 ChangeSet planning validation](docs/validation/phase5-change-planning-2026-09-02.md)
- [Phase 5 approval invalidation validation](docs/validation/phase5-approval-invalidation-2026-09-03.md)
- [Phase 5 Apply preparation validation](docs/validation/phase5-apply-preparation-2026-09-03.md)
- [Phase 5 sandbox Apply Results validation](docs/validation/phase5-sandbox-apply-results-2026-09-04.md)
- [Phase 5 production Apply connection audit](docs/validation/phase5-production-apply-audit-2026-09-04.md)
- [Phase 5 local restore production composition](docs/validation/phase5-local-restore-composition-2026-09-04.md)
- [Phase 5 Qt restore execution boundary](docs/validation/phase5-qt-restore-execution-2026-09-04.md)
- [Phase 5 Qt restore result evidence](docs/validation/phase5-qt-restore-results-2026-09-04.md)
- [Phase 5 local restore explicit refresh](docs/validation/phase5-local-restore-refresh-2026-09-04.md)
- [Phase 5 closure audit](docs/validation/phase5-closure-audit-2026-09-04.md)
- [SSH transfer disconnect validation](docs/validation/ssh-transfer-disconnect-2026-08-30.md)
- [SSH remote journal reconciliation validation](docs/validation/ssh-remote-journal-reconciliation-2026-08-30.md)
- [SSH development read-only validation](docs/validation/ssh-development-readonly-2026-08-29.md)
- [SSH AI server read-only validation](docs/validation/ssh-ai-server-readonly-2026-08-29.md)
- [ADR](docs/adr/README.md)

## 現在の実装とテスト

Phase 6までにLocal／OpenSSH診断、用途別推奨、差分review、exact approval、暗号化dual backup、Apply、runtime validation、自動rollback、切断後のimmutable result照合、手動restoreを実装しました。公開mutation routeはlocal user Apply、SSH user Apply、local user restore、local root restoreの4経路です。root GUI起動、mutation自動retry、秘密値のGUI／引数／標準入力受け渡しは行いません。

最終sourceとartifactでは全806 test（767成功・39 expected skip）、両deb verifier、security regression、OS／通常GUI Gateに成功しています。単体テストは次のコマンドで実行できます。PySide6がない環境ではQt runtime testがexpected skipになります。

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## 想定プロジェクト構成

```text
llm-manager/
├── pyproject.toml
├── src/llm_manager/
│   ├── ui/                 # PySide6（外側）
│   ├── application/        # ユースケース、ポート
│   ├── domain/             # モデル、ポリシー、状態遷移
│   ├── diagnostics/        # 診断オーケストレーション
│   ├── optimization/       # Rule Engine
│   ├── planning/           # Change Planner
│   ├── adapters/           # Local/SSH/Ollama/OpenCode/system
│   └── infrastructure/     # 実行、バックアップ、権限、永続化
├── rules/                  # 制約付き外部ルールデータ（MVP後の候補）
├── release/                # 公式配布物のdownload・検証とversion別保存先
├── tests/
└── docs/
```

設計の基準日: 2026-08-29

MVP のルール本体は `src/llm_manager/optimization/` に型付き Python 定義として置く。上記のトップレベル `rules/` は、schema と署名・配布方式を確立した後に利用する将来候補であり、MVP では作成しない。

## ライセンス

本プロジェクトは [MIT License](LICENSE) で公開します。
