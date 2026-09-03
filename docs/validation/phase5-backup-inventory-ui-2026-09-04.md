# Phase 5 Backup Inventory Read-only UI Gate — 2026-09-04

## Decision

既存`BackupInventoryService`はlocal/remote copyとimmutable operation evidenceを集約するが、production evidence repositoryのhost/fingerprint別compositionは未確定である。この段階ではGUI表示境界だけを実装し、production loaderと全mutation actionを未接続に保つ。

## UI boundary

- 初期表示ではinventory taskを開始しない。
- ユーザーの明示「再読込」でだけ、選択host IDへ束縛したtaskをQt workerで1回実行する。
- backup ID、dual-copy state、local/remote presence、manual protection、attention、coreが算出済みのallowed action名を表示する。
- host変更時は旧hostの一覧とerrorを破棄する。
- locale変更は現在のimmutable viewを再描画するだけでloaderを再実行しない。
- restore、rollback、delete、retention、cleanupを開始するbuttonやcallbackは持たない。
- UI moduleはinfrastructure、process、network、privilege APIをimportしない。

## Evidence

Ubuntu 26.04/PySide6 6.10.2 offscreen環境で対象1件が0.054秒で成功した。fake read-only taskのcall sequenceがrefresh時のfactory/load各1回だけであること、英日表示、一覧内容、locale変更後のcall非増加を確認した。実backup、manifest、journal、SSH、Secret Service、製品設定への変更は行っていない。

## Next

production接続は行っていない。次はlocalとSSHを分離したうえで、まずlocal manifest/journalをstrictかつread-onlyに列挙するcompositionを構築する。
