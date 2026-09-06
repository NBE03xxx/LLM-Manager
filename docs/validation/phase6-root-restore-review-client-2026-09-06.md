# Phase 6 root restore review client — 2026-09-06

非特権側の `RootRestoreReviewClient` を追加した。production GUIにはまだ接続していない。

## 呼出し境界

固定 `/usr/bin/pkexec /usr/bin/llm-manager-restore-review` のpreview/approveだけを呼び出す。既存Apply helper/actionやuser-owned stagingを使用しない。metadata-only canonical requestをlowercase hexで渡す。production runnerは120秒timeoutとstream別32 KiB上限を使用する。cancel/timeout/認証拒否/異常終了/不正応答から成功を推測せず、retryもしない。approveの応答が失われた場合はreviewだけが保存済みの可能性があり、再送してはならない。

preview応答はcanonical JSON、正確なfield集合、選択backup ID、caller UID/host、固定target、file metadata、期限、preview hashを検証する。origin/source hash形式も検査する。これはroot側のorigin/AEAD照合や認可の代替ではない。approveは同じselectionからrequestを作り、receiptのrequest ID/hashが一致したときだけSavedRootRestoreReviewを返す。receiptは復元完了・復元実行認可・GUI同意取得の証明ではない。呼出し元で正確なselectionを表示し、明示同意を取得する接続は次の作業。

helper由来のerror_codeやstderr本文を画面用errorへ転送せず、固定codeへ分類する。新しい設定変更コマンド、root directory/key provisioning、自動restoreは追加していない。

## 検証

新規9 test。専用argvとrequest束縛、不一致receipt、非canonical/巨大/深い/不正JSON、再hashした別identity/target/期限、I/O前の不正入力/期限/cancel、認証拒否/timeoutの単発処理、終了直後cancelを検証した。

実CLI mainと実一時backup/key/storeを結合してpreview→approve→保存review一致、対象file未変更、実行attempt未使用を確認した。runnerとprivileged compositionは注入しており、実pkexec/PolicyKitの検証ではない。

- 全670 test: 647成功、23 skip（主にhostのPySide6 runtime不在）。
- compileall、local/remote packaging shell syntax、desktop-file-validate、git diff --check成功。
- 実設定・service・VM・SSH変更なし。既存変更を含め全変更未コミット。

次もPhase 6。GUI consent/production composition、実PolicyKit認証、専用実行認可/CLI、全mutatorの同一target lock、provisioning、対応OS/Qt Gateが残る。root mutation routeは引き続き非公開。以前の保存deb/SBOMは今回変更のartifact証拠ではない。
