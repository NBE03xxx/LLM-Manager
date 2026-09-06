# Phase 6 root restore execution client — 2026-09-06

## 実装

通常ユーザーから専用execute entryを一度だけ呼ぶ`RootRestoreExecuteClient`を追加した。
exact `LocalRootRestoreRequest`を現在時刻、caller UID、host、request hashでI/O前に検証し、
canonical requestをlowercase hex化して固定
`/usr/bin/pkexec /usr/bin/llm-manager-restore-execute`へ渡す。timeoutは180秒、stdoutと
stderrはstream別32 KiB上限、実行可能fileはpkexecだけを許可する。任意command、path、
unit、設定本文は受け付けない。

exit 0ではcanonical JSONの全field、request ID/hash、strict boolean、resultのID/hash、
attempt hash、timezone付き時刻、state/error code、summary state/attentionを再検査して
`RootRestoreResult`を返す。`committed`以外の保存済み`failed`/`unknown`もresultとして返すが、
attentionを必須とする。

プロセス起動後に正常なterminal resultを確認できない場合の専用
`RootRestoreExecutionUnconfirmed`を追加した。timeout、late cancel、runner I/O/output-limit
障害、未知exit、oversize/malformed/noncanonical/矛盾応答、CLI exit 1はすべてこの状態に
統一する。request ID/hashと、正しくbindingされた`execution_unconfirmed`応答の場合だけ
reported stateを保持する。helper側error文字列は表示しない。自動retryはせず、既存の
read-only status clientでexact requestを照合する。

実行前と確定できるcancelはprocessを起動しない。pkexecの126（認証拒否）と127
（launcher不在）だけは既知の実行前結果として通常のAdapterErrorにする。runnerが例外を
返した場合は、custom runnerやPopen後の失敗を未起動と推測せずunconfirmedにする。

## 検証

新規9 test。固定argv/timeout/canonical request、committed/failed/unknown result、result
binding/schema/state/time/summary偽装、bound/forged unconfirmed、canonical failed応答、timeout、
cancel、runner障害、oversize/noncanonical、認証拒否/launcher不在、期限/identity/pre-cancelを
検証した。全ケースでexecute transportは最大一回。

client→実execute CLI→実一時coordinator/store/backup/key/target/audit/service fixtureの往復で
一度だけ復元し、二回目はunconfirmed/status照合必須となってtargetを再変更しないことを
確認した。実service commandとPolicyKit認証はfixture。

host全745 test: 714成功・31 skip。compileall、local/remote packaging shell syntax、
desktop-file-validate、git diff --check成功。

## 境界と残件

clientは通常GUIへ未接続。最終復元同意session/dialog、実行後status照合UI、実PolicyKit、
installed deb、provisioning、実service/OS Gate、要求をまたぐ排他は未完了。root mutation
routeは非公開を維持する。

前sliceでbuildしたdev debは本client追加前のため、この変更のartifact証拠ではない。
実設定、service、SSH、package、VM状態は変更していない。既存変更を保持し、全変更は
未コミット。現在・次ともPhase 6。
