## Context

LOD is a Python CLI tool (v0.2.0) with 3,400 lines of production code across 11 modules, 1,500 lines of tests, and zero public distribution. The repo is named `json-to-markdown`, has no git commits, and is not published anywhere. The codebase is functional but packaged only for local `pip install -e .` development.

Current `pyproject.toml` is minimal — has `name`, `version`, `description`, `dependencies` (`tiktoken`, `jsonschema`), and a CLI entry point (`lod = "lod.cli:main"`). No classifiers, no URLs, no license declaration, no author metadata.

## Goals / Non-Goals

**Goals:**
- Make `pip install lod` work from PyPI with a fully functional CLI (`lod compile`, `lod check`, `lod proxy`, `lod remediate`, `lod benchmark`, `lod registry`)
- README that converts cold PyPI/GitHub visitors into installers (< 10 second decision)
- CI that runs the test suite on every push, signaling quality to visitors
- First git commit on a public GitHub repo under a coherent name

**Non-Goals:**
- Hosted proxy service (future Phase 2)
- Telemetry backend or dashboard (future)
- PyPI automation via GitHub Actions release workflow (do manually first, automate later)
- Comprehensive documentation site (README is sufficient for launch)
- Renaming the Python package internally (it's already `lod` — only the repo name is wrong)

## Decisions

### 1. Package name: `lod`

**Decision**: Publish as `lod` on PyPI.

**Rationale**: Short, memorable, matches the CLI command, matches the internal package name. Must verify availability on PyPI before publishing.

**Alternative considered**: `lod-cli` or `llm-optimized-docs` — rejected because longer names reduce memorability and the current internal name is already `lod`.

**Risk**: Name may be taken on PyPI. Fallback: `lod-cli`.

### 2. Build system: `pyproject.toml` with setuptools

**Decision**: Stay with setuptools. Add `[build-system]` table referencing `setuptools>=68.0` and `setuptools-scm`.

**Rationale**: Already using setuptools implicitly. No reason to migrate to hatch/flit/poetry for a launch — that's yak-shaving. Add the explicit `[build-system]` table that's currently missing.

**Alternative considered**: Poetry — rejected because it adds a dependency manager we don't need and changes the contributor workflow. Hatch — reasonable but unnecessary migration cost for launch.

### 3. CI: GitHub Actions, single workflow

**Decision**: One `.github/workflows/ci.yml` that runs `pytest` on Python 3.11+ on push to `main` and on PRs.

**Rationale**: Minimal viable CI. Signals quality. Catches regressions. Takes 10 minutes to set up.

**Alternative considered**: Multiple workflows (lint, test, publish) — rejected for launch. Add linting and auto-publish later.

### 4. README strategy: conversion-optimized, not documentation-complete

**Decision**: README follows the structure: one-liner → install command → 30-second demo → feature table → "why LOD" section. No deep docs.

**Rationale**: PyPI README is a landing page, not documentation. The goal is conversion: visitor → `pip install`. Deep documentation comes after there are users who need it.

### 5. License: MIT

**Decision**: MIT license. Create `LICENSE` file.

**Rationale**: Maximum adoption for a dev tool seeking initial traction. The open-source CLI is the PLG funnel per the business plan. Restrictive licensing kills distribution at this stage.

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| `lod` name taken on PyPI | Check before publishing. Fallback: `lod-cli`. Reserve immediately upon availability confirmation. |
| Tests fail in clean install environment | Run tests in CI with fresh venv before first publish. |
| `tiktoken` dependency is heavy (~50MB) | Accept for now. It's required for benchmarking. Can make it optional later with extras (`pip install lod[benchmark]`). |
| README doesn't convert | Iterate. Measure PyPI download stats weekly. A/B test nothing — just ship and improve. |
