# Phase 6 fixed root restore composition — 2026-09-06

## 実装

`StoredRootRestorePreflight`を追加。strict storeのreview/attempt読取り、固定target観測、origin/AEAD verifierを既存preflightへ接続する。test内だけにあったport接続を製品moduleへ移した。

`production_execution()`はrootであることをI/O前に確認し、固定backup/key/source/execution/audit openerを使ってcoordinatorを組み立てる。owner/path/runnerの呼出側overrideは受け付けない。鍵・directoryを作成しない。auditの既存chainを検査してからcoordinatorを返す。各FDは取得直後にExitStackへ登録し、初期化途中失敗・本体例外・正常終了の全経路で閉じる。

同じstore/target/verifierをpreflightとexecutionに渡し、固定service adapterと専用strict auditを使用する。組立だけでは復元やservice操作をしない。context外へcoordinatorを持ち出して使用しない。

これは認可処理ではない。root UIDや保存reviewを専用実行PolicyKit認証の代わりにせず、既存Apply/review CLIから接続しない。専用実行CLIはまだ公開していない。

## 検証

新規6 test。非root時のI/O前拒否、全5 opener各位置での失敗と取得済FDの逆順解放、同一component共有、組立時にaudit append/service操作をしないこと、audit拒否/本体例外での全FD解放を確認した。

実一時store/target/key/AEAD/auditを用いた新port統合では、復元完了・開始終了audit・replay拒否、鍵喪失時の無変更・auditなし・service未呼出しを確認した。固定production openerの構成testはmock FDを用い、実root pathや実serviceは操作していない。

host全728 test: 697成功・31 skip。compileall、local/remote shell syntax、desktop-file-validate、git diff --check成功。実PolicyKit/installed deb/VM Gateは今回未実施。

## 残件

専用実行認可/CLI、要求をまたぐ排他、明示provisioning、実PolicyKit/installed deb/両OS Gateを継続する。root mutation routeは非公開。production compositionがあることをrelease可能の根拠にしない。実環境変更なし、既存変更を保持し全変更未コミット。現在・次ともPhase 6。
