# Project

name: War Room Dashboard

purpose: Package the local 中枢项目台 as a polished open-source, GitHub-ready, local-first dashboard without publishing private SQLite data.

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
- Added `/api/health` for smoke checks.
- Added open-source docs, CI, contribution files, security policy, license, roadmap, examples, and release checklist.

open_source_positioning:

- "Local-first war room for AI operators and solo builders."
- Zero runtime dependencies.
- SQLite truth source.
- Privacy-first by default.
- Designed for project compounding: timeline evidence, reusable artifacts, review cards, and retrospectives.
