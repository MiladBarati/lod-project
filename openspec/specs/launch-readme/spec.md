# launch-readme Specification

## Purpose
TBD - created by archiving change pypi-launch. Update Purpose after archive.
## Requirements
### Requirement: README converts visitors to installers
The README SHALL be structured to enable a cold visitor to understand what LOD does and how to install it within 10 seconds of landing on the page.

#### Scenario: First 10 seconds
- **WHEN** a developer lands on the PyPI page or GitHub repo
- **THEN** they see a one-line description of what LOD does
- **THEN** they see the install command (`pip install lod`)
- **THEN** they see a 3-command quick start example demonstrating immediate value

### Requirement: README includes quick-start demo
The README SHALL include a quick-start section with copy-paste CLI commands that work immediately after installation.

#### Scenario: Quick-start works end-to-end
- **WHEN** a user copies the quick-start commands after running `pip install lod`
- **THEN** each command executes without errors (given a valid OpenAPI spec file)
- **THEN** the user sees meaningful output demonstrating LOD's value

### Requirement: README lists all capabilities
The README SHALL include a feature summary covering all shipped capabilities: compile, check, proxy, remediate, benchmark, registry, middleware.

#### Scenario: Feature table completeness
- **WHEN** a user reads the feature summary section
- **THEN** all 8 core capabilities are listed with brief descriptions
- **THEN** the capabilities map to CLI commands or API usage patterns

### Requirement: README includes supported LLM formats
The README SHALL document the supported LLM output formats (Claude/XML, GPT/YAML, Gemini/TypeScript, default/LOM).

#### Scenario: Format table
- **WHEN** a user needs to know which LLM formats are supported
- **THEN** a table or list maps model names to output formats with corresponding CLI flags

### Requirement: README renders correctly on PyPI
The README SHALL use only markdown features supported by PyPI's renderer (no HTML, no GitHub-specific extensions that break on PyPI).

#### Scenario: PyPI rendering
- **WHEN** the package is uploaded to PyPI
- **THEN** the README renders without broken formatting, missing images, or mangled tables

