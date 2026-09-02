# Phase 5 Recommendations Runtime Validation — 2026-09-02

## Scope

診断完了後のRecommendations画面へ既存Optimization RuleEngineを接続し、3 profile、localized summary、推奨内容、安全な値表示をUbuntu 26.04 desktop VMのPySide6 6.10.2でoffscreen検証した。main workstationへのPySide6導入、Ollama/OpenCode/systemd/SSH設定の変更は行っていない。

## Contract

- 診断reportと選択profileからcatalog version固定のOptimizationPlanを生成し、profile切替時に再評価する。
- setting、現在値、推奨値、severity、actionable/read-only、理由、影響を表示する。
- api key、token、password、secret、credentialを示すsetting名の値はpresentation境界で`<redacted>`にする。
- ja/enは同じcatalog key集合を持ち、言語切替時にprofile、summary、既存推奨一覧を再描画する。
- Recommendations widgetは安定したobject/accessibility nameを持ち、Qt以外のcoreへPySide6依存を追加しない。
- actionableかつ非conflictの推奨だけを明示選択でき、重複・未知・read-only IDを拒否する。選択後も`change_set=None`を維持する。
- Review画面は選択内容と、実行可能ChangeSetが未生成であることを明示し、Applyや承認を起動しない。

## Results

最初の強化Gateでは一般診断fixtureにAgent compaction設定がなく、期待2件に対して正しく0件となった。testをRuleEngine用のbaseline診断fixtureへ修正し、製品コードの挙動は変更しなかった。

更新後のVM Gateは8件全件成功した。QThreadPool/event-loop/cancel/windowの既存4件に加え、Agent profileでactionableなcompaction推奨2件、英語summaryと一覧内容、日本語profile/summary即時再描画、秘密設定値redaction、未知profile拒否を確認した。

後続のselection/Review Gateは9件全件成功した。Agent推奨を明示チェックし、Reviewへ遷移して選択1件と日本語のpreview-only警告を表示した。framework非依存testではselected IDの束縛、`change_set=None`、未知ID拒否を確認した。

source bundleはlibvirt private networkの一時HTTP serverからVM `/tmp/llm-manager-ui-gate`へ渡し、serverとhost側archiveはGate直後に削除した。VM側directoryはユーザーによる明示cleanup対象とする。
