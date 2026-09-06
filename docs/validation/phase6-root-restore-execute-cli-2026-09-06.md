# Phase 6 dedicated root restore execution CLI — 2026-09-06

## 実装

専用privileged entry `llm-manager-restore-execute`を追加した。引数は
`request-sha256 canonical-request-hex`だけで、requestはhex化前16 KiB以下、
lowercase canonical encoding、専用protocol、独立して解決したcaller UID/host、
hash、期限をproduction compositionを開く前に検証する。任意path、unit、backup
payload、設定本文、status/retry subcommandは受け付けない。

実行には独立PolicyKit action
`io.github.nbe03xxx.llm-manager.execute-system-restore`を追加した。
active sessionの`auth_admin`を毎回要求し、`auth_admin_keep`は使わない。既存Apply
actionとreview actionの認証は実行権限として流用しない。GUI全体はrootで起動しない。

CLIは固定production compositionへexact requestと独立identityを渡す。保存済み
terminal resultのrequest ID/hash、attempt hash、timezone付き時刻、state/error codeを
再検査してcanonical JSONを返す。`committed`だけでなく`failed`と`unknown`も、終端
resultの永続化に成功した場合はtransport exit 0とし、利用側がstateを必ず確認する。
後二者は`requires_attention=true`となる。

result永続化が確認できない場合は`execution_unconfirmed`とrequest ID/hash、最後に
観測したstateだけを返してexit 1にする。mutation済みの可能性があるため`failed`や
未実行とは表現せず、自動retryしない。read-only statusでexact requestを再照合する。
その他の例外もtraceback、例外文、設定内容、service出力を返さない。

isolated `/usr/bin/python3 -I` launcher、manpage、deb install list、artifact verifierを
追加した。manpageにはexit 0が復元成功を意味しないこと、unconfirmed時は再実行せず
statusを使うこと、store/key/audit/target parentのprovisioningは行わないことを記載した。

## 検証

新規8 testを追加した。

- exact requestを一度だけcoordinatorへ渡し、committed resultを返す。
- failed/unknownの保存済みresultをattention付きで返す。
- result永続化失敗をunconfirmedとして一度だけ返す。
- 不正hex、oversize、hash/UID不一致、期限切れをcomposition I/O前に拒否する。
- coordinator由来に見える不一致ID/hash、invalid attempt hash/state/error/timeを成功扱いしない。
- unexpected exceptionを伏字化し、status等の別subcommandを持たない。
- PolicyKit action、launcher mode/import、deb/manpage収録が専用entryへ固定される。
- 実一時store/backup/key/target/audit/service fixtureを使うcoordinatorで一度復元し、同じ
  requestの二回目を拒否してtargetを再変更しない。

host全736 test: 705成功・31 skip。compileall、local/remote packaging shell syntax、
desktop-file-validate、git diff --check成功。

workspace外の一時copyで`dpkg-buildpackage -us -uc -b`と
`packaging/verify-deb.sh`に成功した。開発artifact:

- package: `llm-manager 0.1.0~dev0` / `UNRELEASED`
- SHA-256: `5b8606b11299932e102c0c3b9e3c23fe88d0e2710c428cb4f9ed19d4ee9515db`
- execute/review launcher: root/root 0755
- execute/review manpage: root/root 0644（deb内ではgzip圧縮）

## 境界と残件

専用実行CLIとPolicyKit定義は実装したが、通常GUIからは呼ばずroot mutation routeは
非公開を維持する。実PolicyKit認証、installed deb、root store/key/auditの明示
provisioning、実service/OS Gate、非特権execution clientと最終同意GUIは未完了。
要求をまたぐApply/backup/rollback排他も残る。保存済みreviewだけで実行可能になったとは
扱わない。

実Ollama/OpenCode設定、service、SSH、package、VM状態は変更していない。既存の
未コミット変更を保持し、全変更は未コミット。現在・次ともPhase 6。
