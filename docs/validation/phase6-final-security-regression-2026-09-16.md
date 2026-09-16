# Phase 6 final security regression (2026-09-16)

## Outcome

final source commit `5b7d4de03e495fe630deab952de043f945a22bd7`と、そのcommitから再現buildした
local／remote final artifactに対して公開前security regressionを実行し、すべて成功した。

- focused security regression: 159件、158成功、1 expected skip
- full regression: 806件、767成功、39 expected skip
- local final deb verifier: 成功
- remote final deb verifier: 成功
- compileall、packaging shell構文、desktop validation、直接依存SBOM 2件のJSON parse、
  `git diff --check`: 成功

final artifact identity:

- local: `63f4b1b43d0b72f4578f30282d99313b675c29166e37637f9d79040bdbafece1`
- remote: `ee042ece330cc62febff1e4effdb59801ca55042bc845db54e0c5d78c8eea9e4`

## Source identity

採用product source `7f846f5fb1134be7df06490f30a5216ab414ae0d`からfinal source `5b7d4de`までの
`src`、`tests`、主要packaging／version surface差分は`debian/changelog`、`debian/control`、
`packaging/remote/control`のrelease metadata 3fileだけだった。製品実装とtest corpusは不変で、
final artifactは`5b7d4de`からbuild済みである。

## Covered boundaries

focused moduleはpre-final Gateと同一の17 moduleを再実行し、次を明示的に含む。

- common secret形式、argv／environment／quoted assignment／stderr／audit／UI errorのredactionと上限
- local backup、root evidence、helper staging/backend、application root、environment archiveの
  symlink、hardlink、FIFO、path traversal、unsafe ancestor拒否
- private state、backup、root evidence、helper、PolicyKit callerのowner/mode不一致拒否
- plan、report、change set、backup policy、target、request、review、evidence hashのmutation前再照合
- PolicyKit deny、timeout、late cancel、pre-cancelで成功を推測せずone-shotを維持する境界
- SSH host key failure、fingerprint欠落／曖昧／形式不正、診断後fingerprint変更のI/O前拒否

expected skip 1件は明示opt-inが必要な実Secret Service desktop Gateである。この境界はfinal artifactの
通常GUI local Apply／manual restore Gateで別途反復する。active desktop PolicyKitとSSH実経路も同様に
OS／GUI Gateへ分離し、このhost regressionで完了とは扱わない。
