"""Pinned, real Zinit plugin acceptance profile; exercises actual ZLE buffers."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

from shell_test import ROOT, PROMPT, Shell


class CompatibilityTests(unittest.TestCase):
    def test_zinit_profile(self):
        fixtures = ROOT / ".cache/plugins"
        repos = json.loads((ROOT / "tests/plugins.json").read_text())
        for repo, revision in repos.items():
            self.assertEqual((fixtures / repo.replace("/", "---") / ".revision").read_text(), revision)
        with tempfile.TemporaryDirectory(prefix="shistory-compat-") as temp:
            home = Path(temp).resolve()
            plugins = home / "zinit/plugins"
            plugins.mkdir(parents=True)
            for repo in repos:
                (plugins / repo.replace("/", "---")).symlink_to(fixtures / repo.replace("/", "---"))
            (plugins / "chr33s---shistory").symlink_to(ROOT)
            for name in ("project/api", "project/web", "other", "outside"):
                (home / name).mkdir(parents=True)
            for name in ("project", "other"):
                subprocess.run(["git", "init", "-q", str(home / name)], check=True)
            database = home / "shistory/history.db"
            env = dict(os.environ, SHISTORY_DB=str(database), SHISTORY_CONFIG="", SHISTORY_IGNORE="", HOME=str(home), XDG_CONFIG_HOME=str(home / "config"))
            # Seed without adding setup commands to native shell history.
            for seq, (directory, command) in enumerate([
                ("project/api", "echo scoped alpha"), ("project/web", "echo scoped beta"),
                ("other", "echo scoped outsider")
            ], 1):
                subprocess.run([str(ROOT / "bin/shistory"), "record", "--session", "fixture", "--seq", str(seq), "--shell", "zsh", "--cwd", str(home / directory), "--command", command, "--started-at", str(seq)], env=env, check=True)
            startup = f"""PS1='{PROMPT.decode()}'
HISTFILE=$HOME/native-history
HISTSIZE=10000
SAVEHIST=10000
setopt incappendhistory
autoload -Uz add-zsh-hook
_compat_hook() {{ :; }}
add-zsh-hook preexec _compat_hook
add-zsh-hook precmd _compat_hook
add-zsh-hook chpwd _compat_hook
zstyle ':zinit:config' home-dir '$HOME/zinit'
zstyle ':zinit:config' plugins-dir '{plugins}'
# CI checkouts can be group-writable; never block startup on compaudit.
zstyle ':zinit:config' compinit-opts -i
source '{fixtures}/zdharma-continuum---zinit/zinit.zsh'
zinit light zsh-users/zsh-completions
autoload -Uz compinit
compinit -D -i
zinit light zsh-users/zsh-autosuggestions
zinit light zsh-users/zsh-history-substring-search
zinit light chr33s/shistory
zicdreplay
ZSH_AUTOSUGGEST_STRATEGY=(shistory completion)
ZSH_AUTOSUGGEST_IGNORE_WIDGETS+=(_compat_dump)
unset ZSH_AUTOSUGGEST_USE_ASYNC
bindkey '^[[A' shistory-history-up
bindkey '^[[B' shistory-history-down
bindkey '^P' history-substring-search-up
bindkey '^N' history-substring-search-down
_compat_dump() {{ print -rn -- "$BUFFER"$'\\0'"$POSTDISPLAY" > "$HOME/buffer"; }}
zle -N _compat_dump
bindkey '^O' _compat_dump
"""
            shell = Shell(shutil.which("zsh"), home, startup)
            try:
                self.assertNotIn("command not found", shell.startup_output)
                self.assertNotIn("no such file", shell.startup_output)
                result = shell.command("print -r -- COMP:$_comps[shistory]; whence -w _git-flow; print -r -- HOOKS:$preexec_functions:$precmd_functions:$chpwd_functions")
                self.assertIn("COMP:_shistory", result)
                self.assertIn("_git-flow: function", result)
                self.assertIn("_compat_hook", result)
                shell.command("cd project/api")
                self.assertIn(str(home / "project"), shell.command("print -r -- $SHISTORY_SCOPE"))

                def buffer(keys):
                    path = home / "buffer"
                    if path.exists():
                        path.unlink()
                    os.write(shell.fd, keys)
                    # autosuggestions intentionally skips queries while input is queued.
                    time.sleep(0.15)
                    os.write(shell.fd, b"\x0f")
                    deadline = time.monotonic() + 3
                    while not path.exists() or not path.read_bytes():
                        shell.drain()
                        if time.monotonic() > deadline:
                            self.fail("ZLE buffer capture timed out")
                        time.sleep(0.01)
                    data = path.read_bytes().split(b"\0")
                    return [part.decode() for part in data]

                # Autosuggestions render only commands from the current project.
                captured = buffer(b"echo scoped ")
                if captured != ["echo scoped ", "beta"]:
                    os.write(shell.fd, b"\x15\n")
                    shell.prompt()
                    debug = shell.command("_zsh_autosuggest_strategy_shistory 'echo scoped '; print -r -- DEBUG:$SHISTORY_SCOPE:$suggestion; print -r -- $widgets[_compat_dump] $widgets[self-insert]")
                    self.fail(f"suggestion buffer {captured!r}; {debug}")
                os.write(shell.fd, b"\x15")  # clear without executing
                self.assertEqual(buffer(b"scoped\x1b[A")[0], "echo scoped beta")
                self.assertEqual(buffer(b"\x1b[A")[0], "echo scoped alpha")
                self.assertEqual(buffer(b"\x1b[B")[0], "echo scoped beta")
                self.assertEqual(buffer(b"\x1b[B")[0], "scoped")
                newest = shell.rows()[-1]["command"]
                os.write(shell.fd, b"\x15")
                self.assertEqual(buffer(b"\x1b[A")[0], newest)
                self.assertEqual(buffer(b"\x1b[B")[0], "")
                os.write(shell.fd, b"\x15\n")
                shell.prompt()
                shell.command("cd ../web")
                self.assertIn(str(home / "project"), shell.command("print -r -- $SHISTORY_SCOPE"))
                shell.command("cd ../../other")
                self.assertEqual(buffer(b"echo scoped "), ["echo scoped ", "outsider"])
                os.write(shell.fd, b"\x15\n")
                shell.prompt()
                shell.command("cd ../outside")
                self.assertIn(str(home / "outside"), shell.command("print -r -- $SHISTORY_SCOPE"))
                # Native fallback remains usable and separate from SQLite scopes.
                shell.command("print -s 'echo native-fallback'")
                self.assertEqual(buffer(b"native-fallback\x10")[0], "echo native-fallback")
                os.write(shell.fd, b"\x15\n")
                shell.prompt()
                shell.command("exec zsh -d -i")
                result = shell.command("print -r -- $preexec_functions $precmd_functions $chpwd_functions")
                self.assertEqual(result.count("_shistory_preexec"), 1, result)
                self.assertEqual(result.count("_shistory_precmd"), 1, result)
                self.assertEqual(result.count("_shistory_refresh_scope"), 1, result)
                second = Shell(shutil.which("zsh"), home, startup)
                try:
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        results = list(pool.map(lambda pair: pair[0].command(pair[1]), [
                            (shell, "printf shell-one-concurrent"),
                            (second, "printf shell-two-concurrent")
                        ]))
                    commands = {row["command"]: row for row in shell.rows()}
                    self.assertIn("printf shell-one-concurrent", commands, results)
                    self.assertIn("printf shell-two-concurrent", commands, results)
                    self.assertNotEqual(commands["printf shell-one-concurrent"]["session_id"], commands["printf shell-two-concurrent"]["session_id"])
                finally:
                    second.close()
            finally:
                shell.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
