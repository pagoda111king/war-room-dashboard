# Contributing

Thanks for your interest in War Room Dashboard.

This project is intentionally small, local-first, and dependency-light. Contributions are welcome when they keep that spirit intact.

## Good First Contributions

- Improve documentation.
- Add reproducible smoke tests.
- Improve accessibility and responsive behavior.
- Add import/export helpers.
- Improve schema migration safety.
- Add small, optional integrations that do not break local-first usage.

## Design Principles

- Local-first by default.
- SQLite is the source of truth.
- Zero runtime dependencies unless a feature clearly deserves one.
- User data must stay private and ignored by Git.
- Prefer simple files and clear APIs over framework weight.
- A feature is not done until it can be verified locally.

## Local Setup

```bash
git clone https://github.com/pagoda111king/war-room-dashboard.git
cd war-room-dashboard
./start.sh
```

Open `http://127.0.0.1:8766`.

## Checks

```bash
python3 -m py_compile app/server.py scripts/smoke_test.py
python3 scripts/smoke_test.py --db-init-only
```

If a server is already running:

```bash
python3 scripts/smoke_test.py --url http://127.0.0.1:8766
```

## Pull Request Checklist

- No real `*.db`, `.env`, logs, or private user data committed.
- UI still works at desktop and mobile widths.
- `python3 -m py_compile app/server.py scripts/smoke_test.py` passes.
- `python3 scripts/smoke_test.py --db-init-only` passes.
- README or docs updated when behavior changes.
