## ADDED Requirements

### Requirement: Package builds as sdist and wheel
The system SHALL produce both sdist (.tar.gz) and wheel (.whl) distributions via `python -m build` without errors.

#### Scenario: Clean build from source
- **WHEN** a developer runs `python -m build` in the project root
- **THEN** both `dist/lod-<version>.tar.gz` and `dist/lod-<version>-py3-none-any.whl` are created successfully

### Requirement: Package installs from wheel with working CLI
The system SHALL install from the built wheel and expose the `lod` CLI command with all subcommands functional.

#### Scenario: Fresh install and CLI invocation
- **WHEN** a user runs `pip install lod` in a clean virtual environment
- **THEN** the `lod` command is available on PATH
- **THEN** `lod --help` prints usage information listing `compile`, `check`, `proxy`, `remediate`, `benchmark`, and `registry` subcommands

#### Scenario: Subcommand execution after install
- **WHEN** a user runs `lod compile --help` after installing from PyPI
- **THEN** the command prints compile-specific usage without import errors

### Requirement: PyPI metadata is complete
The `pyproject.toml` SHALL include all metadata required for a professional PyPI listing: name, version, description, long_description (from README.md), author, license, classifiers, project URLs, and python_requires.

#### Scenario: PyPI page renders correctly
- **WHEN** the package is uploaded to PyPI
- **THEN** the PyPI page displays the project description (README), license badge, Python version badge, homepage link, and repository link

### Requirement: Build system is explicitly declared
The `pyproject.toml` SHALL include a `[build-system]` table specifying `setuptools>=68.0` as the build backend.

#### Scenario: PEP 517 compliance
- **WHEN** any PEP 517-compliant build frontend (pip, build) processes the package
- **THEN** it finds the `[build-system]` table and uses setuptools without fallback warnings

### Requirement: LICENSE file exists
The project SHALL include a `LICENSE` file containing the MIT license text with correct copyright holder and year.

#### Scenario: License file present
- **WHEN** a user or auditor inspects the repository
- **THEN** a `LICENSE` file exists at the project root with valid MIT license text
