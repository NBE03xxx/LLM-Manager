# MVP 要件定義

## 1. プロジェクト概要

LLM-Manager は、Linux 上のローカルホストまたは OpenSSH 接続先 1 台を対象に、LLM 実行環境を診断し、用途に適した Ollama/OpenCode 設定を提案し、安全なトランザクションとして適用する GUI アプリケーションである。

## 2. 目的と成功基準

利用者が散在するシステム情報と設定を手作業で突き合わせずに、次を一連の操作として完了できることを目的とする。

1. 対象を選び、read-only 診断を実行する。
2. Balanced / Coding / Agent の用途を選ぶ。
3. 再現可能なルールによる推奨と根拠を確認する。
4. 変更差分、影響、権限、再起動、リスクを承認する。
5. バックアップ付きで変更し、検証結果またはロールバック結果を確認する。

MVP の成功は「対象環境を勝手に変更しない」「同じ入力とルール版から同じ推奨が得られる」「失敗を検出し復旧経路を提示できる」ことで評価する。

## 3. 想定ユーザー

- ローカル LLM を使う Linux 開発者
- Ollama と OpenCode の調整を行いたいが、設定箇所や安全な変更手順を一元化したい利用者
- SSH 設定、公開鍵認証、必要に応じた sudo を既に利用できる管理者・上級利用者

## 4. 機能要件

識別子は実装・テスト・レビューで維持する。

| ID | 要件 |
|---|---|
| FR-HOST-01 | Local または `~/.ssh/config` のホストを 1 台選択できる |
| FR-DIAG-01 | system、hardware、Ollama、OpenCode を read-only 診断できる |
| FR-DIAG-02 | 個別項目の成功・未対応・不足権限・不在・失敗を区別できる |
| FR-DIAG-03 | 設定上の期待値と観測可能な実行時値の不一致を報告できる |
| FR-OLLAMA-01 | 導入、版、サービス、環境、API、モデル、ロード状態を確認できる |
| FR-OPENCODE-01 | 導入、版、設定場所、provider/model/base URL/context/timeout/接続設定を確認できる |
| FR-PROFILE-01 | Balanced / Coding / Agent のいずれかを選択できる |
| FR-REC-01 | 診断結果、用途、ルール版から推奨を決定論的に生成できる |
| FR-REC-02 | 推奨ごとに現在値、推奨値、理由、severity、confidence、impact、risk、再起動/root 要否を表示できる |
| FR-PLAN-01 | 選択した推奨から検証可能な ChangeSet と統合 diff を生成できる |
| FR-PLAN-02 | 競合、古い診断結果、書込不能、未対応な変更を適用前に拒否できる |
| FR-APPROVE-01 | 明示的承認がない限り変更しない |
| FR-BACKUP-01 | 変更前に対象、メタデータ、内容、ハッシュをバックアップする |
| FR-APPLY-01 | 承認済み計画だけを適用し、必要な場合だけサービスを再起動する |
| FR-VALIDATE-01 | ファイル内容、サービス状態、Ollama API、OpenCode 接続設定を段階的に検証する |
| FR-ROLLBACK-01 | Apply/Validate 失敗時にバックアップから復元し、復元後検証を行う |
| FR-AUDIT-01 | 診断、計画、承認、実行、検証、復元の結果を秘密情報を除外して記録する |
| FR-I18N-01 | ユーザーlocaleから日本語または英語を初期選択し、設定から変更できる |
| FR-I18N-02 | 未対応localeでは英語へフォールバックし、診断・安全操作を継続できる |

## 5. 非機能要件

- **対応環境:** Ubuntu 26.04とDebian 13をMVP正式対象とする。Python 3.14.4、PySide6 6.8.6以上、Ollama 0.33.2、OpenCode 1.18.25を初期検証基準とし、application/runtimeのsupported minimumはDebian 13 stockに合わせPython 3.13、cryptography 43.0.0、SecretStorage 3.3.3とする。配布時のPySide6は検証済みversionへpinする。周辺バージョンは互換性fixtureと契約テストを通過後にversion matrixへ追加する。
- **応答性:** 外部コマンド、SSH、HTTP、ファイル I/O は UI スレッドで行わない。進捗表示とキャンセル要求を提供する。
- **テスト可能性:** domain/application は PySide6、subprocess、ネットワークに依存しない。Adapter は契約テスト、ルールは表駆動テストを持つ。
- **決定性:** 推奨と計画は入力スナップショットおよびルール版を記録し、再生成可能にする。
- **可観測性:** コマンド種別、終了状態、所要時間、stderr の安全な要約を記録する。秘密値はマスクする。
- **耐障害性:** 各操作に timeout を持たせ、部分的な診断失敗でも取得済み結果を表示する。
- **互換性:** ベンダー固有コマンドの不在を正常な能力不足として扱う。
- **保守性:** core は UI・OS・転送方式から独立し、Adapter を追加可能にする。
- **国際化:** UI、エラー、推奨理由、安全警告は翻訳キーと変数から生成し、日本語・英語で情報量とseverityを一致させる。domain enum、設定キー、監査IDはlocale非依存とする。

## 6. 安全要件

1. 診断は原則 read-only とし、診断中の昇格を要求しない。
2. 診断、推奨生成、変更計画、変更実行を別ユースケースにする。
3. Plan の内容ハッシュと診断スナップショットを承認に結び付け、承認後の差し替えを防ぐ。
4. Apply 直前に対象の現在ハッシュを再確認し、外部変更があれば中止して再計画する。
5. バックアップ成功を Apply の事前条件とする。
6. 原子的置換が可能なファイルは一時ファイル、fsync、rename を使う。権限・所有者・SELinux context は可能な範囲で保存する。
7. 検証失敗時は自動ロールバックを既定とし、復元失敗は重大状態として明示する。
8. コマンド引数は配列で構築し、shell 展開を既定で使わない。許可されたコマンドと操作だけを Adapter が発行する。
9. API token、SSH 関連情報、設定内の秘密値をログ・diff・バックアップ一覧でマスクする。
10. Backup暗号化はユーザー選択とする。無効時は平文保存のriskをBackup前に表示し、localは所有者のみ、remoteは対象に応じてuser-only/root-only権限を強制する。
11. Backupは既定で30日かつhostごとに直近10世代を保持し、いずれかの上限を超えた未保護backupを削除候補とする。手動保護されたbackupは自動削除しない。
12. 一般配布buildではBackup暗号化を既定ON、明示された開発モードでは既定OFFとする。どちらもユーザーが変更でき、OFF時は平文riskの確認を必須とする。

## 7. SSH 要件

- system `ssh` を subprocess として利用し、`~/.ssh/config`、SSH Agent、ProxyJump、known_hosts、公開鍵認証を委譲する。
- MVP は非対話認証を基本とし、秘密鍵・パスフレーズ・SSH パスワードを保存しない。
- 接続先指定は OpenSSH のホスト alias を優先し、任意引数をコマンド文字列に連結しない。
- 接続確認、コマンド実行、ファイル読取・安全な転送を Host Adapter の契約に隠蔽する。
- timeout、host key エラー、認証失敗、sudo 不可を区別して報告する。
- SSH 先への接続自体はユーザーが明示的に診断または変更を開始したときだけ行う。

## 8. 権限管理

- GUI と core は一般ユーザーで実行する。
- ローカルの特権変更は、debでroot-owned固定pathへ導入した限定helperをPolicyKit/pkexecで都度起動する。
- SSH 先は既存の `sudo` ポリシーを利用し、passwordless sudoと対話sudoの双方に対応する。対話認証は外部端末上の`ssh -t`とremote sudo/helperへ委譲し、GUIプロセスはパスワードを入力・読取・保存しない。
- 対話sudoでは、承認済みrequestをremoteへstageした後、端末内で限定helperをsudo実行する。GUIはoperation IDに対応するjournal/resultをread-onlyで監視する。sudo timestampが別SSH sessionでも共有されることは前提にしない。
- SSH先の限定helperは別debとして管理者が事前導入する。未導入、protocol非互換、所有者・mode不正の場合は診断と推奨だけを許可し、root Changeを生成しない。GUIからhelperを自動導入・更新しない。
- 特権 helper は宣言された ChangeSet、対象パス、ハッシュ、許可操作を検証し、任意コマンド実行器にしない。

## 9. MVP 対象範囲

- 単一ホスト、Linux、Local/SSH
- system/hardware の基礎診断
- Ollama/OpenCode の診断、推奨、設定変更、検証、復元
- 3 用途プロファイル
- 明示的 Rule Engine
- GUI によるワークフローとローカル監査ログ
- systemd drop-inを含むroot権限変更
- 開発中のソース起動と、一般ユーザー向けリリース時のdebパッケージ

詳細な境界は [mvp-scope.md](mvp-scope.md) を参照する。

## 10. MVP 対象外

Ollama、GPU driver、ROCm、CUDA のインストール、model download、SSH 鍵管理、複数ホスト一括処理、自動 benchmark、LLM による設定判断、Codex/Claude Code/OpenClaw の変更、llama.cpp、vLLM は対象外とする。

## 11. 受け入れ条件

- AC-01: Local と OpenSSH alias の双方を同一ユースケースで診断でき、診断が設定を変更しない。
- AC-02: 必須診断項目に値または明示的な状態・理由がある。
- AC-03: 固定 fixture に対し、同一ルール版の推奨結果が常に一致する。
- AC-04: Coding と Agent が異なる目的・制約で推奨を生成する。
- AC-05: Review 画面に全変更、diff、影響、risk、restart/root 要否が表示される。
- AC-06: 承認なし、バックアップ失敗、計画後の外部変更のいずれでも Apply されない。
- AC-07: 成功時は Validate を通過した結果だけが Commit 状態になる。
- AC-08: 故障注入テストで Apply/Validate 失敗後に復元され、復元後検証結果が残る。
- AC-09: 長時間処理中も Qt event loop のsentinel event、進捗、cancel signalが処理され、外部I/OがUI thread上で実行されない。
- AC-10: GUI/core/adapter の依存方向を自動テストまたは静的検査で確認できる。
- AC-11: ログと表示に既知の秘密値が露出しない。
- AC-12: GUI を root で起動せずに通常診断を完了できる。
- AC-13: 対応version matrix外またはallowlist外の設定から自動Changeが生成されない。
- AC-14: 未完了Applyを検出した場合、再適用前にjournal、host identity、before/after hashから状態照合する。
- AC-15: 日本語・英語の両localeで全MVP画面、安全警告、主要エラーを表示でき、未対応localeでは英語で起動する。

## 12. 設計判断・残存検証事項

採用: Ubuntu 26.04/Debian 13、初期基準 Python 3.14.4 / Ollama 0.33.2 / OpenCode 1.18.25、互換確認後の周辺版追加、OpenSSH CLI、外部端末対話sudo、systemd drop-inを含むroot変更、local+remote二重backup、一般配布は暗号化ON・開発モードはOFF、30日かつ10世代保持、port-and-adapter、Python定義ルール、QThreadPool、日本語/英語、最終deb配布。代替案と移行条件は各設計文書に記載する。

設計方式はPhase 0 ADRで確定した。実装時にPySide6 wheel、helper deb/protocol、対応端末、AES-256-GCM envelope、Secret Service、OpenCode source-span patchをsandboxで検証し、Gate未通過機能はread-onlyとする。

## 13. 要件トレーサビリティ

| 要件群 | 主設計文書 | 主要受け入れ条件 | 予定テスト種別 |
|---|---|---|---|
| FR-HOST / FR-DIAG | `diagnostics.md`, `architecture.md` | AC-01, AC-02, AC-12 | parser、HostPort契約、Local/SSH E2E |
| FR-OLLAMA / FR-OPENCODE | `diagnostics.md`, `mvp-scope.md` | AC-02, AC-13 | version matrix、API/config fixture |
| FR-PROFILE / FR-REC | `optimization.md` | AC-03, AC-04, AC-13 | table-driven、golden、境界/property |
| FR-PLAN / FR-APPROVE | `safe-apply.md`, `data-model.md` | AC-05, AC-06, AC-13 | planner conflict、approval invalidation |
| FR-BACKUP / FR-APPLY | `safe-apply.md` | AC-06, AC-07, AC-14 | integrity、allowlist、fault injection |
| FR-VALIDATE / FR-ROLLBACK | `safe-apply.md` | AC-07, AC-08, AC-14 | service/API validation、recovery state |
| FR-AUDIT | `safe-apply.md` | AC-11, AC-14 | redaction、journal recovery |
| GUI/non-functional | `gui.md`, `architecture.md` | AC-09, AC-10 | Qt event-loop、architecture test |
| FR-I18N | `gui.md`, `architecture.md` | AC-15 | locale切替、fallback、翻訳完全性、layout test |

実装時は各test caseに少なくとも1つのFR/AC IDを付与する。ACを満たすtestが存在しない状態ではMVP完了としない。
