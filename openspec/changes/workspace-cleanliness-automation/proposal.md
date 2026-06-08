## Why

The repository is currently in a dirty state with staged deletions, untracked files, redundant directories, and no automated tools to enforce project formatting, linting, or testing standards. This introduces cognitive overhead and increases technical debt. Consolidating paths, cleaning the Git status, and configuring development tooling ensures developer velocity and codebase consistency.

## What Changes

- **Path Consolidation**: Delete the redundant root-level `specs/` directory and keep all specifications under `openspec/specs/`.
- **Git Status Cleanup**: Stage and commit untracked files (such as `workspace-maintenance` spec files) and resolve staged deletions.
- **Tooling Automation**: Add configurations for linting/formatting (`ruff`) and testing (`pytest`) inside `pyproject.toml` and clean up build artifacts.

## Capabilities

### New Capabilities
- None

### Modified Capabilities
- `workspace-maintenance`: Add requirements for development tooling automation and path structure consolidation.

## Impact

- No functional API or production code is affected.
- Updates configuration files (`pyproject.toml`).
- Changes workspace file structure by removing the empty root `specs/` directory.
