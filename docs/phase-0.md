# Phase 0 技術調査・設計確定

## 1. 結論

Phase 0 の設計基準を次のとおり確定する。ここでの「確定」は実装方針の確定であり、実機検証済みを意味しない。実装および実機検証は後続Phaseで行う。

| 項目 | 決定 |
|---|---|
| OS | Ubuntu 26.04、Debian 13 |
| Python | 3.14.4 基準 |
| PySide6 | 最低 6.8.6。Python 3.14対応が公式release noteに明記された最初の版 |
| Ollama | 0.33.2 基準。API fixtureとsystemd effective stateで互換判定 |
| OpenCode | 1.18.25 基準。tag固定schema/source snapshotで互換判定 |
| Local privilege | PolicyKitから固定pathの限定helperを起動 |
| SSH privilege | system OpenSSH + external terminal + sudo + 同じ限定helper protocol |
| Backup | local正本 + SSH先復旧用copy、30日・10世代、任意暗号化 |
| Rule format | MVPは型付きPython定義、任意式を許さない |
| GUI concurrency | QThreadPool/QRunnable、Applyはworkflow coordinatorで直列化 |
| Locale | 日本語・英語、未対応localeは英語fallback |
| Remote helper | 別debをSSH先へ事前導入。未導入・非互換時はread-only |
| Backup keys | local/remote独立鍵。remote copyはremote鍵で単独復元可能 |
| Endpoint policy | 自動変更は対象hostのloopback Ollama endpointのみ |
| OpenCode edit | 既存scalar tokenのsource-span置換のみ。構造追加・削除はread-only |

## 2. 公式根拠

- Qt for Python 6.8.6 release noteはPython 3.14対応を明記している。[PySide6 release notes](https://doc.qt.io/qtforpython-6.8/release_notes/pyside6_release_notes.html)
- OllamaはLinuxのsystemd環境変数設定方法と主要なserver settingsを公式FAQで説明している。[Ollama FAQ](https://docs.ollama.com/faq)
- Ollama APIは厳密なversioningではないが、安定性と後方互換を期待すると公式に説明されている。[API introduction](https://docs.ollama.com/api/introduction)
- Ollamaの保存モデル、ロード中モデル、model detailは`/api/tags`, `/api/ps`, `/api/show`で取得できる。[tags](https://docs.ollama.com/api/tags), [ps](https://docs.ollama.com/api/ps), [show](https://docs.ollama.com/api-reference/show-model-details)
- OpenCode 1.18.25のtagは存在し、設定実装はJSON/JSONC、XDG config、複数sourceのmergeを使用する。[release](https://github.com/anomalyco/opencode/releases/tag/v1.18.25), [tagged config source](https://raw.githubusercontent.com/anomalyco/opencode/v1.18.25/packages/opencode/src/config/config.ts)
- OpenCode 1.18.25のtag固定schemaはmodel、provider、compaction等を定義する。[tagged schema](https://raw.githubusercontent.com/anomalyco/opencode/v1.18.25/packages/core/src/v1/config/config.ts), [provider schema](https://raw.githubusercontent.com/anomalyco/opencode/v1.18.25/packages/core/src/v1/config/provider.ts)
- pkexecは認証agentを利用し、引数自体を検証しないため、helper側の入力検証が必要である。[pkexec manual](https://polkit.pages.freedesktop.org/polkit/pkexec.1.html)
- Secret Serviceはlocked collectionとpromptを定義している。[Secret Service specification](https://specifications.freedesktop.org/secret-service/latest/ch03.html)
- user state/data/configの配置はXDG Base Directoryに従う。[XDG Base Directory](https://specifications.freedesktop.org/basedir/0.8/)
- `cryptography`は対象のUbuntu 26.04/Debian 13をtest対象に含み、AESGCMは12-byte nonceとassociated dataの認証を提供する。[installation](https://cryptography.io/en/stable/installation/), [AEAD API](https://cryptography.io/en/stable/hazmat/primitives/aead/)
- Microsoft `node-jsonc-parser`はsource edit APIを提供する一方、property追加時のinline comment再関連付け問題が報告されているため、MVPはより狭い既存scalar置換に限定する。[parser](https://github.com/microsoft/node-jsonc-parser), [known insertion issue](https://github.com/microsoft/node-jsonc-parser/issues/125)

## 3. Phase 0 成果物

- [Version matrix](version-matrix.md)
- [Setting allowlist](setting-allowlist.md)
- [Threat model](threat-model.md)
- [Traceability matrix](traceability.md)
- [Rule fixture contract](rule-fixtures.md)
- [ADR index](adr/README.md)

## 4. Phase 0 Exit 判定

基本判断に加え、remote helper配布、復旧鍵、endpoint、暗号container、JSONC編集方式をADRで確定したため、設計上のExit条件は満たす。ただし次は実装開始後の検証Gateとして残す。

- Ubuntu 26.04/Debian 13上でPySide6 6.8.6 wheel/import/Qt pluginを確認する。
- Ollama 0.33.2の実応答を保存しAPI fixtureを凍結する。
- OpenCode 1.18.25の有効config mergeとJSONC round-tripをsandboxで確認する。
- PolicyKit policy、remote helper、端末起動、Secret Serviceの利用可否を各desktopで検証する。
- AES-256-GCM envelopeのknown-answer/tamper/key-loss testを行う。
- OpenCode既存scalarのsource-span置換がコメントとbyte差分を保持することをfixtureで確認する。

Gate未通過の対象はread-onlyに縮退し、自動変更対応と表示しない。
