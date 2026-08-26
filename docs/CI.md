# CI Recipe

This repository includes a local smoke test in `scripts/smoke_test.py`.

If you want GitHub Actions, create `.github/workflows/ci.yml` with:

```yaml
name: CI

on:
  push:
  pull_request:

jobs:
  smoke:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Compile
        run: python3 -m py_compile app/server.py scripts/smoke_test.py

      - name: Smoke test database init
        run: python3 scripts/smoke_test.py --db-init-only
```

Why this file is documented instead of enabled by default:

- Some GitHub OAuth tokens cannot push workflow files without the `workflow` scope.
- The project remains fully verifiable with local smoke tests.
- Maintainers can enable Actions manually when their GitHub token allows it.
