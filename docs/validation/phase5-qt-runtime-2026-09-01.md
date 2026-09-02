# Phase 5 Qt Runtime Validation — 2026-09-01

## Scope

Ubuntu 26.04 disposable desktop VM `ubuntu26.04`へUbuntu repositoryの`python3-pyside6.qtcore`と`python3-pyside6.qtwidgets` 6.10.2を導入し、Phase 5のoptional Qt workerと最小Hosts/Diagnose widgetをoffscreen platformで検証した。main workstationへdependencyを導入していない。Ollama、OpenCode、systemd、SSH設定は変更していない。

sourceはlibvirt private network `192.168.122.1`上の一時HTTP serverからVM `/tmp/llm-manager-ui-gate`へ渡した。配信serverはGate直後に停止し、VM内artifactは明示cleanup対象とした。passwordはVM terminalのsudo認証だけで扱い、application、argv、stdin、log、repositoryへ保存していない。

## Results

| Gate | Result |
|---|---|
| QThreadPool execution | taskのQt threadがUI threadと異なることを確認 |
| event-loop responsiveness | worker実行中もzero-delay sentinel eventを処理 |
| result signal | background resultをUI event-loopで受信しhost lockを解放 |
| cancellation | shared `CancellationToken`へcancelを伝え、`cancelled` signalを受信 |
| minimum window | 6工程navigationとprimary controlsをoffscreen構築 |
| locale | Englishから日本語へ切替え、button/statusを即時更新 |
| vertical slice | Diagnose buttonからbackground fake reportを受け、Recommendationsへ遷移 |

初回window GateではtestがQt `objectName`で検索する一方、widgetが`accessibleName`だけを持つ不一致を検出し、両方を設定した。初回vertical sliceではfixture hostと選択hostの不一致をpresenterが拒否したためfixture bindingを修正し、production slotも不一致をstable `report_host_mismatch` failureへ変換した。最終4 runtime testsは全件成功した。

## Remaining boundary

実OpenSSH接続診断、host-key自動解決、Recommendations以降の実widget、長文layout、実display操作、packaged GUI entry pointは後続Phase 5 Gateとする。runtime testはPySide6不在環境ではskipし、optional importとcore testを継続する。

## Hosts/composition follow-up

同日、`~/.ssh/config`のread-only literal alias discovery、Local/OpenSSH task composition、host selectorを追加した。main workstationの実configはalias名を表示せずLocal 1件/SSH 1件として列挙し、接続は開始していない。実Local taskは固定allowlistで`partial` reportを返し、選択host ID bindingとOllama観測に成功した。system PATH外のOpenCodeは個別失敗となり、取得済み結果を保持した。host selectorを含むQt runtime回帰は同じVMで再検証する。
