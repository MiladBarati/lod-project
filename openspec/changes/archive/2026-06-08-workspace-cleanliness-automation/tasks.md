## 1. Path Consolidation & Local Cleanup

- [x] 1.1 Remove the redundant empty root-level `specs/` directory
- [x] 1.2 Delete stray local build directories (`dist/`, `lod_cli.egg-info/`)

## 2. Tooling & Automation Configuration

- [x] 2.1 Add configuration settings for the `ruff` linter and formatter in `pyproject.toml`
- [x] 2.2 Add configuration settings for the `pytest` test runner in `pyproject.toml`

## 3. Verification & Git State Synchronization

- [x] 3.1 Run `ruff check .` to verify formatting and style compliance
- [x] 3.2 Run test suite via `pytest` to verify test runner configuration
- [x] 3.3 Stage and commit all remaining untracked specs, config files, and archives to achieve a clean Git working tree status
