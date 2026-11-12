# agents

`agent-dispatch` が実行時に読む、役割定義のサンプルです。`~/.claude/agents/` に写して使います。

- `bin/agent-dispatch` は、frontmatter を除いた本文だけを `spec`（Codex に渡す仕様作成）と `impl`（Claude に切り替えたときの実装）の指示に足します。ファイル名は `spec.md` と `impl.md` のままにしてください。
- `spec` の本文のうち、`# 仕様策定は Opus` で始まる行は、Codex に渡す前に取り除かれます。サンプルには、その行を置いていません。
- `model:` の値は、Claude Code から直接このエージェントを呼ぶときの指定です。`agent-dispatch` 経由では、モデルをスクリプトの定数で決めるため使いません。
- 内容は、自分の運用に合わせて書き換えてください。
