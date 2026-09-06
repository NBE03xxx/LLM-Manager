# Phase 6 helper / root restore target lock — 2026-09-06

## 実装

既存`DeclaredHelperExecutor`には変更前hash照合から書込み・service操作までの対象排他がなかった。専用root restoreが使う固定drop-in親directoryのflockを`locked_root_target`へ共通化し、既存Apply helperの1要求全体にも適用した。ATOMIC_REPLACE、RESTORE_FILE、REMOVE_CREATED_FILE、daemon-reload、restartを同じロック区間で処理する。ロック取得後に要求期限も再確認する。

各取得で独立したopen file descriptionを作り、非blocking LOCK_EXで競合を拒否する。同じprocessの別backendも競合する。lock fileは作成・削除しない。`.llm-restore-*`が残る場合はApply側も停止し、その証拠を自動削除しない。失敗時にもFDを閉じて解放する。

production helperは固定`/etc/systemd/system`をroot owner・安全なmode・no-followで開き、初回Applyに必要な`ollama.service.d`だけをdir_fd相対で作成できる。親directoryのroot:rootと非group/world-writableを検査してからロックする。sandbox owner例外は既存の明示sandboxに限定する。

競合は最初のoperationを`helper_target_busy`、後続を`not_executed`として既存receiptへ保存する。同じoperation IDはロック解放後も再実行しない。root復元の既存`root_restore_target_busy`応答は保持した。

## 検証

新規10 testを一時directoryと実flockで実施した。

- root復元が保持中はApplyとrollbackの置換・削除をtarget readより前に拒否する。
- helperのbefore-hash read、書込み、reload、restartの全区間で逆方向のroot復元が競合する。
- 別Python processも同じinodeのロックへ競合し、解放後は取得できる。
- service失敗、stale target、取得後期限切れでは後続を停止しロックを解放する。
- 中断stagingは残したまま拒否する。unsafe directoryも拒否する。
- 初回Applyの親作成と、作成fileを消すrollbackが成功する。
- CLIは競合失敗receiptを保存し、解放後も同一要求のreplayを拒否する。

host全693 test: 664成功・29 skip。compileall、local/remote packaging shell syntax、desktop-file-validate、git diff --check成功。hostにPySide6 runtimeがないためQt関連skipを含む。今回OS/PolicyKit Gateとdeb rebuildは実施していない。

## 範囲と残件

ロックは既存helperの1要求と専用root restore coordinatorの実行区間を直列化する。非特権側のbackup採取、Apply後の外部validation、別helper要求として実行するrollbackまでを一つのtransactionとして保護するものではない。root origin captureのApply接続・同一lock区間、旧版helperとの混在、外部管理者による操作や親directory差替えへの協調は未完了。全mutator統合の完了とは扱わない。

専用root復元実行認可/CLI、明示provisioning、実PolicyKit/installed deb、両OS/実display Gateを継続する。root mutation routeは公開しない。保存済みdeb/SBOMは本変更後のartifact証拠ではない。

開始時に既存の未コミットdiffを確認し、保持した。VMはread-only確認でUbuntu/Debianともshut off。host SSH configはnobody:nogroup 0777のままでproduction SSH Gateを保留。実設定・service・SSH設定・package・VM状態は変更していない。全変更は未コミット。現在・次ともPhase 6。
