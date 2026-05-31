# Contributing

## Branching

Use short-lived branches from the current default branch:

```text
type/scope-summary
```

Examples:

```text
security/upload-validation
docs/readme-setup
chore/ci-smoke-tests
```

## Commit Messages

Use Conventional Commits:

```text
type(scope): subject
```

Allowed types:

```text
feat
fix
security
refactor
chore
docs
perf
test
```

Every non-trivial commit should explain:

- why the change is needed;
- what changed;
- whether there is a breaking change.

## Sensitive Data Rules

Never commit:

- `.env` files;
- uploaded face images;
- SQLite databases;
- CSV rosters or course exports;
- access logs;
- trained model files;
- local IDE/workspace metadata.

If sensitive data is committed, stop and report it privately before continuing.
History rewrites and force-pushes require explicit owner approval.

## Local Checks

Use Python 3.11+.

```powershell
python -m pip install -r requirements-dev.txt
ruff check .
pytest -q
```

Install `requirements-worker.txt` only on machines that need camera and Arduino
runtime support.

## Pull Requests

Pull requests should include:

- summary of the change;
- security impact;
- migration or breaking-change notes;
- verification commands;
- screenshots only when UI changes need visual review.

Use rebase-and-merge when possible so each atomic commit remains reviewable.
