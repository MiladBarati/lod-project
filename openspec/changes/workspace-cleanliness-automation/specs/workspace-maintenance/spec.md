## ADDED Requirements

### Requirement: Workspace directory consolidation
The repository SHALL maintain a consolidated directory structure with no redundant, legacy, or empty directory paths.

#### Scenario: Verify spec paths consolidation
- **WHEN** verifying the root-level directories
- **THEN** the root-level `specs/` directory SHALL NOT exist, and all specifications SHALL be located within `openspec/specs/`

### Requirement: Automated code formatting and linting configuration
The repository SHALL define configurations for code formatting and linting tools inside `pyproject.toml` to programmatically enforce style standards.

#### Scenario: Verify ruff configuration
- **WHEN** inspecting the `pyproject.toml` file
- **THEN** it SHALL contain valid configuration blocks for the `ruff` linter and formatter

### Requirement: Standardized test runner configuration
The repository SHALL define configuration settings for the test runner inside `pyproject.toml` to unify test suite execution.

#### Scenario: Verify pytest configuration
- **WHEN** inspecting the `pyproject.toml` file
- **THEN** it SHALL contain valid configuration blocks for `pytest`
