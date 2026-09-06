# Phase 6 strict root restore audit — 2026-09-06

## 実装

専用`RootRestoreAuditLog`を追加。固定`/var/lib/llm-manager/local-root-restore/audit`の既存root-owned directoryをno-followで開くproduction openerと、借用dir_fdで動くadapterを用意した。directory/keyは自動作成しない。production実行CLIには未接続。

既存AuditEvent形式を用い、sequence、previous hash、event hash、canonical内容、HEADとの一致を検証する。開始/終了のevent typeとrequest hash/state/error codeだけを許可し、未知field・重複field・設定本文を拒否する。同一requestの開始/終了重複、開始なしの終了、要求hash不一致、時刻逆行を拒否する。

root readerのowner/group/mode・regular file・no-follow・hardlink検査を使用。全read/appendを独立open descriptionのshared/exclusive nonblocking flockで排他する。最大10000 event、各16 KiB、HEAD 128 byte。immutable eventを排他公開/fsyncしてからHEADを更新/fsyncする。途中失敗はpendingやHEAD不一致として停止し、証拠の自動cleanup・上書きrepairをしない。既存eventは置換せず、HEADだけをatomic replaceする。

## 検証

新規9 test。実一時directoryでhash chain往復、metadata、重複/未知field/開始なし終了、tail削除、mode/symlink/hardlink、fsync失敗のpending保持、event公開後HEAD保存前の失敗、reader/writer競合を確認した。

実一時targetの復元coordinatorへ接続し、正常復元の開始/終了監査保存を確認。不安全audit directoryでは実targetを書き換えずserviceも呼ばずFAILEDになる。実Ollama serviceはfixture。

host全722 test: 691成功・31 skip。compileall、local/remote shell syntax、desktop-file-validate、git diff --check成功。実PolicyKit・installed deb・OS Gateは今回未実施。

## 境界と残件

hash chainはroot権限者が全storeを置換できない保証ではない。全履歴とHEADを削除された空directoryを初期未使用と区別する外部anchorも未導入。これはroot-owned evidenceに対する破損・部分欠落検出であり、外部の改ざん防止証明ではない。

固定openerとaudit adapterは完成したが、専用実行認可/CLIのproduction compositionは未完了。要求間排他、明示provisioning、実PolicyKit/installed deb/両OS Gateを継続する。root mutation route非公開。source/VM/実設定/service/SSH/packageの実環境変更なし。既存未コミット変更は保持。現在・次ともPhase 6。
