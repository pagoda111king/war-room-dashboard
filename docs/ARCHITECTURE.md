# Architecture

War Room Dashboard is intentionally simple:

```text
Browser UI
   |
   | HTTP / JSON
   v
Python standard-library server
   |
   | sqlite3
   v
Local SQLite database
```

## Components

### `app/index.html`

Single-page application containing:

- Layout and styles.
- Project board rendering.
- Big-goal grouping, drag-and-drop assignment, and project creation forms.
- Timeline and Gantt rendering.
- Artifact, review card, question, concept note, and retrospective views.
- Direct `fetch()` calls to the local JSON API.

### `app/server.py`

Zero-dependency HTTP server using:

- `http.server.ThreadingHTTPServer`
- `sqlite3`
- `json`
- Python standard-library helpers only

Responsibilities:

- Serve `index.html`.
- Initialize and migrate SQLite tables.
- Seed demo data on first start.
- Provide JSON CRUD endpoints.
- Keep big goals separate from projects while allowing nullable project assignment.
- Provide local review-card scheduling helpers.
- Provide `/api/health` for verification.

### `app/项目台.db`

Local SQLite source of truth.

This file is intentionally ignored by Git. Each user gets their own local database.

## Data Flow

1. User edits a project card in the browser.
2. The UI sends a `PATCH /api/projects/:id` request.
3. The server updates SQLite.
4. If `just_done` changed, the server records a timeline commit.
5. The UI reloads the affected views.

## Local-First Boundary

The app binds to `0.0.0.0` so phones on the same Wi-Fi can access it. This is convenient for private LAN use, but it is not public-internet hardening.

Before public deployment, add:

- Authentication
- HTTPS
- Backups
- Write permissions
- Data redaction
- Rate limiting

## Why Not a Framework?

The first version is deliberately small:

- Easy to inspect.
- Easy to fork.
- Easy to run on any machine with Python.
- No build chain.
- No dependency lock-in.

Frameworks may be useful later, but the current goal is a durable, understandable personal tool.
