# MVP スコープ

## 1. スコープ基準

MVP は「単一 Linux ホストの Ollama/OpenCode 環境を、安全に診断・提案・変更・検証・復元できる最小の縦切り」とする。対応項目が存在しない場合も、曖昧な空値ではなく明示的状態を返す。

## 2. In Scope

| 領域 | MVP |
|---|---|
| Host | Local 1 台または OpenSSH alias の SSH 先 1 台 |
| OS | Ubuntu 26.04、Debian 13。distribution、kernel、architecture、diskを診断 |
| Hardware | CPU/cores、RAM、swap、GPU vendor/name/count、取得可能な VRAM/driver/compute stack |
| Ollama | installed/version/service/environment/API/models/loaded runtime の診断 |
| OpenCode | installed/version/config/provider/model/base URL/context/timeout の診断 |
| Optimization | Balanced/Coding/Agent、明示 Rule Engine、説明可能な Recommendation |
| Planning | 設定 schema に基づく ChangeSet、diff、競合、root/restart/risk |
| Safety | approval、backup、precondition、apply、validate、automatic/manual rollback、audit |
| Privileged changes | systemd drop-inを含むroot必須変更、PolicyKitまたはSSH sudo |
| Helper prerequisite | Localは本体deb同梱、SSH先はremote helper debの事前導入が必要 |
| GUI | 6 工程、非同期実行、進捗、キャンセル、部分失敗 |
| Testing | domain/rule/parser/adapter contract/workflow/fault injection |
| Distribution | 開発中はソース起動、一般ユーザー向けリリースはdeb |
| Language | ユーザーlocaleに基づく日本語・英語、設定による切替、英語fallback |

設定変更の正確なキーは、対応する Ollama/OpenCode version matrix と公式 schema を実装前に確定した範囲に限定する。未知版は診断のみまたは警告付き read-only とする。

## 3. Best-effort / Optional in MVP

- physical CPU cores
- GPU utilization、temperature
- vendor tool が提供する VRAM used
- Ollama の runtime CPU/GPU offload 内訳と memory usage
- SELinux context の保存（対応環境で可能な場合）

取得できないことを failure とせず、`unsupported/unavailable` と理由を返す。ただし推奨ルールは欠損データを考慮して confidence を下げる。

## 4. Out of Scope

- Ollama 自動インストール
- GPU driver、ROCm、CUDA のインストール・更新
- model download/delete
- GUIによるSSH先helperの自動インストール・更新
- SSH key/password/agent の管理・保存
- 複数ホストへの一括診断・設定
- 自動 benchmark、負荷試験
- LLM/AI による設定値決定
- Codex、Claude Code、OpenClaw の設定変更
- llama.cpp、vLLM、他 runtime
- Windows/macOS の正式対応
- Web UI、multi-user server、remote daemon

対象外機能を検出・案内することはできるが、実行ボタンは提供しない。

## 5. MVP 完了の Definition of Done

1. requirements の受け入れ条件を自動または手動 test case に対応付ける。
2. 代表 Local fixture と SSH fake transport で end-to-end workflow が通る。
3. 対応版の実 Linux/Ollama/OpenCode test matrix で read-only 診断を確認する。
4. sandbox fixture に対し Apply 成功、validation failure、rollback failure を検証する。
5. secret redaction と privilege boundary の security review を完了する。
6. GUI が長時間操作で freeze せず、取消と終端状態が明確である。
7. 利用者向け backup/rollback 手順と既知制限を文書化する。
8. 対応version matrix外では自動Changeが生成されず、read-onlyへ縮退する。
9. 設定allowlist外のpath/keyをChange Plannerと特権helperの双方が拒否する。
10. 要件・受け入れ条件・test caseのトレーサビリティに欠落がない。

## 6. スコープ変更規則

新機能は「安全な縦切りの完成に必須か」で判断する。対象 runtime/client/host 数を増やす変更は原則 post-MVP とし、まず Adapter 契約と fixture で拡張可能性を検証する。

## 7. 実装前 Gate

- Ubuntu 26.04/Debian 13におけるsystemd user/system serviceの範囲
- PySide6 6.8.6 wheel/import/pluginと、基準版以外のPython/Ollama/OpenCode version matrix
- 自動変更を許可する具体的 setting allowlist
- Local/remote helper deb、protocol互換性、対話端末のsandbox検証
- AES-256-GCM envelope、local Secret Service鍵、remote root鍵、復旧手順のsandbox検証
- validation の必須 check と timeout

これらが未確定の場合、該当機能は read-only に縮退させる。

## 8. 対応version方針

- 正式対象OSはUbuntu 26.04とDebian 13とする。それ以外のUbuntu/Debianリリースは検出できても正式対応と表示しない。
- Python 3.14.4、Ollama 0.33.2、OpenCode 1.18.25を最初の検証基準版とする。
- PySide6最低版は公式にPython 3.14対応が明記された6.8.6とする。配布時はPython 3.14.4とのwheel/import/plugin検証済みversionへpinする。
- Ollama/OpenCodeは「診断対応」と「自動変更対応」を別に宣言する。
- 自動変更対応は、設定schema、優先順位、runtime検証、rollback fixtureが確認済みのversion rangeに限定する。
- 未知major versionはread-only、未知minor/patchはfixture互換性を確認できるまでactionable recommendationを抑止する。
- systemd user unitとsystem unitは別環境としてtest matrixに載せる。
- version rangeの拡張にはparser、planner、validation、rollbackのfixtureを必要とする。

上記基準版を最初のfixture/E2E対象とする。Ollama/OpenCodeの周辺バージョンは、parser、planner、validation、rollbackの互換性fixtureと契約テストを通過後にmatrixへ追加する。単なるversion文字列の近さでは対応扱いにしない。

## 9. Backup保持・暗号化

- local正本とSSH先復旧用copyの双方に同じretention metadataを持たせる。
- 既定保持は30日かつhostごとに直近10世代とする。30日超過または10世代超過した未保護backupを古い順に削除候補とするが、最低1件の復元可能なbackupは残す。
- ユーザーが手動保護したbackupは期限・世代数による自動削除対象外とする。
- 暗号化はMVPではユーザー選択とする。無効時はReview/Backup画面で平文保存riskと保存先を明示する。
- 一般配布buildは暗号化ON、明示的な開発モードはOFFを初期値とする。初期値はユーザー設定で変更できる。
- 暗号化の有無にかかわらず、権限制限、integrity hash、secret非表示、確実な削除結果の記録を必須とする。

## 10. Locale対象

- `ja`と`en`をMVPサポートlocaleとする。地域variantは同じ言語catalogへ解決する。
- 初回起動はOS/Qt locale、以後はユーザーの明示設定を優先する。
- 未対応localeおよび翻訳欠落は英語へfallbackする。
- 画面、進捗、エラー、推奨理由、Review、権限要求、Backup/Rollback、復旧手順を翻訳対象とする。
- command、path、設定キー、model名、ログ識別子、domain enumは翻訳しない。
