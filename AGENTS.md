# Agent Rules

These rules are given to agentic coding agents operating in this repo.

---

## Repository Shape
- Hermes plugin: `plugin/__init__.py` — PID namespace sandbox hook
- Standalone CLI: `standalone/terminal-jail` — universal bash wrapper
- systemd snippets: `systemd/` — gateway hardening examples
- Product specs: `specs/`
- Long-term memory: `.memory-bank/`
- Task board: `.coding-hermes/tasks.md`

## Process
- Make the smallest meaningful change. Validate after every step.
- Document what changed and why.

## Secrets and Privacy
- Never write secrets to `specs/`, `.memory-bank/`, git history, or logs.

## Git and Workspace Hygiene
- All commits MUST include `Co-authored-by: Alexis Okuwa <wojonstech@gmail.com>`.
- Always `git pull --rebase` before committing. Stash first if dirty.
- Use `git mv` for all file and folder moves.
- Never revert unrelated changes unless explicitly requested.
- Never run destructive git commands unless explicitly requested.

## GitReins Quality Harness
```bash
PATH="$HOME/go/bin:$HOME/gitreins-poc/.venv/bin:$PATH" gitreins guard
```
- secrets guard BLOCKS on fail — no exceptions.
- lint and tests BLOCKS on fail.
- Never commit with `--no-verify` for code changes.
