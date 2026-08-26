# Packaging Note

This folder is the GitHub-safe package of the local 中枢项目台.

What changed in this packaged version:

- Keeps app code in `app/`.
- Excludes the real local SQLite database from GitHub.
- Starts with one command: `./start.sh`.
- Adds README and project metadata.
- Keeps the dashboard local-first and dependency-free.

Before publishing a later version, check:

- `git status --short`
- `git check-ignore -v app/项目台.db`
- `python3 -m py_compile app/server.py`
- `PORT=8876 ./start.sh`

