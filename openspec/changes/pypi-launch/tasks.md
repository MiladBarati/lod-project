## 1. Package Metadata & Build System

- [x] 1.1 Add `[build-system]` table to `pyproject.toml` specifying `setuptools>=68.0` and `wheel`
- [x] 1.2 Add full project metadata to `pyproject.toml`: author, author-email, license, classifiers (Development Status, Intended Audience, Topic, License, Python version), project URLs (Homepage, Repository, Issues)
- [x] 1.3 Set `long_description` to read from `README.md` with `content-type = "text/markdown"` via `[project]` `readme` field
- [x] 1.4 Create `LICENSE` file with MIT license text
- [x] 1.5 Verify `python -m build` produces both sdist and wheel without errors

## 2. README Rewrite

- [x] 2.1 Write one-liner hero description at top (what LOD does in one sentence)
- [x] 2.2 Add install command block (`pip install lod`) immediately below hero
- [x] 2.3 Write 3-command quick-start section (compile, check, proxy) with copy-paste examples
- [x] 2.4 Create feature summary table covering all 8 capabilities with brief descriptions
- [x] 2.5 Add supported LLM formats table (Claude/XML, GPT/YAML, Gemini/TypeScript, default/LOM)
- [x] 2.6 Verify README uses only PyPI-compatible markdown (no HTML, no GitHub-specific extensions)

## 3. CI Pipeline

- [x] 3.1 Create `.github/workflows/ci.yml` with trigger on push to `main` and PRs targeting `main`
- [x] 3.2 Configure workflow: ubuntu-latest, Python 3.11, `pip install .` (non-editable), `pytest`
- [x] 3.3 Validate workflow YAML syntax locally (e.g., `actionlint` or manual review)

## 4. Pre-Publish Verification

- [x] 4.1 Run full test suite in a clean venv with non-editable install (`pip install .` then `pytest`)
- [x] 4.2 Verify `lod --help` works and lists all subcommands after clean install
- [x] 4.3 Test `lod compile --help`, `lod check --help`, `lod proxy --help` for import errors
- [x] 4.4 Check PyPI for `lod` name availability; if taken, fall back to `lod-cli`

## 5. Publish & Ship

- [ ] 5.1 Create initial git commit with all project files
- [ ] 5.2 Create public GitHub repository (named `lod`)
- [ ] 5.3 Push to GitHub and verify CI workflow runs and passes
- [ ] 5.4 Build final sdist + wheel with `python -m build`
- [ ] 5.5 Upload to PyPI with `twine upload dist/*`
- [ ] 5.6 Verify `pip install lod` works from PyPI in a clean environment
