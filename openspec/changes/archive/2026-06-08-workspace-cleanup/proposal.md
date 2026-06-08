## Why

The workspace contains unstaged deleted files from archived changes and untracked `.DS_Store` files. This creates repository noise, increases cognitive load, and violates git hygiene best practices. Cleaning up the git state and local OS junk ensures a clean, reliable workspace.

## What Changes

- Stage and commit the deletion of archived changes in `openspec/changes/` and `openspec/changes/archive/`.
- Remove all untracked `.DS_Store` files from the project subdirectories.

## Capabilities

### New Capabilities

- `workspace-maintenance`: Define requirements for repository hygiene, version control cleanliness, and build environment isolation.

### Modified Capabilities

- None

## Impact

- No functional code, APIs, or dependencies are affected.
- Cleans up the Git working tree.
