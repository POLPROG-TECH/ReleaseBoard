# GitLab CI/CD Integration

ReleaseBoard ships with a production-grade `.gitlab-ci.yml` pipeline that lints, tests, builds, and publishes the project on every push and merge request.

## Table of Contents

- [Pipeline Overview](#pipeline-overview)
- [Stage Diagram](#stage-diagram)
- [Stages in Detail](#stages-in-detail)
  - [Lint](#lint)
  - [Test](#test)
  - [Build](#build)
  - [Pages](#pages)
- [Configuration Variables](#configuration-variables)
- [Caching](#caching)
- [Artifacts](#artifacts)
- [Coverage Badges](#coverage-badges)
- [Merge Request Integration](#merge-request-integration)
- [Customization](#customization)
  - [Adding a Deploy Stage](#adding-a-deploy-stage)
  - [Adding Scheduled Pipelines](#adding-scheduled-pipelines)
  - [Extending the Test Matrix](#extending-the-test-matrix)
- [Troubleshooting](#troubleshooting)

---

## Pipeline Overview

The `.gitlab-ci.yml` at the repository root defines a four-stage pipeline:

| Stage | Job | Image | Purpose |
|:------|:----|:------|:--------|
| **lint** | `ruff-lint` | `python:3.12-slim` | Static analysis with [ruff](https://docs.astral.sh/ruff/) — fails fast on code quality issues |
| **test** | `test` (matrix) | `python:3.12-slim`, `python:3.13-slim` | Runs the full pytest suite with coverage on Python 3.12 and 3.13 |
| **build** | `build-wheel` | `python:3.12-slim` | Builds the sdist + wheel and validates the CLI against an example config |
| **pages** | `pages` | `python:3.12-slim` | Deploys `docs/` to GitLab Pages (main branch only) |

The pipeline triggers on **merge request events** and **pushes to the default branch** via `workflow: rules`.

## Stage Diagram

```text
┌─────────┐     ┌──────────────────┐     ┌─────────────┐     ┌───────┐
│  lint    │────▶│  test            │────▶│  build      │────▶│ pages │
│          │     │  (3.12 + 3.13)  │     │             │     │       │
│ ruff     │     │  pytest + cov   │     │ wheel + CLI │     │ docs  │
│ check    │     │                  │     │ validation  │     │ deploy│
└─────────┘     └──────────────────┘     └─────────────┘     └───────┘
                                                              main only
```

## Stages in Detail

### Lint

```yaml
ruff-lint:
  stage: lint
  image: python:3.12-slim
  before_script:
    - pip install --quiet ruff
  script:
    - ruff check src/ tests/
```

- Runs `ruff check` against source and test directories.
- Fails fast — no point running tests if the code doesn't pass linting.
- Uses the project's `[tool.ruff]` configuration from `pyproject.toml`.

### Test

```yaml
test:
  stage: test
  image: python:${PYTHON_VERSION}-slim
  parallel:
    matrix:
      - PYTHON_VERSION: ["3.12", "3.13"]
  before_script:
    - pip install --quiet -e ".[dev]"
  script:
    - pytest --cov=releaseboard --cov-report=term-missing
        --cov-report=xml:coverage.xml --junitxml=report.xml -q
```

- **Matrix build** across Python 3.12 and 3.13.
- The main test suite runs **without** ReleasePilot installed. An optional `test-releasepilot` job (with `allow_failure: true`) tests the ReleasePilot integration separately — see the pipeline definition for details.
- Produces `coverage.xml` (Cobertura format) and `report.xml` (JUnit format).
- GitLab automatically parses both reports for the merge request UI.
- The `coverage` regex extracts the total percentage for the pipeline badge.
- Artifacts expire after **30 days**.

### Build

```yaml
build-wheel:
  stage: build
  image: python:3.12-slim
  before_script:
    - pip install --quiet build
    - pip install --quiet -e .
  script:
    - python -m build
    - releaseboard validate --config examples/config.json
```

- Builds both **sdist** and **wheel** via [PEP 517](https://peps.python.org/pep-0517/).
- Validates the installed CLI works by running `releaseboard validate` against the example config.
- `dist/` artifacts are retained for **90 days**.

### Pages

```yaml
pages:
  stage: pages
  image: python:3.12-slim
  script:
    - mkdir -p public
    - cp -r docs/* public/
  artifacts:
    paths:
      - public
  rules:
    - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH
```

- Copies `docs/` into `public/` for GitLab Pages.
- Only runs on the **default branch** (typically `main`).
- After deployment, docs are accessible at your project's GitLab Pages URL.

## Configuration Variables

The pipeline defines these variables globally:

| Variable | Value | Purpose |
|:---------|:------|:--------|
| `PYTHONDONTWRITEBYTECODE` | `1` | Prevents `.pyc` file creation in containers |
| `PIP_CACHE_DIR` | `$CI_PROJECT_DIR/.pip-cache` | Keeps pip downloads inside the project for caching |
| `PYTHONPATH` | `src` | Ensures `src/` layout is importable without install |

You can override any variable in **Settings → CI/CD → Variables** or in your fork's `.gitlab-ci.yml`.

## Caching

```yaml
default:
  cache:
    key: pip-${CI_COMMIT_REF_SLUG}
    paths:
      - .pip-cache/
    policy: pull-push
```

- **Per-branch cache key** — avoids cache pollution between branches.
- The `.pip-cache/` directory stores downloaded pip packages.
- `pull-push` policy means every job reads from and writes to the cache.

## Artifacts

| Job | Artifact | Retention | Format |
|:----|:---------|:----------|:-------|
| `test` | `coverage.xml` | 30 days | Cobertura XML |
| `test` | `report.xml` | 30 days | JUnit XML |
| `build-wheel` | `dist/` | 90 days | sdist + wheel |
| `pages` | `public/` | — | GitLab Pages |

Test artifacts are uploaded **even on failure** (`when: always`) so you can debug failing runs.

## Coverage Badges

To enable a coverage badge in GitLab:

1. Go to **Settings → CI/CD → General pipelines**
2. Under **Test coverage parsing**, set the regex to:

   ```
   TOTAL.*\s(\d+%)$
   ```

3. Save. The badge will appear on the project page and can be embedded in your README:

   ```markdown
   ![coverage](https://gitlab.com/your-group/releaseboard/badges/main/coverage.svg)
   ```

4. For the pipeline status badge:

   ```markdown
   ![pipeline](https://gitlab.com/your-group/releaseboard/badges/main/pipeline.svg)
   ```

> **Note:** The `test` job already includes the `coverage:` key with the regex, so GitLab parses it automatically.

## Merge Request Integration

On merge requests the pipeline runs all four stages (except **pages**). GitLab will:

- Show **ruff lint results** inline if the job fails.
- Display the **JUnit test report** in the MR widget with pass/fail counts.
- Show **Cobertura coverage** diffs inline on changed files.
- Display the **coverage percentage** change between the MR and target branch.

To require the pipeline to pass before merging, enable **Merge checks → Pipelines must succeed** in project settings.

## Customization

### Adding a Deploy Stage

To deploy the built wheel to a PyPI registry, add a stage after `build`:

```yaml
stages:
  - lint
  - test
  - build
  - deploy        # ← add
  - pages

deploy-pypi:
  stage: deploy
  image: python:3.12-slim
  dependencies:
    - build-wheel
  before_script:
    - pip install --quiet twine
  script:
    - twine upload dist/*
  rules:
    - if: $CI_COMMIT_TAG =~ /^v\d+\.\d+\.\d+$/
  variables:
    TWINE_USERNAME: __token__
    TWINE_PASSWORD: $PYPI_TOKEN
```

> **Note:** Store `PYPI_TOKEN` as a [masked CI/CD variable](https://docs.gitlab.com/ee/ci/variables/#mask-a-cicd-variable).

### Adding Scheduled Pipelines

For nightly readiness reports, create a [scheduled pipeline](https://docs.gitlab.com/ee/ci/pipelines/schedules.html):

1. Navigate to **CI/CD → Schedules** in your GitLab project.
2. Create a new schedule (e.g., daily at 06:00 UTC).
3. Add `workflow: rules` for `schedule` if needed:

   ```yaml
   workflow:
     rules:
       - if: $CI_PIPELINE_SOURCE == "merge_request_event"
       - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH
       - if: $CI_PIPELINE_SOURCE == "schedule"    # ← add
   ```

### Extending the Test Matrix

To add Python 3.14 (or any future version):

```yaml
test:
  parallel:
    matrix:
      - PYTHON_VERSION: ["3.12", "3.13", "3.14"]
```

To allow a new Python version to fail without blocking the pipeline:

```yaml
test-py314:
  extends: test
  variables:
    PYTHON_VERSION: "3.14"
  allow_failure: true
```

## Troubleshooting

| Issue | Solution |
|:------|:---------|
| **`ruff` not found** | The `ruff-lint` job installs ruff in `before_script`. Ensure the runner has internet access. |
| **Test failures on 3.13 only** | Check for version-specific API changes. Run `python3.13 -m pytest` locally to reproduce. |
| **Cache not speeding up jobs** | Verify `.pip-cache/` exists. Check **CI/CD → Pipelines → Job** for cache hit/miss messages. |
| **Coverage not showing in MR** | Ensure the regex `TOTAL.*\s(\d+%)$` is set in **Settings → CI/CD → General pipelines**. |
| **Pages not updating** | The `pages` job only runs on the default branch. Check that the `public/` artifact is produced. |
| **Build fails on `releaseboard validate`** | Ensure `examples/config.json` exists and is a valid configuration file. See [configuration.md](configuration.md). |
| **Pip install timeouts** | Increase pip timeout: add `PIP_TIMEOUT: "120"` to `variables`. |
| **Duplicate pipelines (MR + push)** | The `workflow: rules` block prevents this — MR pipelines take precedence when both apply. |

> **Note:** For detailed configuration options, see [configuration.md](configuration.md). For schema reference, see [schema.md](schema.md).
