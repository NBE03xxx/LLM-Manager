# Phase 6 accessibility修正後candidate再現build — 2026-09-13

commit `ff7913bb97e896f7992720b9a43c2382970a5fc8` のtracked sourceのみを
`git -c tar.umask=0022 archive`で独立した2つの一時directoryへ展開し、
local/remote両debを各2回buildした。両artifactともSHA-256が完全一致した。

| artifact | SHA-256 |
| --- | --- |
| `llm-manager_0.1.0_all.deb` | `351edec886ff06f7e72979e7e6022abac45354871dbd412cab724d01f9518243` |
| `llm-manager-remote-helper_0.1.0_all.deb` | `830f50b2b22984bba9622d10cca81a54571e101655f0fbd53c7a7fe76b774d2d` |

採用candidateは `/tmp/llm-manager-candidate-ff7913b-20260913/` に0644で保持する。
versionは0.1.0、UNRELEASEDを維持する。

## 検査

- 各local build内806 test成功（767成功・39 expected skip）。
- local/remote専用package verifierを各回実行し成功。
- 展開した全fileにELF、共有library、bytecode/cacheがないことを確認。
- 実行fileはlocalの固定launcher/helper 5本とremote helper 1本のみ。
- source commit、toolchain、2回のhash、実行file一覧を
  `candidate-build-2026-09-13/build-evidence.json`へ保存。
- 各local build logをgzipで保存し、証拠dirのSHA256SUMSを作成。

local debのhashは前回のaccessibility修正確認用overlay artifactと一致する。
したがって、英日AT-SPIと通常終了の記録は、このlocal debと同一byteのartifactに対する
検証として関連付けられる。過去のb15a984 local lifecycleとは異なるartifactである。
remote helperはprivate runtimeにUI sourceも含む構成のためhashが変わっており、
旧remote helperのlifecycle証拠を新artifactの検証済み根拠として流用しない。

## 次の作業

新candidateのOS lifecycle、remote helper、SSH、SBOM等の残Gateを継続する。
最終release時にはUNRELEASED解除後のartifact確認と署名・公開が必要。
VM、package、設定、serviceを変更していない。一時build treeは証拠JSONのpathに保持する。
