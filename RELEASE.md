# Release Process

This project uses a manual release workflow with automated changelog generation.

## How to Release

### 1. Trigger the Manual Release Workflow

Go to [Actions → Manual Release](https://github.com/wuwentao/midea-lan/actions/workflows/manual-release.yml) and click "Run workflow":

- **Branch**: `main` (default)
- **Release version**: Enter the version number (e.g., `2026.9.1`)

The workflow will:

- ✅ Validate the version format (must be `X.Y.Z`)
- ✅ Check that the tag doesn't already exist
- ✅ Generate changelog from commits since last release
- ✅ Update `.release-please-manifest.json` and `midealan/version.py`
- ✅ Create a release branch and open a PR

### 2. Review and Merge the Release PR

The workflow creates a PR titled `chore(main): release X.Y.Z`.

**Review checklist**:

- [ ] Version number is correct
- [ ] CHANGELOG.md contains all expected changes
- [ ] All CI checks pass

**Merge the PR** (squash or rebase, as configured).

### 3. Automatic Tag and GitHub Release

When the release PR is merged to `main`, the [Create Release workflow](https://github.com/wuwentao/midea-lan/actions/workflows/create-release.yml) automatically:

- ✅ Creates git tag `vX.Y.Z`
- ✅ Pushes the tag to GitHub
- ✅ Creates a GitHub Release with changelog excerpt

**Done!** 🎉 Your release is published.

## Version Numbering

This project uses Calendar Versioning (CalVer):

```
YYYY.MINOR.PATCH
```

Examples: `2026.9.1`, `2026.10.0`

## Changelog Generation

Changelogs are generated automatically by [git-cliff](https://github.com/orhun/git-cliff) based on [Conventional Commits](https://www.conventionalcommits.org/).

**Commit types that appear in changelog**:

- `feat:` → Features
- `fix:` → Bug Fixes
- `perf:` → Performance
- `refactor:` → Refactor
- `docs:` → Documentation
- `test:` → Testing

**Commit types that are hidden**:

- `chore:`, `ci:`, `build:` (unless they contain breaking changes)

## Tools

- **Changelog**: [git-cliff](https://github.com/orhun/git-cliff) (configured in `cliff.toml`)
- **Workflows**: `.github/workflows/manual-release.yml` and `.github/workflows/create-release.yml`
- **Version storage**: `.release-please-manifest.json` and `midealan/version.py`

## Migrating from release-please

The old `release-please.yml` workflow is disabled (push trigger commented out). If you need to use it for any reason, you can still trigger it manually via workflow_dispatch, but note that the `release-as` input does not work in manifest mode.
