# ADR-0010: 自動変更Endpointは対象HostのLoopback Ollamaだけとする

- Status: Accepted
- Date: 2026-08-29

## Decision

`OLLAMA_HOST`はloopback+portだけ、OpenCode `provider.ollama.options.baseURL`は同じ対象hostのloopback Ollama `/v1`だけを自動変更できる。non-loopback、wildcard、他provider、userinfo、redirectはdenylistとする。

## Consequences

MVPでunauthenticated APIの意図しない公開とcredentialの別origin送信を避けられる。LAN公開やreverse proxyは診断・手動案内に留める。
