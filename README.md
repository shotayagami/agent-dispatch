# agent-dispatch

GitHub と Gitea の Issue や PR に付けたラベルを、実行ホストで 10 分ごとに拾い、Codex または Claude に作業を渡す仕組みです。仕組みの説明は [docs/label-workflow.md](docs/label-workflow.md) にあります。

| ディレクトリ | 内容 | 配置先 |
|---|---|---|
| `bin/` | 本体と補助スクリプト | `~/bin/` |
| `tests/` | テスト（`tests/` で `python3 -m unittest`） | `~/bin/tests/` |
| `systemd/` | ユーザータイマーと service | `~/.config/systemd/user/` |
| `rules/` | 協調と判断範囲の決まり（サンプル） | `~/.claude/rules/` |
| `agents/` | spec と impl の役割定義（サンプル） | `~/.claude/agents/` |

## 実行環境

実行ホストは Proxmox 上の LXC コンテナです。開発とビルドに使っているコンテナで、この仕組みはその中で systemd のユーザータイマーとして動きます。

| 項目 | 内容 |
|---|---|
| OS | Debian 13（trixie） |
| 資源 | 10 コア、メモリ 16 GiB（2026-11-12 時点） |
| 実行ユーザー | 一般ユーザー 1 つ。ログアウト後も動かすため、linger を有効にしている |
| 必要なコマンド | `git`、`gh`（2.46.0）、`tea`（0.16.0）、`jq`、`python3`、`node`（nvm の v24）、`codex`、`claude`（Claude Code 2.1.302） |
| ログイン | `gh` は GitHub、`tea` は login 名 `gitea-home`（Gitea の管理者トークン）。`codex` と `claude` も各 CLI でログインしておく |
| 通知 | `~/.env.ntfy-agent` の `NTFY_AGENT_TOKEN` で ntfy に送る |
| 保存先 | `~/.local/state/agent-dispatch/`（ログ、bare clone、切り替えの状態ファイル）と `~/.worktrees/`（実装用の worktree） |

service は PATH に nvm の node の `bin` を含めています。別の環境に移すときは、このパスと、上の表のコマンドとログインを先に整えてください。

## 設定

接続先は環境変数で渡します。`systemd/env.example` を `~/.config/agent-dispatch/env` に写して値を入れると、service が `EnvironmentFile` として読みます。手で実行するときにも、同じ変数が必要です。

| 変数 | 内容 |
|---|---|
| `AGENT_GH_OWNER` | 検索する GitHub のオーナー名 |
| `AGENT_GITEA_WEB` | 人に見せる Gitea の URL |
| `AGENT_GITEA_GIT` | git と API の接続先になる Gitea の URL |
| `NTFY_AGENT_URL` | ntfy の URL |
| `NTFY_AGENT_TOPIC` | ntfy のトピック名（省略時は `agent-decisions`） |

`worktree-cleanup` も `AGENT_GITEA_GIT` を読みます。Gitea の PR を確かめるとき、接続先のホストがこのホストと同じで、`~/.env` に `GITEA_API_KEY=<トークン>` の行があれば、そのトークンで API を呼びます。トークンはコマンドの引数に出さず、標準入力から curl に渡します。どちらかが無ければ、これまでどおり `~/.netrc` で認証します。

## サンプルについて

`rules/` と `agents/` の中身は、運用中のものをもとに、環境固有の値を外して書き直したサンプルです。実際の運用で使っているファイルそのものではありません。

本体は実行時に `~/.claude/agents/spec.md` と `impl.md` を読むため、`agents/` のファイルは配置が必要です。`rules/` は本体が読まないので、使わなくても動きます。

## 補足

2026-11-14 時点の実行ホストの内容を写したものです。パスのユーザー名は `/home/yagamin` に置き換えてあります。ユーザー名がこれと違う環境では、systemd の service の絶対パスを直す必要があります。テストはこのリポジトリの `bin/` のスクリプトを読むので、直す必要はありません。認証情報は含まれていません。ntfy のトークンは `~/.env.ntfy-agent` から読みます。

## ライセンス

MIT ライセンスです。詳しくは [LICENSE](LICENSE) を見てください。
