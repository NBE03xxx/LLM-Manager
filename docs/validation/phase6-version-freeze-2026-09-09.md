# Phase 6 MVP version freeze

## 結論

MVP release versionを`0.1.0`に固定した。PythonのPEP 440 versionとDebian package versionはどちらも`0.1.0`となる。

`debian/changelog`のdistributionは依然`UNRELEASED`である。これは最終OS lifecycle、resolved-environment SBOM、checksum/署名のGate前に公開可能と扱わないための意図的な境界である。

## 同期対象

- `pyproject.toml`と`src/llm_manager/__init__.py`
- `debian/changelog`と`packaging/remote/control`
- local/remote helper metadata
- local/remote CycloneDX SBOMのcomponent version、`bom-ref`、dependency root
- local/remote artifact verifier
- production local/remote helper compatibility allowlist
- helper compatibility test fixture
- packaging手順のartifact名

historical validation記録の`0.1.0~dev0`は当時artifactのidentityであるため書き換えていない。

## 検証

focused 23件の初回実行で、remote helper metadataの破壊testが旧`dev0`文字列を置換し、fixtureを実際に変更していないことを検出した。安定版の`0.1.0`を`0.2.0`へ置換する破壊fixtureに修正し、不正versionが`INVALID`となる検査を復旧した。

- focused version/helper/composition test: 23件成功
- host full suite: 791件中753件成功、38件expected skip（hostにPySide6 runtimeなし）
- `compileall`: 成功
- local/remote packaging shell syntax: 成功
- desktop entry validation: 成功
- local/remote CycloneDX JSON parse: 成功
- `git diff --check`: 成功

VM package、OpenCode/Ollama設定、service、backup/keyは変更していない。現在・次ともPhase 6。次はこのversion freeze commitから再現可能なlocal/remote artifact setをbuild・verifyし、最終lifecycle/SBOM Gateの入力を固定する。
