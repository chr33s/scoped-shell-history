# shistory

SQLite shell history scoped to the current Git project, or to the exact current
directory outside a project. A Go binary owns configuration, scope detection,
privacy filtering, queries, and persistence. Thin Zsh and Bash adapters record
one completed event per command without replacing native history.

## Build and install

Development tools are pinned in `mise.toml`: Go 1.26.5, Python 3.14.7 (the PTY
test runner), fzf 0.74.4 (selector tests), and GitHub CLI 2.97.0 (release publishing).
Dependencies are pinned in `go.mod` and verified by `go.sum`.
Python, SQLite's CLI, and a C compiler are not runtime dependencies.

```sh
mise trust
mise install
mise run build
mkdir -p ~/.local/bin
cp bin/shistory ~/.local/bin/shistory
```

Add `~/.local/bin` to `PATH`, then add one of these to your shell configuration:

```zsh
# ~/.zshrc
source /path/to/shistory/shistory.plugin.zsh
```

```bash
# ~/.bashrc
source /path/to/shistory/shell/shistory.bash
```

Prebuilt archives are available on [GitHub Releases](https://github.com/chr33s/shistory/releases).
Each push to `main` publishes a release tagged `main-<full-commit-SHA>` after the
Linux and macOS checks pass. Archives cover macOS and Linux on ARM64 and AMD64,
and include the binary, shell adapters, completions, README, and license.
`SHA256SUMS` lists archive checksums. Reruns preserve published releases and
resume unfinished drafts.

Extract the matching archive, copy its `shistory` binary to `~/.local/bin`, and
source the adapters from a permanent location where you keep the extracted
directory. On macOS, verify the archive with `shasum -a 256 -c SHA256SUMS`
(the command also reports missing archives for platforms you did not download).

CI signs macOS release binaries with Developer ID and submits them to Apple for
notarization before publishing. Standalone executables cannot have notarization
tickets stapled, so Gatekeeper needs internet access to retrieve their tickets.
Local `mise run release` builds remain unsigned unless `MACOS_SIGNING_REQUIRED=1`.
[Apple documents the signing and notarization checks](https://support.apple.com/en-us/102445).

### Release signing secrets

Add these repository secrets under **Settings → Secrets and variables → Actions**:

| Secret | Value |
| --- | --- |
| `DEVELOPER_ID_CERTIFICATE_BASE64` | Base64 of a Developer ID Application `.p12` export including its private key. |
| `DEVELOPER_ID_CERTIFICATE_PASSWORD` | Password protecting that `.p12` export. |
| `DEVELOPER_ID_APPLICATION` | Full signing identity: `Developer ID Application: Your Name (TEAMID)`. |
| `KEYCHAIN_PASSWORD` | A random password for the temporary CI keychain. |
| `APPLE_ID` | Apple developer account email used for notarization. |
| `APPLE_TEAM_ID` | Developer team ID matching the signing certificate. |
| `APPLE_APP_SPECIFIC_PASSWORD` | App-specific Apple account password for notarization. |

On macOS, `base64 -i DeveloperIDApplication.p12 | pbcopy` prepares the certificate
secret. CI creates a temporary keychain and removes it and the certificate export
when signing finishes or fails. Missing secrets or failed notarization prevent
publication; PR checks do not use these secrets.

Zsh 5.9 and Bash 3.2 / 5.3 are tested. Bash 4+ supports the optional Readline
Ctrl-R binding; Bash 3.2 still supports recording and all CLI commands. On older
Bash, duration timestamps have one-second resolution. Loading twice is safe;
re-executing the shell starts a fresh random session.

## Use

```sh
h                            # list current project/directory history
hs migrate                   # search the current scope
hg kubectl                   # search all scopes
shistory list --directory    # only executions from this exact directory
shistory list --failed
shistory search --global --limit 20 'docker compose'
shistory scope --json
shistory doctor
```

Rows are newest first, ordered by execution timestamp then row ID. Storage keeps
repeated executions. Search collapses adjacent duplicate commands by default;
use `--dedupe=false` to see every execution. Search treats `%` and `_` as literal
text. Suggestions use a literal, case-sensitive prefix. `--session` and
`--hostname` filter query results.

`--format json` returns complete structured events, `raw` prints command text,
and `nul` separates unmodified commands with NUL bytes. Table output quotes
command text to preserve multiline readability and avoid terminal control
characters. `suggest` emits command text only, with a final output newline;
`navigate` emits `ID<TAB>command` with no added newline. `fzf` format is
`ID<TAB>command<NUL>` so selections preserve multiline commands.

The adapters capture the starting directory before execution, so `cd ../other`
belongs to the directory it was entered from. Git roots take precedence over
configured markers. Symlinks are resolved to canonical directories; linked Git
worktrees have their own project scopes. No database sync occurs.

## Configuration and privacy

Configuration defaults to `$XDG_CONFIG_HOME/shistory/config.toml`, or
`~/.config/shistory/config.toml`. Missing default configuration is fine; an
explicit missing `SHISTORY_CONFIG` is an error. Unknown settings are rejected.

```toml
[database]
path = "~/.local/share/shistory/history.db"

[root]
git = true
markers = [] # opt in, e.g. ["go.mod", "package.json", "pyproject.toml"]

[history]
ignore_leading_space = true
store_failed = true
max_results = 100
ignore = ["^ls$", "^pwd$", "^clear$"]

[search]
scope = "auto" # auto, directory, or global; affects search's default scope
dedupe = true
```

`[root] vcs = false` is an alias for disabling Git detection. `SHISTORY_CONFIG`
selects a different config file; `SHISTORY_DB` overrides the database path;
`SHISTORY_IGNORE` adds one Go regular expression to ignore rules. Without an
explicit database path, `$XDG_DATA_HOME/shistory/history.db` is used, falling
back to `~/.local/share/shistory/history.db`.

Leading-space commands are ignored by default. The dedicated database directory
has mode 0700 and the database 0600. Custom shared parent directories are not
chmodded. Credentials can still appear in recorded commands; ignore rules do
not perform secret detection.

```sh
shistory delete --id 928
shistory delete --scope .
shistory prune --days 90          # global retention
shistory prune --before 1700000000000 --scope .
shistory vacuum
```

Deletion and pruning print the number of removed rows. Vacuum reclaims database
space. SQLite uses WAL, a 1000 ms busy timeout, and short inserts; failed backend
writes do not interrupt an interactive shell. `doctor` checks integrity, schema,
WAL, timeout, and database permissions.

## Zinit and Zsh plugins

Install the binary first; loading the plugin does not download or build it.

```zsh
zinit light zsh-users/zsh-completions
autoload -Uz compinit
compinit
zinit light zsh-users/zsh-autosuggestions
zinit light zsh-users/zsh-history-substring-search
zinit light chr33s/shistory
zicdreplay # apply completion registrations captured by Zinit

# Opt in to scoped suggestions. A scope cache refreshes at startup and chpwd.
ZSH_AUTOSUGGEST_STRATEGY=(shistory completion)

# Bind your terminal's actual sequences. No bindings change by default.
bindkey '^[[A' shistory-history-up
bindkey '^[[B' shistory-history-down
bindkey '^R' shistory-reverse-search

# Optional native/global history fallback.
bindkey '^P' history-substring-search-up
bindkey '^N' history-substring-search-down
```

The adapter adds its navigation widgets to
`ZSH_AUTOSUGGEST_CLEAR_WIDGETS` without replacing existing entries. Empty-buffer
Up/Down traverses the scope; a nonempty buffer filters by substring. Repeated Up
walks older matches, Down walks newer matches and restores the original query
at the newest boundary. Row-ID cursors remain stable when other shells insert.
Changing scope resets navigation. To refresh scope after creating a repository
without changing directories, run `_shistory_refresh_scope`.

Zsh hooks are registered using `add-zsh-hook`. Completion definitions can be
loaded before `compinit`; when `compdef` is already available the Zinit entrypoint
registers `_shistory` immediately. Existing `h`, `hs`, and `hg` commands are
preserved.

## Optional scoped Ctrl-R

Install `fzf`, then bind `shistory-reverse-search` in Zsh. On Bash 4+, set
`SHISTORY_BIND_KEYS=1` before sourcing the adapter or run:

```bash
bind -x '"\C-r":_shistory_reverse_search'
```

Selections are inserted into the editing buffer and never executed automatically.
Cancellation leaves the buffer unchanged. Zsh's `SHISTORY_BIND_KEYS=1` also
binds terminfo Up/Down sequences when available. Manual bindings remain the most
portable choice. The CLI works without fzf.

## Bash behavior

Bash captures cwd/time once through a DEBUG trap, then obtains the complete
accepted history entry at the next prompt. Pipelines and multiline commands are
stored as one event. Both scalar and array `PROMPT_COMMAND` are chained, and an
existing DEBUG trap is retained with its incoming status. Native `HISTFILE`,
`HISTCONTROL`, and `HISTIGNORE` remain configured by the user; `histappend` is
enabled and `history -a` runs at each prompt.

Bash commands excluded from native history cannot be recovered by this approach.
In particular, `ignoredups`/`erasedups` may prevent repeated accepted lines from
being captured. To retain every execution, omit those native suppression options.
`cmdhist` and `lithist` preserve multiline entries as typed; without `lithist`,
Bash may normalize multiline syntax into semicolon-separated history text.
Commands that terminate or replace the shell (`exit`, `exec`) cannot be finalized
at a later prompt. These lifecycle limits also apply to Zsh prompt-based recording.

## Verification and releases

```sh
mise run verify       # Go tests, go vet, real Bash/Zsh PTY smoke tests
mise run compat-test  # downloads pinned upstream plugins, tests real Zinit/ZLE
mise run release     # CGO-free macOS/Linux, amd64/arm64 tarballs in dist/
```

The compatibility profile uses revisions in `tests/plugins.json` and tests
completion registration, rendered autosuggestions, project-only navigation,
native fallback bindings, scope transitions, retained hooks, and shell re-exec.
Go tests cover simultaneous first-run migrations/writes, worktrees, symlinks,
privacy rules, original multiline text, query filters, cursor stability, and
maintenance commands. CI runs both profiles on macOS and Linux.

The specification's later roadmap remains future work: history-file import,
command analytics, export, FTS5 optimization, redaction, a daemon/session scope
cache for Bash, and encrypted sync. Native Up/Down stays unchanged unless scoped
Zsh widgets are explicitly bound.
