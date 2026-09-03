# Phase 5 Backup Inventory Read-only UI Gate — 2026-09-04

## Decision

既存`BackupInventoryService`はlocal/remote copyとimmutable operation evidenceを集約するが、SSH production evidence repositoryのhost/fingerprint別compositionは未確定である。GUI表示境界に続き、local manifest/journalだけのstrict production loaderを接続した。全mutation actionは未接続に保つ。

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

## Local production loader

`LocalBackupStore.list_manifests_strict`と`LocalOperationJournal.list_for_host_strict`を追加した。通常の互換list APIは変更せず、GUI production refreshでは未知entry、symlink、owner/mode不一致、非canonical/改ざん、host/storage/target root不一致を1件でも検出すると一覧全体をfail closedにする。manifestとjournalを共通backup/operation IDで結合し、terminal journal statusまたは`backup_only`、local presence、manual protection、attentionをimmutable表示recordへ変換する。

state rootが存在しない場合は空tupleを返し、directoryを作らない。local factoryはSSH hostを拒否する。暗号本文は復号しないためSecret Service promptは発生せず、restore/rollback/cleanupも呼ばない。

Ubuntu 26.04/PySide6 6.10.2で、restart後のmanifest/journal結合、tamper/未知entry拒否、空state非生成、SSH分離、production entrypoint接続、Qt refreshを含む5件が0.040秒で成功した。

## Next

## SSH production inventory audit

既存OpenSSH境界を再監査した。root journal evidence取得は既知の`operation-id`と`request-hash`を必須にする固定`read-journal-evidence` commandだけであり、remote backup IDの列挙APIではない。remote retentionの`list_retention`はroot helper内で明示的な`prune-retention` requestを処理する前後の照合に使うbackendで、GUI refresh用のread-only transportとして公開されていない。

したがって現行protocolのままSSH production inventoryを接続すると、ID非束縛のremote列挙または新しいpasswordless sudo commandが必要になり、Phase 4で確定した最小権限境界を拡張する。Phase 5ではこれを暗黙に行わず、SSH hostをlocal loaderで拒否するfail-closed状態を維持する。local production inventoryとGUI read-only表示は独立して完了扱いとする。

## Next

次はlocal inventoryの表示情報を基に、復元内容をまだ読み出さないrestore previewと明示承認境界を設計する。実restore、rollback、delete、cleanupは接続しない。SSH inventory protocolの追加は、固定command、identity/fingerprint binding、権限、実SSH Gateを含む独立したmaterial変更として扱う。
