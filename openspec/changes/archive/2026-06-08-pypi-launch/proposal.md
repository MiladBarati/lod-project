## Why

LOD has 8 shipped capabilities across 3,400 lines of production code and 1,500 lines of tests — but zero distribution. The repo hasn't been committed, isn't on PyPI, and has no public presence. Every day this stays local, the first-mover window for LLM agent schema governance narrows while better-funded teams converge on the same idea.

The single highest-leverage action is to make `pip install lod` work. Distribution is the bottleneck between "interesting prototype" and "real business."

## What Changes

- **Package metadata hardened** for PyPI publishing (classifiers, URLs, license, author metadata in `pyproject.toml`)
- **CLI entry point verified** end-to-end from a clean `pip install`
- **README rewritten** for PyPI landing page — must convert cold visitors into installers in under 10 seconds
- **Project renamed** from `json-to-markdown` to `lod` across all references — brand coherence matters
- **Build + publish pipeline created** — `python -m build` → `twine upload` workflow, documented and repeatable
- **Minimum viable CI** — GitHub Actions workflow that runs tests on push to `main`, so the public repo signals quality from day one
- **First git commit + public GitHub repo** — the code must exist in public before anything else matters

## Capabilities

### New Capabilities
- `pypi-packaging`: Everything required to publish LOD as a working PyPI package — metadata, build config, classifiers, sdist/wheel generation, and upload workflow
- `ci-pipeline`: GitHub Actions workflow for automated test execution on push/PR to `main`
- `launch-readme`: PyPI-optimized README with quick-start, feature summary, and install command — designed to convert cold traffic

### Modified Capabilities
_(none — no existing spec requirements are changing)_

## Impact

- **`pyproject.toml`**: Major metadata additions (classifiers, URLs, license, author, long_description)
- **`README.md`**: Full rewrite for PyPI landing page optimization
- **New files**: `.github/workflows/ci.yml`, potentially `LICENSE`, `MANIFEST.in`
- **Dependencies**: No new runtime dependencies. `build` and `twine` as dev/publish dependencies only
- **Risk**: Package name `lod` availability on PyPI must be verified before committing to the name
