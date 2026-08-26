# Packaging Note

This folder is the GitHub-safe package of the local 中枢项目台.

What changed in this packaged version:

- Keeps app code in `app/`.
- Excludes the real local SQLite database from GitHub.
- Starts with one command: `./start.sh`.
- Adds README and project metadata.
- Keeps the dashboard local-first and dependency-free.
- Adds `/api/health` for reliable local and CI smoke checks.
- Adds standard open-source files: license, contributing guide, security policy, code of conduct, changelog, roadmap, issue templates, PR template, smoke test, and a CI recipe.

Before publishing a later version, check:

- `git status --short`
- `git check-ignore -v app/项目台.db`
- `python3 -m py_compile app/server.py`
- `python3 scripts/smoke_test.py --db-init-only`
- `PORT=8876 ./start.sh`
- `python3 scripts/smoke_test.py --url http://127.0.0.1:8876`
