## ADDED Requirements

### Requirement: Tests run on every push to main
The CI pipeline SHALL execute the full test suite on every push to the `main` branch and on every pull request targeting `main`.

#### Scenario: Push triggers test run
- **WHEN** a developer pushes a commit to the `main` branch
- **THEN** GitHub Actions triggers the CI workflow
- **THEN** the workflow runs `pytest` against the full test suite
- **THEN** the workflow reports pass/fail status on the commit

#### Scenario: PR triggers test run
- **WHEN** a developer opens or updates a pull request targeting `main`
- **THEN** GitHub Actions triggers the CI workflow
- **THEN** the PR shows the CI check status (pass/fail)

### Requirement: CI tests on Python 3.11+
The CI pipeline SHALL test on Python 3.11 at minimum, matching the `requires-python` constraint.

#### Scenario: Python version matrix
- **WHEN** the CI workflow executes
- **THEN** tests run on at least Python 3.11
- **THEN** all tests pass before the workflow reports success

### Requirement: CI installs package from source
The CI pipeline SHALL install the package from source (not editable mode) to catch packaging issues.

#### Scenario: Non-editable install in CI
- **WHEN** the CI workflow sets up the test environment
- **THEN** it runs `pip install .` (not `pip install -e .`)
- **THEN** tests execute against the installed package, catching missing files or broken imports

### Requirement: CI workflow file is valid
The workflow file SHALL be a valid GitHub Actions workflow at `.github/workflows/ci.yml`.

#### Scenario: Workflow syntax
- **WHEN** GitHub parses `.github/workflows/ci.yml`
- **THEN** the workflow is accepted without syntax errors
- **THEN** the workflow uses `ubuntu-latest` as the runner OS
