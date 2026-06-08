## Context

The workspace currently shows a dirty git working tree due to unstaged file deletions in `openspec/changes` and `openspec/changes/archive/`. Additionally, macOS system metadata files (`.DS_Store`) are present in several subdirectories under `openspec/`.

## Goals / Non-Goals

**Goals:**
- Commit the unstaged deletions of archived changes to sync git tracking with the physical directory structure.
- Clean up untracked macOS `.DS_Store` files from the local directory.
- Maintain a clean git working tree state.

**Non-Goals:**
- Editing library source code, configuration files, or tests.
- Modifying project dependencies.

## Decisions

1. **Delete local `.DS_Store` files**:
   - Run a search-and-destroy command `find . -name ".DS_Store" -delete` in the root workspace directory.
2. **Commit pending unstaged file deletions**:
   - Run `git add -u` to stage the deleted files and commit them to version control.

## Risks / Trade-offs

- **Risk**: Deleting necessary configuration files.
- **Mitigation**: `.DS_Store` files are OS-specific metadata and safe to delete. The deleted archived change files are already archived and no longer needed.
