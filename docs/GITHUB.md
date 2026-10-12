# Publishing to GitHub

The repository is a **pure GenLayer Intelligent Contracts project** — this
directory is pushed on its own. The documentation website lives outside this
directory in the sibling `frontend/` workspace folder and never enters
version control, so the pushed repo stays 100% contracts + tests + docs +
samples.

## First push

```bash
# from inside spec-clear/
git init -b main
git add .
git status                 # confirm: no node_modules/, no .venv/, no caches
git commit -m "SpecClear: consensus-profiled semantic batch clearing primitive (GenLayer)"

git remote add origin https://github.com/<your-account>/spec-clear.git
git push -u origin main
```

## Every later change

```bash
git add -A
git commit -m "<change summary>"
git push
```

## Tag the submittable state

Tag the exact commit the `submission/` package was taken from, so reviewers
can reproduce the artifact:

```bash
git tag -a submission-v1.0.0 -m "GenLayer submission package: spec_clear + fill_gate (lint-corrected)"
git push origin submission-v1.0.0
```

## Produce the GenLayer submission zip (frontend never included)

`git archive` exports a subdirectory straight from the tracked tree — the
cleanest way to prove the zip equals what is under version control:

```bash
# exact submission folder only — upload this to GenLayer
git archive --format=zip --output=spec-clear-submission.zip main:submission
```

Alternatively without git:

```bash
# Linux / macOS
zip -r spec-clear-submission.zip submission/
# Windows PowerShell
Compress-Archive -Path submission -DestinationPath spec-clear-submission.zip
```

## Verify before pushing

```bash
python scripts/preflight.py          # compile + header bytes + E022 + submission identity
pytest tests/unit -q                 # static boundary + address-sync guards
pytest tests/direct -q               # full protocol suites (Direct Mode)
```

All three must be green before a push that changes `contracts/`,
`submission/`, any test, or any documented deployment fact.

## Curl-only repo creation (no website click-through)

```bash
gh repo create spec-clear --public --source=. --push
# or, with plain curl (needs a PAT with repo scope):
curl -X POST -H "Authorization: Bearer <TOKEN>" https://api.github.com/user/repos \
  -d '{"name":"spec-clear","private":false,"description":"Consensus-profiled semantic batch clearing primitive for GenLayer"}'
```
