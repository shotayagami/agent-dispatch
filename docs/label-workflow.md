# ラベルで AI に作業を任せる仕組み

最終確認: 2026-11-14。実行ホストの `~/bin/agent-dispatch` と補助スクリプトを読んで書いた。

## 概要

GitHub と Gitea の Issue や PR にラベルを付けると、実行ホストで 10 分ごとに動く `agent-dispatch` がそれを拾い、Codex または Claude に作業を渡す。1 回の起動で処理するのは 1 件だけで、PR のマージは人が行う。

対象は `AGENT_GH_OWNER` に設定した GitHub のオーナー配下と、Gitea の全リポジトリである。

## 構成

| 要素 | 実体 |
|---|---|
| 実行ホスト | Proxmox 上の LXC コンテナ（README の「実行環境」） |
| 起動 | systemd ユーザータイマー `agent-dispatch.timer`（`OnCalendar=*:0/10`）。service は oneshot で `TimeoutStartSec=65min` |
| 本体 | `~/bin/agent-dispatch` |
| 補助 | `agent-notify`（ntfy 通知）、`agent-impl-ai`、`agent-spec-ai`（担当の切り替え）、`agent-dispatch-handoff`（pr-fix の途中作業の引き継ぎ）、`agent-dispatch-verify`（impl の実装後の検証） |
| 検出 | `agent-detect`。systemd ユーザータイマー `agent-detect.timer`（毎時）で動く。対象は `~/.config/agent-detect/repos`（例は `systemd/agent-detect.repos.example`） |
| 状態とログ | `~/.local/state/agent-dispatch/` |
| 設定 | 環境変数 `AGENT_GH_OWNER`、`AGENT_GITEA_WEB`、`AGENT_GITEA_GIT`、`NTFY_AGENT_URL`、`NTFY_AGENT_TOPIC`（省略時は `agent-decisions`）。例は `systemd/env.example` |
| 決まり | `~/.claude/rules/agent-collaboration.md` と `agent-autonomy.md`。このリポジトリの `rules/` にサンプルがある |
| 役割定義 | `~/.claude/agents/spec.md` と `impl.md`。Codex と Claude に渡す役割の本文で、実行時に読む。このリポジトリの `agents/` にサンプルがある |
| テスト | `~/bin/tests`（`python3 -m unittest`） |

前回の実行が続いている間は flock で排他され、次の起動は何もせず終わる。

## ラベル

| ラベル | 付ける先 | 担当 | 結果 |
|---|---|---|---|
| `agent:spec` | Issue | Claude の `claude-opus-5-5`、次に `fable`。使えなければ Codex の `gpt-6-luna`、次に `gpt-6.1-terra` | 仕様を Issue にコメントする |
| `agent:impl` | Issue（仕様のコメントがあるもの） | Codex の `gpt-6.2-sol`。切り替えは後述 | worktree で実装し、PR を作ってレビューまで進める |
| `agent:pr-fix` | 利用者が作った PR | `agent:impl` と同じ | 既存 PR のブランチに修正を push し、PR に報告する |
| `agent:review` | 利用者が作った PR | 既定は Claude。使えなければ Codex | 差分のレビューを PR にコメントする |

## 使い方の流れ

1. Issue に依頼の内容を書き、`agent:spec` を付ける。
2. 次の起動（10 分以内）で拾われ、処理が終わると Issue に `## 仕様` のコメントが付いて、ntfy に通知が届く。人の判断が要る点があれば、`## 判断待ち` が別のコメントで続くので、判断をコメントで返す。
3. 仕様を確認し、判断待ちがあれば決めて仕様に反映してから、`agent:impl` を付ける。PR ができ、レビューのコメントが付き、ntfy に通知が届く。
4. 人が PR を確認してマージする。修正が必要なら PR に指摘を書いて `agent:pr-fix` を付ける。追加の push のあとにもう一度レビューさせるなら `agent:review` を付ける。
5. マージしたら、作った worktree を `~/bin/worktree-cleanup` で片付ける。

拾われたラベルは着手の時点で外される。続けて依頼するときは、ラベルを付け直す。

## 処理の中身

### 共通

- 候補は GitHub を `gh search`、Gitea を `tea api` で探す。見つけたあと、Issue 本体で open であることとラベルが今も付いていることを確かめ、付いている最初の 1 件を取る。
- 拾う前に、利用者の名義のコメントを読む。「着手: …」のコメントのあとに「完了: …」か「中断: …」の行も、レビューの結果の末尾の行もなければ、着手が閉じていないとみなす。その場合はラベルを外さずに飛ばし、`## 判断待ち` のコメントと ntfy で 1 度だけ知らせる。着手を閉じると、次の起動で拾われる。着手を書いたのが dispatcher か手作業のエージェントかは区別しない。コメントを読めなかったときも飛ばす。
- ラベルを外してから「着手: …」のコメントを書く。終えたときは「完了: …」のコメントで着手を閉じる。止められた場合や失敗した場合は、「中断: …」のコメントと ntfy で知らせる。
- エージェントに渡す Issue の本文とコメントは、`gh` と `tea` にログインしている利用者の名義のものだけで、他人の本文は「(利用者以外が書いたため省略)」に置き換わる。
- エージェントには forge の道具も資格情報も渡さない。コメントの投稿、コミット、push、PR の作成は `agent-dispatch` が行う。
- Claude は `--restricted` で起動するのでユーザー設定を読まない。そこで、実行するホストの `~/.claude/settings.json` で有効にしたプラグインと、`~/.claude/plugins/synced/` のプラグイン、`~/.claude/skills/` のスキルを `--plugin-dir` で渡す。プラグインの形になっていない単体のスキルは、実行のたびに `user-skills` と `anthropic-skills` (claude.ai から同期したもの) の 2 つのプラグインにまとめる。MCP は `--strict-mcp-config` で読まず、LSP は使えるツールに含めないので使われない。スキルを呼べるよう、どの経路でも Skill ツールを渡す。
- 読み取り専用の Codex は `--ignore-user-config` で起動し、読めるファイルを作業ツリーと実行に必要なものに限る。スキルの一覧と `~/.codex/AGENTS.md` はこの制限と関係なく渡るので、その本文を読めるよう、`~/.codex/skills`、`~/.agents/skills` と、AGENTS.md が指す `~/.claude/CLAUDE.md`、`~/.claude/rules`、`~/.claude/knowledge` の読み取りも許可する。`~/.codex/config.toml` は読まないので、そこで信頼済みにしたフックは動かない。実装の Codex はユーザー設定をそのまま読む。

### agent:spec

1. リポジトリを `--depth 100` で clone する。
2. Claude を `--restricted` で起動する。モデルは `claude-opus-5-5` で、利用できなければ `fable` で再試行する。MCP は読み込まず、使えるツールは Read、Grep、Glob、Skill と、仕様のファイルへの Write だけで、Bash は渡さない。時間は 20 分まで、費用の上限は 5 USD である。
3. 書かれた仕様を、`## 仕様` の形（決定、根拠、変更対象、検証方法、リスクと未決事項、次の担当）で Issue にコメントする。人の判断が要る点は `## 判断待ち` の節に書かれ、仕様とは別のコメントで投稿される。このとき仕様の末尾には、判断が決まるまで `agent:impl` を付けないよう書き、次の担当は人にさせる。「検証方法」には、実装後に自動で実行するコマンドを ` ```verify ` の囲みに 1 行 1 コマンドで書かせる（後述の実装後の検証）。書き終えた仕様は、保存する前に yomiyasu で推敲させる。Claude は Skill ツールで呼ぶが、Bash がないので検査スクリプトは動かせず、スキルにある目視の点検で代える。Codex はスキルのファイルを読み、検査スクリプトを記録なし (`--no-record`) で動かす。見出し、項目の名前、` ```verify ` の囲みの中身、コマンド、パス、識別子、数値は変えさせない。
4. Claude のどちらのモデルも利用できないと確認でき、途中の出力もない場合に限り、Codex `gpt-6-luna` を読み取り専用で起動する。MCP は読み込まず、web 検索も無効で、時間は 20 分までである。Luna も利用できなければ、同じ条件で Terra で再試行する。Terra も使えなければ Issue に中断を報告して止まる。

### agent:impl

1. リポジトリごとの bare clone（`~/.local/state/agent-dispatch/repos/`）から、`~/.worktrees/<repo>-issue-<番号>` に worktree を作る。ブランチは `feat/issue-<番号>` で、起点は既定ブランチである。既定ブランチ以外を起点と PR の基準にするリポジトリは、`~/.local/state/agent-dispatch/base-branch` に `<forge>:<リポジトリ> <ブランチ>` の形で 1 行ずつ書く（例: `gitea:gitea/proj dev`）。書いたブランチが origin になければ中断する。同名のブランチがリモートにあれば中断する。
2. Codex を `workspace-write` で起動する。ネットワークは使えず、git の操作もさせない。時間は 20 分までで、Issue のコメントにある `## 仕様` に従って実装し、`.agent-impl-report.md` に報告を書く。
3. 実装後の検証。仕様の最後の ` ```verify ` の囲みを、`agent-dispatch-verify` がネットワークなし・HOME なしの sandbox（bwrap）で順に実行する。1 コマンドは 300 秒までで、終了コード 0 を成功とみなす。失敗したら、出力の末尾を添えて Codex に最大 2 回直させ、検証をやり直す。直らなくても PR は作り、報告、完了のコメント、ntfy に「検証: 失敗」と書く。囲みがなければ「検証: 未実施」と書き、成功とは扱わない。失敗がすべて「コマンドが無い」（終了コード 127）のときは、実装ではなく sandbox の環境の問題として Codex に直させず、「検証: 未実施」と書く。sandbox の中では git が動かない。
4. 変更されたファイルを名前で指定して add し、`feat: <タイトル> (#番号)` でコミットして push する。PR の本文は報告に `Closes #番号` を足したものである。
5. `.github/workflows/` か `.gitea/workflows/` を変える差分は push せずに中断する。変更が空のときも中断し、`## 判断待ち` が報告にあればそれを添える。
6. 実装していない AI が差分をレビューして PR にコメントし、完了のコメントと ntfy で知らせる。作業用の `.agent-*` ファイルはログの横の `<ログ>.files/` に移す。

### agent:pr-fix

次の条件をすべて満たす PR だけが対象になる。満たさなければ中断する。

- 作成者が利用者である。
- open である。
- fork からの PR ではない。
- 基準ブランチが、既定ブランチか、`base-branch` にそのリポジトリの行として書いたブランチである。
- リモートのブランチ先頭が PR の head と一致している。

PR 専用の worktree（`~/.worktrees/<repo>-pr-<番号>`）で、PR 本文と利用者のコメントにあるレビュー指摘を修正する。push の直前に PR の状態を測り直し、head が変わっていれば push しない。push は fast-forward のみで、`--force-with-lease` に PR の head を指定する。

元のブランチ（`feat/issue-<番号>`）の worktree に未コミットの変更がある場合は、元を変更せずにスナップショットを取り、専用 worktree に引き継ぐ。PR 専用 worktree に前回の途中変更が残っていれば、内容を記録して再開する。引き継ぎ中に元の内容が変わった場合や、作業元が複数ある場合は、変更を保持したまま中断する。無視対象のファイルは移動も削除もしない。

### agent:review

作成者が利用者の PR だけを扱う。PR の head を `refs/pull/<番号>/head` から取得し、`origin/<基準ブランチ>` との差分を `.agent-diff.patch` に書いてレビューさせる。結果は `## レビュー` から始まり、最後に `判定: 問題なし` か `判定: 要修正` が付く。

Claude は `claude-opus-5-5`（利用できなければ `fable`）を `--restricted` で起動し、使えるツールを読み取りと Skill、`git status`、`git log`、`git show`、`git grep`、`git diff`、`git ls-files`、`ls` に限る。時間は 8 分まで、費用の上限は 3 USD である。Codex の場合も読み取り専用で、時間は 8 分までである。

## 担当の切り替え

| 作業 | 既定 | 利用不可のとき |
|---|---|---|
| spec | Claude `claude-opus-5-5`、次に `fable` | Codex `gpt-6-luna`、次に `gpt-6.1-terra`。どれも使えなければ中断 |
| impl | Codex `gpt-6.2-sol`、次に `gpt-6.2-astra`、`gpt-6-luna` | Claude `claude-sonnet-5-5`、`claude-opus-5-5`、`fable` の順（ファイルの読み書きだけで実装）。`impl-codex-only` が有効なら Claude には切り替えない |
| review（impl と pr-fix の後） | 実装していない AI。Codex が実装したときは Claude `claude-opus-5-5`、次に `fable` | もう一方の AI。どちらも使えなければ「独立レビューは未実施」と記録する |
| review（`agent:review`） | Claude `claude-opus-5-5`、次に `fable` | Codex |

`review-by-codex` が有効な間は、レビューを最初から Codex が行い、Codex が使えなければ Claude に切り替える。実装と同じ AI がレビューしたときは、コメントにその旨が付く。

切り替えるのは、利用上限、認証エラー、過負荷、コマンドが起動できないことを確認できた場合に限る。承認や安全上の拒否、時間切れ、原因が不明な失敗では切り替えない。impl では、途中の変更や生成物が worktree に残っている場合も切り替えない。

切り替えのコマンドは次のとおりである。状態は `~/.local/state/agent-dispatch/` にあるファイルの有無で決まる。

| コマンド | 状態ファイル | 内容 |
|---|---|---|
| `agent-impl-ai codex-only` / `default` / `status` | `impl-codex-only` | impl で Codex のモデルがすべて使えないときに、Claude へ切り替えるか |
| `agent-spec-ai review-codex` / `review-claude` / `status` | `review-by-codex` | レビューを最初から Codex にするか、既定に戻すか |

2026-11-21 に `agent-spec-ai status` で確認した現在の状態は、impl が `default`（Claude へ切り替える）、review が既定（Claude）である。

## 検出ループ（agent-detect）

AI を使わずに、仕事の候補を見つけて Issue にする。毎時、対象のリポジトリごとに次の 2 つを調べる。

- 既定ブランチの最新の push の CI が失敗している（cancelled と skipped は対象外）。
- 利用者が作った PR が 14 日以上更新されていない。

2 回続けて見えたものだけを、各リポジトリに Issue として作る。ラベルは付けないので、仕様化を頼むときは人が `agent:spec` を付ける。同じ検出の Issue が開いていれば重複して作らない。検出が解消したら、コメントを付けて閉じる。取得に失敗したリポジトリは「不明」として扱い、Issue を閉じない。Issue を作ったときだけ ntfy に知らせる。`agent-detect --dry-run` は検出結果を表示するだけである。

### アラートとセキュリティの検出

`AGENT_DETECT_ALERT_REPO` に置き場所のリポジトリを設定すると、次の検出も Issue にする。置き場所は GitHub に限る。取得元ごとの設定は README の「設定」にある。

| 取得元 | 対象 | 1 件の単位 | ラベル |
|---|---|---|---|
| Alertmanager | 発火中のアラート（Watchdog と InfoInhibitor、重大度 none と info を除く） | アラート名・名前空間・対象 | `incident` |
| Zabbix | 重大度が Average 以上の障害 | トリガー | `incident` |
| Wazuh | 修正版のある Critical と High の脆弱性 | ホスト × パッケージ | `security` |
| SimpleRisk | 閉じていないリスク | リスク | `security` |

- `incident` の Issue は、作ったあとに claude -p が読み取りだけで調査し、結果をコメントする。1 回の起動で 3 件までである。`security` の Issue は調査しない。
- 閉じた Issue と同じ検出がまた見えたら、新しく作らずに開き直し、再発の回数をコメントに書く。
- 取得に失敗した取得元の Issue は閉じない。
- Wazuh は、修正版があるかを `vulnerability.scanner.condition` で判定し、`Package default status` のものは数えない。indexer が Wazuh のホストの `127.0.0.1` だけで待ち受ける構成を前提に、起動のたびに SSH のポート転送を張り、読み終えたら閉じる。
- SimpleRisk は、API Extra がなくても読めるように、ログインしたセッションで `/api/v2/risks` を読む。Cloudflare Access の後ろにある前提で、サービストークンのヘッダを付ける。
- 資格情報とセッションの Cookie は、権限 700 の一時ディレクトリのファイルから渡し、コマンドの引数に出さない。

## 安全のための制限

- 利用者以外が作った PR は、`agent:review` でも `agent:pr-fix` でも扱わない。差分や本文が指示として読まれるのを避けるためである。ただし Gitea は全員が同じ `gitea` 名義で書き込まれるため、Gitea 上では作成者による絞り込みが効かない。外部の人の報告を依頼するときは、利用者が内容をコメントに書き直してからラベルを付ける。
- CI の定義を変える差分は push しない。
- 1 日の起動回数に上限がある（既定 60 回、環境変数 `AGENT_DISPATCH_DAILY_MAX` で変える）。検証の再実装も 1 回に数える。上限に達するとラベルを外さずに止め、翌日に自動で再開する。通知は 1 日 1 回である。金額は数えない。
- 危険な操作の判断は `agent-autonomy.md` の 3 段階（単独で実行、実行して報告、止まる）に従う。
- 閉じていない着手のコメントが残っている Issue や PR には手を付けない（`agent-collaboration.md`）。時間切れのあとに強制終了されると「中断」のコメントが書かれないので、そのときは人が「中断」のコメントで着手を閉じる。

## ログと調査

- ログは `~/.local/state/agent-dispatch/<日時>-<リポジトリ>-<番号>.log` にある。作業用のファイルは同名の `.log.files/` に残る。
- 起動の記録は `journalctl --user -u agent-dispatch` で見る。候補がなければ「候補: 0 件」と出る。
- `agent-dispatch --dry-run` は、候補を表示するだけで何も処理しない。
- 拾われないときは、ラベルが実在するか、Issue が open か、前回の実行が続いていないか（flock）を確かめる。GitHub の検索は反映が遅れることがある。
- 中断のコメントが付いたときは、原因を取り除いてからラベルを付け直す。実装の途中で止まった場合は、worktree が残っている。
