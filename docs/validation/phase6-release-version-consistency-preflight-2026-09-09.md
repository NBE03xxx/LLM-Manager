# Phase 6 release version consistency preflight

## 目的

release versionを変更する際、Python package、Debian package、helper互換性、SBOM、artifact verifierの一部だけが古いversionのまま残ることを防ぐ。このpreflightでrelease version自体は確定しない。

## 追加したGate

`DebianPackagingTests.test_release_version_surfaces_are_consistent`が次を同一version setとして検証する。

- `pyproject.toml`のPEP 440 development versionと`src/llm_manager/__init__.py`
- PEP 440 `.devN`からDebian `~devN`への明示変換
- `debian/changelog`とremote helper `control`
- local/remote helper metadata
- local/remote CycloneDX component version、`bom-ref`、dependency root reference
- local/remote artifact verifierの期待version
- production local/remote helper compatibility allowlist

現行値はPython `0.1.0.dev0`、Debian `0.1.0~dev0`である。最終OS lifecycle、resolved-environment SBOM、署名条件が揃う前に最終releaseを名乗らない。

## 再開環境

- route freeze commit `8854232`: `origin/main`へpush済み
- host system SSH: root-owned configurationを通常経路で利用可能
- Ubuntu 26.04: running、guest agent IP `192.168.122.48`、logged-in userなし
- Debian 13: `shut off`
- UbuntuへのBatchMode SSH: UID 1000で成功
- remote helper: 未導入
- OpenCode config候補3件: すべて不在

SSH user Apply disconnect/reconciliationの再Gateにはremote helper導入の管理者認証が必要である。GUIにpasswordを入力せず、未導入状態でmutationを開始しない。

## 検証結果

- focused distribution test: 8件成功（新規testの単体実行を含む）
- host full suite: 791件中753件成功、38件expected skip（hostにPySide6 runtimeなし）
- `compileall`: 成功
- local/remote packaging shell syntax: 成功
- desktop entry validation: 成功
- local/remote CycloneDX JSON parse: 成功
- `git diff --check`: 成功

現在・次ともPhase 6。
