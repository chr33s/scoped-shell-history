# Scoped Shell History Plugin — Sketch

## Goal

Build a Zsh/Bash plugin that stores shell history in SQLite and scopes history by:

1. **Project root**, when the current directory belongs to a project.
2. **Current directory**, when no project root is detected.

The core UX should feel like normal shell history, while allowing fast queries such as:

- history for the current project
- history for the current directory
- global history
- search by command text
- optionally replay or insert a selected command

---

## Proposed name

`shistory` or `scopehist`

Examples below use `shistory`.

---

## High-level architecture

```text
                    ┌──────────────────────────────┐
                    │          SQLite DB           │
                    │ ~/.local/share/shistory.db   │
                    └──────────────┬───────────────┘
                                   │
                         shared CLI / library
                                   │
                    ┌──────────────▼───────────────┐
                    │       shistory binary        │
                    │ detect scope / insert/query  │
                    └───────────┬───────────┬──────┘
                                │           │
                         ┌──────▼───┐   ┌──▼───────┐
                         │   Zsh    │   │   Bash   │
                         │ adapter  │   │ adapter  │
                         └──────────┘   └──────────┘
```

Keep shell code thin. Put scope detection, SQLite writes, migrations, filtering, and search in one executable.

A compiled binary is ideal eventually, but an MVP can be written in Python, Go, Rust, or even shell + `sqlite3`.


---

## Recommended stack

### Production choice

Use:

```text
Go
├── database/sql
├── pure-Go SQLite driver
├── TOML configuration
├── native CLI / small command dispatcher
├── Zsh adapter
├── Bash adapter
└── optional fzf integration
```

Recommended layers:

| Layer | Choice |
|---|---|
| Core language | Go |
| Database | SQLite |
| SQLite access | `database/sql` + pure-Go SQLite driver |
| Shell integration | Thin `.zsh` and `.bash` adapters |
| Config | TOML |
| Search | SQLite queries first, FTS5 later |
| Interactive search | Optional `fzf` |
| Packaging | Single binary + shell init scripts |
| Tests | Go unit/integration tests + shell smoke tests |

### Why Go

Go is the default recommendation because this is primarily a shell/CLI utility rather than a native desktop application.

Advantages:

- fast startup
- simple single-binary distribution
- straightforward SQLite support
- easy macOS and Linux releases
- strong cross-compilation story
- good fit for filesystem/process-oriented tooling
- low runtime/deployment friction
- simpler maintenance than Rust for a small utility

The target release matrix can be:

```text
darwin/arm64
darwin/amd64
linux/amd64
linux/arm64
```

This matters because shell configuration often follows the user onto:

```text
local macOS machines
Linux workstations
remote servers
dev containers
WSL
CI environments
```

### Why not Swift as the default

Swift is technically a strong fit on macOS and has an excellent SQLite ecosystem.

A Swift stack would look like:

```text
Swift
├── Swift Argument Parser
├── GRDB
├── Foundation
├── Swift Package Manager
└── thin Bash/Zsh adapters
```

Swift is preferable if the project is expected to evolve into a macOS-native product with:

```text
SwiftUI
AppKit
Keychain
Spotlight
LaunchAgents
iCloud
menu-bar UI
```

For a CLI-first tool intended to work across macOS and Linux, Go has the simpler deployment and release story.

Decision rule:

```text
CLI-first + macOS/Linux + remote machines
    -> Go

macOS-first + likely native UI/platform integration
    -> Swift
```

If this remains a personal macOS-only tool and the maintainer is significantly more productive in Swift, Swift is a fully reasonable choice.

### Why not Python for production

Python is useful for prototyping the shell lifecycle and scoping semantics.

It is less attractive for the production binary because the tool may run around every interactive command.

Potential drawbacks:

- interpreter startup
- runtime dependency
- packaging complexity
- environment/version management
- less convenient distribution to remote machines

A Python proof of concept is still useful before finalizing the shell hooks.

### Why not shell + `sqlite3`

Shell plus the `sqlite3` CLI is acceptable for a spike, but becomes brittle when handling:

```text
multiline commands
quoting
binary-safe arguments
migrations
configuration
concurrency
structured output
root detection
search
```

Keep shell as an integration layer only.

### Why not Rust as the default

Rust would also be a strong implementation choice:

- native startup
- static binaries
- strong SQLite libraries
- low runtime overhead

But for this project, Go achieves the important operational properties with less implementation complexity.

Rust is a good choice if the project is also intended as a systems-programming exercise.

### SQLite driver

Prefer a pure-Go SQLite driver so releases do not require CGO.

Benefits:

- simpler cross-compilation
- easier static-ish release artifacts
- fewer native build dependencies
- easier installation on remote machines

If advanced SQLite extension compatibility becomes important later, a CGO-based driver can be reconsidered.

### CLI framework

Avoid a heavy CLI framework initially.

The MVP only needs commands such as:

```text
shistory record
shistory list
shistory search
shistory scope
shistory doctor
shistory prune
```

The Go standard library plus a small dispatcher is sufficient.

Introduce something like Cobra only if the command surface becomes substantially larger.

### Configuration stack

Use TOML:

```text
~/.config/shistory/config.toml
```

TOML is preferable here because the configuration is user-edited and hierarchical.

Example:

```toml
[database]
path = "~/.local/share/shistory/history.db"

[root]
git = true
markers = []

[history]
ignore_leading_space = true
store_failed = true
max_results = 100

[search]
scope = "auto"
dedupe = true
```

### Search stack

Start with ordinary indexed SQLite queries.

Use:

```sql
WHERE command LIKE ?
```

for the initial implementation.

Add SQLite FTS5 only when:

- the database grows large enough to justify it
- richer tokenized search is needed
- prefix/fuzzy-ish matching becomes important

Do not introduce an external search service.

### Interactive UI stack

Keep `fzf` optional.

Core behavior:

```text
shistory search <query>
```

Optional richer behavior:

```text
Ctrl-R
  -> shistory emits candidates
  -> fzf filters/selects
  -> shell adapter inserts selected command into the buffer
```

The backend must remain useful without `fzf`.

### Recommended source layout

```text
shistory/
├── cmd/
│   └── shistory/
│       └── main.go
├── internal/
│   ├── config/
│   │   └── config.go
│   ├── db/
│   │   ├── db.go
│   │   └── migrations.go
│   ├── history/
│   │   ├── record.go
│   │   ├── list.go
│   │   └── search.go
│   ├── scope/
│   │   ├── detect.go
│   │   └── git.go
│   └── session/
│       └── session.go
├── shell/
│   ├── shistory.zsh
│   └── shistory.bash
├── migrations/
│   └── 001_init.sql
├── go.mod
└── README.md
```

The main architectural rule is:

> Make the shell adapters dumb and make the Go binary authoritative.

Scope detection, persistence, migrations, filtering, config, search semantics, and formatting should all live in the Go core.

---

## Scope model

For every command, compute:

```text
cwd        = directory where command was executed
project    = detected project root, if one exists
scope_type = "project" if project != null else "directory"
scope_path = project if project != null else cwd
```

Examples:

```text
~/src/acme/api/src
  git root: ~/src/acme
  scope: project:/home/me/src/acme

~/Downloads
  no project root
  scope: directory:/home/me/Downloads
```

This gives stable project-wide history while preserving directory-local history elsewhere.

---

## Project root detection

Start conservative.

### MVP

Use Git:

```sh
git -C "$PWD" rev-parse --show-toplevel
```

Only treat it as a project root when that succeeds.

### Later

Support configurable root markers:

```text
.git
.hg
.svn
package.json
pyproject.toml
go.mod
Cargo.toml
Gemfile
pom.xml
```

Recommended semantics:

- Git/VCS roots take precedence.
- Marker-based detection is opt-in or configurable.
- Cache `cwd -> root` mappings in memory per shell session.

Example config:

```toml
[root]
vcs = true
markers = ["pyproject.toml", "package.json", "go.mod", "Cargo.toml"]
```

---

## SQLite schema

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS history (
    id            INTEGER PRIMARY KEY,
    session_id    TEXT NOT NULL,
    seq           INTEGER NOT NULL,

    started_at    INTEGER NOT NULL, -- unix ms
    duration_ms   INTEGER,

    command       TEXT NOT NULL,
    exit_status   INTEGER,

    cwd           TEXT NOT NULL,
    scope_type    TEXT NOT NULL CHECK (scope_type IN ('project', 'directory')),
    scope_path    TEXT NOT NULL,

    shell         TEXT NOT NULL,
    hostname      TEXT,
    tty           TEXT
);

CREATE INDEX IF NOT EXISTS idx_history_scope_time
    ON history(scope_path, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_history_cwd_time
    ON history(cwd, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_history_time
    ON history(started_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_history_session_seq
    ON history(session_id, seq);
```

Optional FTS search:

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS history_fts
USING fts5(command, content='history', content_rowid='id');
```

For an MVP, `LIKE '%foo%'` is enough. Add FTS when the DB gets large.

---

## Command lifecycle

Capture two events:

```text
pre-command
  command text
  cwd
  project root / scope
  timestamp

post-command
  exit status
  duration
```

The pre-command state matters because the command itself may change directory.

Example:

```sh
cd ../other-project
```

That command belongs to the scope where it was entered, not the resulting directory.

---

## Zsh integration

Zsh provides clean hooks.

Use:

```zsh
autoload -Uz add-zsh-hook

add-zsh-hook preexec  _shistory_preexec
add-zsh-hook precmd   _shistory_precmd
```

Sketch:

```zsh
typeset -g SHISTORY_CMD=""
typeset -g SHISTORY_STARTED_NS=""

_shistory_preexec() {
  SHISTORY_CMD="$1"
  SHISTORY_STARTED_NS="$(date +%s%N)"

  command shistory begin \
    --session "$SHISTORY_SESSION_ID" \
    --cwd "$PWD" \
    --command "$SHISTORY_CMD"
}

_shistory_precmd() {
  local status=$?

  command shistory end \
    --session "$SHISTORY_SESSION_ID" \
    --status "$status"
}
```

A better implementation avoids invoking the backend twice per command. For example:

- store the pending command in shell variables
- write the previous command during `precmd`
- or batch writes through a lightweight daemon

For MVP simplicity, two calls are acceptable if the backend is fast enough.

---

## Bash integration

Bash is trickier.

Use a `DEBUG` trap to observe a command before execution, and `PROMPT_COMMAND` to finalize it after execution.

Do **not** blindly replace existing traps or `PROMPT_COMMAND`; chain them.

Sketch:

```bash
_shistory_debug_trap() {
  local last_status=$?

  [[ "$BASH_COMMAND" == _shistory_* ]] && return
  [[ "${SHISTORY_INTERNAL:-0}" == 1 ]] && return

  _shistory_pending_cmd="$BASH_COMMAND"
  _shistory_pending_cwd="$PWD"
  _shistory_started_at="$EPOCHREALTIME"
}

_shistory_prompt_command() {
  local status=$?

  if [[ -n "${_shistory_pending_cmd:-}" ]]; then
    SHISTORY_INTERNAL=1 shistory record \
      --session "$SHISTORY_SESSION_ID" \
      --cwd "$_shistory_pending_cwd" \
      --command "$_shistory_pending_cmd" \
      --status "$status"
    unset SHISTORY_INTERNAL
  fi
}
```

### Bash caveat

`DEBUG` fires for individual simple commands, including pieces of pipelines and shell internals.

For robust command-line capture, an alternative is to read the most recently accepted interactive history entry:

```bash
history 1
```

and flush it from `PROMPT_COMMAND`.

That tends to better match what the user typed.

Recommended Bash MVP:

1. Enable history immediately:
   ```bash
   shopt -s histappend
   ```
2. On every prompt:
   - save `$?`
   - run `history -a`
   - obtain the latest complete history entry
   - dedupe by history number/session sequence
   - write it to SQLite using the *captured pre-command cwd*

If exact multiline/pipeline behavior matters, test extensively across Bash versions.

---

## Session identity

Generate once when the shell starts:

```sh
SHISTORY_SESSION_ID="$HOSTNAME-$$-$(date +%s)"
```

Prefer a random UUID when available:

```sh
SHISTORY_SESSION_ID="$(uuidgen 2>/dev/null || printf '%s-%s-%s' "$HOSTNAME" "$$" "$RANDOM")"
```

Also keep a monotonic per-session sequence number.

This helps with:

- duplicate suppression
- ordering commands emitted in the same millisecond
- merging multiple shells safely

---

## Backend CLI

Minimal API:

```text
shistory record
shistory list
shistory search
shistory scope
shistory prune
shistory doctor
```

### Record

```sh
shistory record \
  --session "$SHISTORY_SESSION_ID" \
  --seq 42 \
  --shell zsh \
  --cwd "$PWD" \
  --command 'npm test' \
  --status 1 \
  --duration-ms 842
```

The backend should compute the root itself:

```text
cwd -> detect project root -> choose scope -> insert
```

This keeps root semantics identical across Bash and Zsh.

### Query current scope

```sh
shistory list --cwd "$PWD"
```

Backend:

```text
cwd
  -> project root if present
  -> otherwise cwd
  -> SELECT ... WHERE scope_path = ?
```

### Search current scope

```sh
shistory search --cwd "$PWD" 'kubectl'
```

### Search globally

```sh
shistory search --global 'kubectl'
```

---

## Shell UX

Keep the normal shell history mechanism intact initially.

Add a scoped history command:

```sh
h
```

Equivalent to:

```sh
shistory list --cwd "$PWD"
```

Suggested aliases/functions:

```sh
h          # current project/directory history
hg foo     # global search
hs foo     # scoped search
```

Example:

```text
$ hs migrate
  928  2h   0   ./manage.py migrate
  903  1d   1   ./manage.py migrate --plan
  711  6d   0   alembic upgrade head
```

---

## Arrow-key integration

There are two levels.

### Phase 1 — low risk

Keep native Up/Down behavior untouched.

Provide:

```text
Ctrl-R -> scoped SQLite search
```

This gives most of the value without fighting shell internals.

For Zsh, bind a ZLE widget.

For Bash, use Readline bindings or an external selector such as `fzf`.

### Phase 2 — replace history navigation

Implement Up/Down so it queries SQLite for the current scope.

This is feasible, but significantly more invasive because the shell already maintains its own in-memory history state.

Recommendation: avoid it in the MVP.

---

## Scoped reverse search

Best UX:

```text
Ctrl-R
  ┌ scoped: ~/src/acme
  │
  │ > docker
  │
  │ docker compose up db
  │ docker compose exec api bash
  │ docker build -t acme-api .
  └
```

On selection, insert the command into the current editing buffer instead of executing it.

Zsh:

```zsh
BUFFER="$selected"
CURSOR=${#BUFFER}
```

Bash can use Readline helpers or bind to a shell function where supported.

---

## Deduplication

Recommended policy:

- never dedupe at storage time by command text alone
- preserve actual execution history
- dedupe only when displaying search results

Why:

```text
make test
make test
make test
```

is meaningful execution history.

For interactive search, collapsing adjacent duplicates is useful.

Example SQL:

```sql
SELECT *
FROM history
WHERE scope_path = ?
ORDER BY started_at DESC
LIMIT 500;
```

Then collapse adjacent identical `command` values in the CLI.

---

## Ignore rules

Support familiar history exclusions.

Environment variable:

```sh
SHISTORY_IGNORE='^(ls|cd|pwd|clear)$'
```

Or config:

```toml
[history]
ignore = [
  "^ls$",
  "^cd( .*)?$",
  "^pwd$",
  "^clear$"
]
ignore_leading_space = true
store_failed = true
```

Important default:

```text
commands beginning with a space are not stored
```

This mirrors a common shell-history privacy convention.

Also consider filtering obvious secret-bearing commands, but do not promise secret detection as a security boundary.

---

## Security

The database may contain credentials pasted into commands.

Minimum safeguards:

```text
0600 ~/.local/share/shistory/history.db
0700 ~/.local/share/shistory/
```

Do not sync the DB by default.

Add:

```sh
shistory delete --id ...
shistory delete --scope .
shistory vacuum
```

Potential later feature:

```toml
[redact]
patterns = [
  "(?i)(password|token|secret)=\\S+"
]
```

Treat redaction as best-effort only.

---

## Concurrency

SQLite is a strong fit because many shells may append simultaneously.

Use:

```sql
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=1000;
```

Each record should be a short transaction.

Avoid keeping a transaction open between `preexec` and `precmd`.

Instead, either:

### Option A — one insert after command completes

Keep pending command metadata in shell variables:

```text
preexec:
  remember command + cwd + started_at

precmd:
  compute duration + status
  INSERT complete row
```

This is the preferred design.

### Option B — insert then update

Works, but doubles writes and leaves partial rows if a shell is killed.

---

## Recommended final hook model

### Zsh

```text
preexec:
  pending.command = full command line
  pending.cwd = $PWD
  pending.started_at = now

precmd:
  status = $?
  shistory record(pending..., status, duration)
```

### Bash

```text
before command:
  capture cwd + start time

PROMPT_COMMAND:
  status = $?
  obtain newest complete history entry
  shistory record(...)
```

The hard part in Bash is pairing the complete accepted command line with the directory where it began.

A practical solution is:

```text
DEBUG trap:
  capture cwd/start only once per prompt cycle

PROMPT_COMMAND:
  read latest complete history entry
  persist it
  reset state
```

---

## Suggested implementation language

### Go

Strong default for a standalone plugin:

- one binary
- fast startup
- easy SQLite support
- easy distribution
- no runtime dependency

Layout:

```text
cmd/shistory/
    main.go

internal/db/
    db.go
    migrations.go

internal/scope/
    detect.go

internal/history/
    record.go
    query.go

shell/
    shistory.zsh
    shistory.bash
```

Rust is also a good fit, but Go will likely be simpler for this utility.

Python is ideal for proving the design before compiling it.

---

## Config

```text
~/.config/shistory/config.toml
```

Example:

```toml
[database]
path = "~/.local/share/shistory/history.db"

[root]
git = true
markers = []

[history]
ignore_leading_space = true
store_failed = true
max_results = 100

[search]
scope = "auto"
dedupe = true
```

---

## Useful SQL queries

### Current scope

```sql
SELECT id, started_at, exit_status, cwd, command
FROM history
WHERE scope_path = ?
ORDER BY started_at DESC
LIMIT ?;
```

### Failed commands

```sql
SELECT started_at, cwd, command, exit_status
FROM history
WHERE scope_path = ?
  AND exit_status <> 0
ORDER BY started_at DESC;
```

### Project commands executed from a subdirectory

```sql
SELECT cwd, command
FROM history
WHERE scope_path = ?
ORDER BY started_at DESC;
```

### Most-used commands

This is more useful after normalizing command binaries separately.

```sql
SELECT command, COUNT(*) AS n
FROM history
WHERE scope_path = ?
GROUP BY command
ORDER BY n DESC
LIMIT 20;
```

---

## Optional normalized command field

Later, store the executable separately:

```text
command:      "git commit -am 'fix'"
command_name: "git"
```

Then queries such as:

```text
last 50 git commands in this project
failed npm commands
most common tools by project
```

become cheap.

---

## MVP

### v0.1

Implement:

- SQLite DB creation/migrations
- Git project-root detection
- fallback to current directory
- Zsh `preexec` + `precmd`
- Bash capture using `DEBUG` + `PROMPT_COMMAND`
- `record`
- `list`
- `search`
- `--global`
- ignore leading-space commands
- WAL + busy timeout
- current-scope `h` command

Do not replace shell-native Up/Down history yet.

### v0.2

Add:

- Ctrl-R scoped search
- `fzf` integration
- marker-based roots
- display dedupe
- durations
- import from `.zsh_history` / `.bash_history`

### v0.3

Add:

- command analytics
- pruning
- export
- optional hostname/session filtering
- sync only if explicitly designed with encryption

---

## Example behavior

Directory tree:

```text
~/src/acme/
├── .git/
├── api/
└── web/
```

Commands:

```text
~/src/acme/api $ pytest
~/src/acme/web $ npm test
```

Both are stored under:

```text
scope_type = project
scope_path = /home/me/src/acme
```

Then:

```text
~/src/acme/api $ h
pytest
npm test

~/src/acme/web $ h
pytest
npm test
```

Outside projects:

```text
~/Downloads $ unzip foo.zip
~/Downloads $ h
unzip foo.zip
```

Stored under:

```text
scope_type = directory
scope_path = /home/me/Downloads
```

---

## Main design decisions

1. **SQLite is the source of truth; shell adapters only capture events.**
2. **Scope is computed centrally by the backend.**
3. **A Git root defines one shared project-history namespace.**
4. **Outside projects, history is exact-directory scoped.**
5. **Store complete execution events; dedupe only in search/display.**
6. **Use one completed INSERT after the command returns.**
7. **Keep native history navigation initially; replace Ctrl-R first.**
8. **Preserve leading-space privacy behavior.**
9. **Use WAL mode so multiple shells can write concurrently.**
10. **Keep Zsh/Bash adapters small enough to audit.**

---

## Minimal command contract

The shell adapter only needs to call:

```sh
shistory record \
  --session "$SHISTORY_SESSION_ID" \
  --seq "$SHISTORY_SEQ" \
  --shell "$SHISTORY_SHELL" \
  --cwd "$command_start_cwd" \
  --started-at "$started_at" \
  --status "$exit_status" \
  --command "$command"
```

Everything else belongs in the backend.

That separation is the key design choice: shell integration stays fragile-but-small, while all persistence and scoping logic remains deterministic and testable.

---

## Zinit and existing Zsh plugin compatibility

The plugin must coexist with common Zinit-managed Zsh plugins, especially:

```zsh
zinit light zsh-users/zsh-completions
zinit light zsh-users/zsh-autosuggestions
zinit light zsh-users/zsh-history-substring-search
```

### Compatibility summary

| Plugin | Coexists unchanged? | Uses SQLite scoped history automatically? | Recommended integration |
|---|---:|---:|---|
| `zsh-users/zsh-completions` | Yes | N/A | Keep unchanged |
| `zsh-users/zsh-autosuggestions` | Yes | No | Add a `shistory` suggestion strategy |
| `zsh-users/zsh-history-substring-search` | Yes | No | Replace Up/Down bindings with `shistory` ZLE widgets |

The SQLite plugin should not replace or disable normal Zsh history. Native history remains available as a compatibility/fallback layer.

### `zsh-completions`

No special history integration is required.

`zsh-completions` extends Zsh's completion system through functions on `$fpath`; it does not depend on how command history is persisted.

Ensure completion initialization happens after the completion definitions have been made available.

A simple setup is:

```zsh
zinit light zsh-users/zsh-completions

autoload -Uz compinit
compinit
```

For a more Zinit-native setup, `zicompinit` / `zicdreplay` may be used.

`shistory` should eventually ship its own completion definition:

```text
shell/completions/_shistory
```

supporting:

```text
shistory record
shistory list
shistory search
shistory scope
shistory doctor
shistory prune
```

### `zsh-autosuggestions`

The plugin can be loaded normally:

```zsh
zinit light zsh-users/zsh-autosuggestions
```

However, its default `history` strategy searches Zsh's native `$history` associative array.

Therefore:

```text
SQLite contains project-scoped history
        !=
native Zsh history used by default autosuggestions
```

Without integration, autosuggestions continue to work, but suggestions are based on native/global Zsh history rather than the current `shistory` scope.

#### Custom `shistory` autosuggestion strategy

Provide a Zsh adapter function:

```zsh
_zsh_autosuggest_strategy_shistory() {
  local prefix="$1"

  suggestion="$(
    command shistory suggest \
      --cwd "$PWD" \
      --prefix "$prefix" \
      --limit 1 \
      2>/dev/null
  )"
}
```

Configure:

```zsh
ZSH_AUTOSUGGEST_STRATEGY=(shistory completion)
```

Semantics:

```text
typing:      git ch
cwd:         ~/src/acme/api
project:     ~/src/acme

query:
  most recent command
  WHERE scope_path = ~/src/acme
  AND command starts with "git ch"

suggestion:
  git checkout feature/foo
```

The backend should expose a specialized fast command:

```text
shistory suggest --cwd <cwd> --prefix <prefix>
```

rather than using the full general-purpose search output.

Requirements for `suggest`:

- output command text only
- no headings
- no timestamps
- no ANSI output
- one result by default
- very low startup/query latency
- escape nothing; emit the original command exactly

Suggested query:

```sql
SELECT command
FROM history
WHERE scope_path = ?
  AND command LIKE ? || '%'
ORDER BY started_at DESC, id DESC
LIMIT 1;
```

For prefix matching, an indexed or FTS-based optimization can be added later if needed.

#### Autosuggestion performance

Autosuggestions may query on each buffer change.

Therefore `shistory suggest` is on a latency-sensitive path.

Targets:

```text
process startup + query:
  ideal     < 5 ms
  usable    < 15 ms
```

Do not run Git root detection from scratch on every keystroke if it requires spawning `git`.

The Zsh adapter should cache:

```text
PWD -> scope_path
```

and refresh the scope on:

```text
chpwd
shell startup
explicit invalidation
```

Then call:

```zsh
shistory suggest --scope "$SHISTORY_SCOPE" --prefix "$prefix"
```

instead of:

```zsh
shistory suggest --cwd "$PWD" ...
```

This keeps autosuggestions responsive.

### `zsh-history-substring-search`

This plugin also coexists with `shistory`, but its own widgets search Zsh's native history.

Its normal bindings:

```zsh
bindkey '^[[A' history-substring-search-up
bindkey '^[[B' history-substring-search-down
```

will therefore remain global/native rather than project-scoped.

For the desired SQLite behavior, `shistory` should provide equivalent ZLE widgets:

```text
shistory-history-up
shistory-history-down
```

Conceptually:

```zsh
_shistory_history_up() {
  local result

  result="$(
    command shistory navigate \
      --scope "$SHISTORY_SCOPE" \
      --query "$BUFFER" \
      --direction older
  )"

  [[ -n "$result" ]] || return 0

  BUFFER="$result"
  CURSOR=${#BUFFER}
}

zle -N shistory-history-up _shistory_history_up
```

and similarly for `down`.

Bindings:

```zsh
bindkey '^[[A' shistory-history-up
bindkey '^[[B' shistory-history-down
```

The SQLite-backed widgets should implement the behavior users expect from `zsh-history-substring-search`:

```text
empty buffer:
    walk backward/forward through current scoped history

non-empty buffer:
    substring search inside current scoped history

repeated Up:
    older match

repeated Down:
    newer match
```

State should remain in Zsh variables between widget invocations:

```text
query
current result ID
scope
direction
```

The backend API should support stable navigation using history row IDs rather than sending an offset that becomes invalid if another shell inserts rows.

Example:

```text
shistory navigate \
  --scope /Users/me/src/acme \
  --query docker \
  --before-id 8421
```

### Keep `zsh-history-substring-search` as an optional fallback

It is acceptable to continue loading:

```zsh
zinit light zsh-users/zsh-history-substring-search
```

while binding the arrow keys to `shistory`.

This allows alternate bindings for native/global history if desired:

```zsh
# SQLite project-scoped navigation
bindkey '^[[A' shistory-history-up
bindkey '^[[B' shistory-history-down

# Optional native/global history fallback
bindkey '^P' history-substring-search-up
bindkey '^N' history-substring-search-down
```

Alternatively, once `shistory`'s widgets fully reproduce the desired behavior, the history-substring-search plugin can be removed.

### Interaction with `zsh-autosuggestions` widgets

`zsh-autosuggestions` wraps ZLE widgets and already knows about the upstream history-substring-search widget names.

Add the `shistory` widget names to its clear-widget list:

```zsh
ZSH_AUTOSUGGEST_CLEAR_WIDGETS+=(
  shistory-history-up
  shistory-history-down
)
```

This avoids stale inline suggestions while the history navigation widget changes the edit buffer.

### Hook safety

Use Zsh's hook mechanism:

```zsh
autoload -Uz add-zsh-hook

add-zsh-hook preexec _shistory_preexec
add-zsh-hook precmd  _shistory_precmd
add-zsh-hook chpwd   _shistory_chpwd
```

Do not overwrite:

```text
preexec_functions
precmd_functions
chpwd_functions
```

and do not assign a standalone `precmd()` or `preexec()` function that could interfere with other plugins.

This is important in a plugin-rich Zinit setup.

### Recommended Zinit load order

A straightforward configuration:

```zsh
# Completion definitions
zinit light zsh-users/zsh-completions

autoload -Uz compinit
compinit

# ZLE/history UI plugins
zinit light zsh-users/zsh-autosuggestions
zinit light zsh-users/zsh-history-substring-search

# Load shistory last so its final keybindings win.
source /path/to/shistory/shell/shistory.zsh
```

Then configure:

```zsh
ZSH_AUTOSUGGEST_STRATEGY=(shistory completion)

ZSH_AUTOSUGGEST_CLEAR_WIDGETS+=(
  shistory-history-up
  shistory-history-down
)

bindkey '^[[A' shistory-history-up
bindkey '^[[B' shistory-history-down

# Optional native/global fallback:
bindkey '^P' history-substring-search-up
bindkey '^N' history-substring-search-down
```

The exact arrow-key escape sequences vary by terminal, so the installer should not assume `^[[A` and `^[[B` universally.

### Better Zinit packaging

The repository should itself be loadable with Zinit:

```zsh
zinit light yourname/shistory
```

Repository layout:

```text
shistory/
├── shistory.plugin.zsh
├── shell/
│   ├── shistory.zsh
│   ├── shistory.bash
│   └── completions/
│       └── _shistory
└── ...
```

`shistory.plugin.zsh` should:

1. verify that the `shistory` binary exists
2. initialize the session ID
3. cache the current scope
4. register `preexec`, `precmd`, and `chpwd` through `add-zsh-hook`
5. define ZLE widgets
6. define the autosuggestions strategy when `zsh-autosuggestions` is present
7. avoid forcing keybindings unless explicitly enabled by config

### Recommended default behavior around existing plugins

The safest default is:

```text
zsh-completions:
    untouched

zsh-autosuggestions:
    automatically expose `shistory` strategy
    user/config chooses whether it is enabled

zsh-history-substring-search:
    untouched unless user enables shistory navigation bindings

native HISTFILE:
    preserved

SQLite:
    authoritative enhanced/scoped history store
```

This makes installation non-destructive and allows gradual adoption.

### Compatibility acceptance tests

Add an integration test profile equivalent to:

```zsh
zinit light zsh-users/zsh-completions
zinit light zsh-users/zsh-autosuggestions
zinit light zsh-users/zsh-history-substring-search
zinit light yourname/shistory
```

Test:

```text
1. `compinit` succeeds.
2. Existing completions still work.
3. Autosuggestions still render.
4. `shistory` autosuggestions only return current-scope commands.
5. Up/Down only traverse current-scope SQLite history when shistory bindings are enabled.
6. Ctrl-P/Ctrl-N can still traverse native history if fallback bindings are configured.
7. Changing directories inside one project does not change scope.
8. Changing to another project changes scope.
9. Changing to a non-project directory selects that exact directory as scope.
10. Multiple shells can insert history concurrently.
11. Existing plugin hooks remain registered.
12. `exec zsh` does not produce duplicate hook registrations.

