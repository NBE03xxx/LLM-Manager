# Architecture Decision Records

| ADR | Status | Decision |
|---|---|---|
| [0001](0001-system-openssh.md) | Accepted | system OpenSSHを利用する |
| [0002](0002-python-rule-engine.md) | Accepted | MVPルールは型付きPython定義 |
| [0003](0003-qt-threadpool.md) | Accepted | GUI taskはQThreadPool中心 |
| [0004](0004-privilege-helper.md) | Accepted | 固定pathの限定helperと宣言request |
| [0005](0005-backup-and-recovery.md) | Accepted | local+remote backupとjournal recovery |
| [0006](0006-locale.md) | Accepted | ja/en、英語fallback、UI境界翻訳 |
| [0007](0007-supported-versions.md) | Accepted | fixture gateでD/A対応を分離 |
| [0008](0008-remote-helper-package.md) | Accepted | SSH先helperは別debで事前導入 |
| [0009](0009-backup-crypto-and-keys.md) | Accepted | AES-256-GCMとlocal/remote独立鍵 |
| [0010](0010-endpoint-policy.md) | Accepted | 自動変更endpointはloopback Ollamaのみ |
| [0011](0011-opencode-jsonc-editing.md) | Accepted | 既存scalarのsource-span置換のみ |

ADRの変更は上書きせず、superseding ADRを追加する。
