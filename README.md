# LLM-Manager

LLM-Manager は、ローカル Linux PC または既存の OpenSSH 接続先について、ハードウェア、OS、Ollama、OpenCode を診断し、用途別の最適化案を安全にレビュー・適用するデスクトップ GUI アプリケーションです。

Phase 0〜3を完了し、現在は **Phase 4（Safe Apply Core）を実装中**です。local sandbox向けBackup Store、AES-GCM暗号化、Secret Service鍵provider、user-level atomic apply、実行後Validator、journal/audit、rollback Coordinator、限定特権helper core、root変更専用Safe Apply workflow、local/remote helperの分離deb sandbox build/artifact Gate、外部端末SSH対話認証、remote recovery copyの限定transport Port・user staging・sandbox retentionまで実装済みです。PySide6 GUI、deb実install/desktop integration Gate、実SSH remote helper接続はまだ実装していません。

MVP の正式対象は Ubuntu 26.04 と Debian 13 で、Python 3.14.4、Ollama 0.33.2、OpenCode 1.18.25 を初期検証基準とする。製品の周辺バージョンは互換性確認後に対応範囲へ追加する。開発中はソース起動を許容し、一般ユーザー向けリリースでは deb パッケージを提供する。

UIはユーザーlocaleを初期値として日本語・英語を提供し、未対応localeは英語へフォールバックする。

## MVP の価値

- 1 台のローカルまたは SSH ホストを read-only で診断する
- Balanced / Coding / Agent の用途別に、明示的なルールで推奨を生成する
- 現在値、推奨値、理由、影響、リスク、差分を承認前に提示する
- Backup → Apply → Validate を経て成功を確定し、失敗時は Rollback する
- Ollama と OpenCode の設定を対象とし、GUI 自体は root で動かさない

## 設計原則

診断、推奨生成、変更計画、実行を分離します。GUI はユースケースを呼び出すだけで、OS コマンドや SSH を直接扱いません。外部処理の結果は構造化し、将来の CLI や別 UI でも core を再利用できる構造にします。

## 文書

- [要件](docs/requirements.md)
- [MVP スコープ](docs/mvp-scope.md)
- [アーキテクチャ](docs/architecture.md)
- [データモデル](docs/data-model.md)
- [診断設計](docs/diagnostics.md)
- [最適化設計](docs/optimization.md)
- [安全な設定変更](docs/safe-apply.md)
- [deb packaging](docs/packaging.md)
- [GUI 設計](docs/gui.md)
- [ロードマップ](docs/roadmap.md)
- [Phase 0 技術調査](docs/phase-0.md)
- [Version matrix](docs/version-matrix.md)
- [Setting allowlist](docs/setting-allowlist.md)
- [Threat model](docs/threat-model.md)
- [Local read-only validation](docs/validation/local-readonly-2026-08-29.md)
- [SSH development read-only validation](docs/validation/ssh-development-readonly-2026-08-29.md)
- [SSH AI server read-only validation](docs/validation/ssh-ai-server-readonly-2026-08-29.md)
- [ADR](docs/adr/README.md)

## 現在の実装とテスト

Phase 1〜3の基盤に加え、Phase 4ではsandbox限定のLocalBackupStore、複数source-spanを束ねるAtomicFileExecutor、stale hash/path/symlink検査、FileValidator、承認に束縛されたSafeApplyCoordinator、root変更専用のBackup→helper Apply→runtime Validate→helper Rollback、逆順rollbackと故障注入テストを実装しています。単体テストは次のコマンドで実行できます。

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
├── tests/
└── docs/
```

設計の基準日: 2026-08-29

MVP のルール本体は `src/llm_manager/optimization/` に型付き Python 定義として置く。上記のトップレベル `rules/` は、schema と署名・配布方式を確立した後に利用する将来候補であり、MVP では作成しない。

## ライセンス

本プロジェクトは [MIT License](LICENSE) で公開します。
