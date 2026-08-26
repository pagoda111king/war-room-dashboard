# Project

name: War Room Dashboard

purpose: Package the local 中枢项目台 as a clean, GitHub-ready dashboard without publishing private SQLite data.

entrypoint:

- `app/server.py`
- `app/index.html`

local_start:

```bash
./start.sh
```

public_boundary:

- Source code and docs are publishable.
- Real `项目台.db` is private and must stay ignored.
- Demo data is generated on first local start.

current_upgrade:

- Added command strip metrics.
- Added board search and status filter.
- Changed blocking review modal into a non-blocking review nudge.

