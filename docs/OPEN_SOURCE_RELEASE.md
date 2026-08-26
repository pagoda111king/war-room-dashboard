# Open Source Release Checklist

Use this before every public release.

## Privacy

- [ ] `git status --short` has no accidental database files.
- [ ] `git check-ignore -v app/项目台.db` confirms the real database is ignored.
- [ ] No `.env`, logs, screenshots with private data, or credentials are staged.

## Quality

- [ ] `python3 -m py_compile app/server.py scripts/smoke_test.py`
- [ ] `python3 scripts/smoke_test.py --db-init-only`
- [ ] Start app with `PORT=8876 ./start.sh`
- [ ] `python3 scripts/smoke_test.py --url http://127.0.0.1:8876`
- [ ] Desktop UI renders.
- [ ] Mobile-width UI renders.

## Documentation

- [ ] README reflects the latest behavior.
- [ ] API docs updated when endpoints change.
- [ ] Roadmap updated when priorities change.
- [ ] Changelog updated for release.

## GitHub

- [ ] Local smoke tests are green.
- [ ] If GitHub Actions is enabled manually, CI is green.
- [ ] Repo description is current.
- [ ] Topics are current.
- [ ] Release notes mention privacy boundary and local-first status.
