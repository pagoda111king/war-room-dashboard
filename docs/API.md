# API Reference

Base URL:

```text
http://127.0.0.1:8766
```

All API responses are JSON.

## Health

### `GET /api/health`

Returns app status and row counts.

```json
{
  "ok": true,
  "app": "war-room-dashboard",
  "version": "0.1.0",
  "database": "项目台.db",
  "counts": {
    "projects": 4,
    "commits": 0,
    "artifacts": 0,
    "tasks": 4,
    "plans": 2,
    "cards": 3,
    "reviews": 0
  }
}
```

## Projects

- `GET /api/projects`
- `POST /api/projects`
- `PATCH /api/projects/:id`
- `DELETE /api/projects/:id`

Fields:

- `emoji`
- `name`
- `status`
- `ball`
- `what`
- `just_done`
- `doing_next`
- `blocker`
- `path`
- `lastmove`
- `category`

When `just_done` changes, the server automatically writes a timeline commit.

## Commits

- `GET /api/commits`
- `POST /api/commits`
- `DELETE /api/commits/:id`

Used for timeline evidence.

## Artifacts

- `GET /api/artifacts`
- `POST /api/artifacts`
- `DELETE /api/artifacts/:id`

Used for reusable outputs such as SOPs, docs, links, datasets, and decisions.

## Tasks

- `GET /api/tasks`
- `POST /api/tasks`
- `PATCH /api/tasks/:id`
- `DELETE /api/tasks/:id`

Fields:

- `project_id`
- `title`
- `status`
- `goal`
- `owner`
- `start_date`
- `due_date`
- `progress`
- `note`

## Plans

- `GET /api/plans`
- `POST /api/plans`
- `PATCH /api/plans/:id`
- `DELETE /api/plans/:id`

Used for daily plan and expectation tracking.

## Cards

- `GET /api/cards`
- `POST /api/cards`
- `PATCH /api/cards/:id`
- `DELETE /api/cards/:id`

`PATCH /api/cards/:id` supports:

```json
{"review": "correct"}
```

or:

```json
{"review": "wrong"}
```

This updates the SM-2 style scheduling fields.

## Battle

- `GET /api/battle/sessions`
- `GET /api/battle/events?session_id=:id`
- `POST /api/battle/sessions`
- `POST /api/battle/answer`
- `POST /api/battle/end`

Used for multi-role knowledge review.

## Card Questions

- `GET /api/card-questions`
- `POST /api/card-questions`
- `POST /api/card-questions/close-stale`

The stale-close endpoint closes inactive question threads after the configured local rule.

## Concept Notes

- `GET /api/concept-notes`
- `POST /api/concept-notes`
- `PATCH /api/concept-notes/:id`
- `POST /api/concept-notes/:id/graduate`

Concept notes can be graduated into review cards when enough structured fields exist.

## OpenMAIC Hook

- `GET /api/openmaic/status`

Checks whether the optional local `OPENMAIC_URL` service is reachable.
