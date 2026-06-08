## Context

The workspace currently suffers from several inconsistencies that degrade developer velocity:
1. Redundancy: Two directories named `specs` exist (one under root and one under `openspec/specs/`). The root-level directory is empty.
2. Git status: The workspace contains staged deletions and untracked files (such as local specs and archives), causing status checks to report a dirty tree.
3. Tooling automation: The project's configuration file `pyproject.toml` lacks standardized linting, formatting, and test execution configs. Development relies on human memory rather than automated validation.

## Goals / Non-Goals

**Goals:**
- Consolidate all specs to `openspec/specs/` and delete the redundant root-level `specs/` folder.
- Clean up git working tree by tracking all specs/archives and finalizing staged deletions.
- Configure `ruff` and `pytest` in `pyproject.toml` to automate style standards and testing.

**Non-Goals:**
- Rewriting existing tests or test runners.
- Adding pre-commit hooks packages (out of scope for this change).
- Modifying production package code.

## Decisions

### Decision 1: Standardize Linting & Formatting with Ruff
We will add configuration settings for `ruff` to `pyproject.toml`.
- **Alternatives Considered**: `flake8` + `black` + `isort`.
- **Rationale**: `ruff` is significantly faster, provides equivalent/superior features, and reduces dependencies to a single package, improving system maintainability and compounding leverage.

### Decision 2: Consolidate Specification Directory
We will remove the empty root-level `specs/` directory and ensure all documentation resides in `openspec/specs/`.
- **Rationale**: Reduces path confusion and enforces a single, standard schema structure.

### Decision 3: Standardize Test Execution via Pytest
We will add a `[tool.pytest.ini_options]` config section in `pyproject.toml`.
- **Rationale**: Standardizes test execution settings (like python path and directory mappings) so developers can run test suites by typing `pytest` without needing custom wrappers.

## Risks / Trade-offs

- **Risk**: Ruff formatting conflicts with existing style, causing large diffs.
  * **Mitigation**: Perform a dry run with `ruff format --diff`. If diffs are minimal, apply formatting; if major, configure ruff rules to match existing code style.
- **Risk**: Discarding staged deletions could accidentally delete needed configurations.
  * **Mitigation**: Verify index contents using `git diff --cached` before committing or purging files.
