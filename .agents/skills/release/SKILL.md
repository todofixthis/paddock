---
name: release
description: Use when preparing or publishing a new release or hotfix of phx-paddock — covers release notes, version bump, build, PyPI upload, GitHub release creation, and merging main back into develop
---
# Release

## Phase 1 — Research & draft (before touching any files)

### 1. Gather changes since last release
Run this from an up-to-date `develop`, since `HEAD` ends the range (for a hotfix,
see _Hotfixes_ below):
```bash
git checkout develop && git pull
gh release list --limit 1 --json tagName --jq '.[0].tagName'   # find last release tag
git log <last-tag>..HEAD --oneline                              # all commits since
```

### 2. Look up PR and issue context
For every merge commit, extract the PR number and fetch its description. Skip the
previous release's "Merge v<version> back into develop" PR and the merge inside
it: they carry nothing new.
```bash
git log <last-tag>..HEAD --oneline --merges
gh pr view <number> --json title,body,labels
```

For every `#<number>` reference in commit messages, fetch the issue:
```bash
gh issue view <number> --json title,body,labels
```

### 3. Draft release notes
Using the commit list, PR descriptions, and issue context, draft the release notes following the _Writing Release Notes_ guide below, and write them to `release-<version>.md` in the repo root (gitignored; steps 6 and 10 read it). Run the `nz-english` skill on the draft, then present it to the developer for review and incorporate feedback before proceeding.

### 4. Recommend version number
Based on the changes, recommend a semver bump:
- **major** — breaking changes
- **minor** — new features or behaviour changes, fully backwards-compatible
- **patch** — bug fixes only

**Stop here. Get explicit confirmation of the release notes and version number before continuing.**

---

## Phase 2 — Publish (after confirmation)

### 5. Bump version on a release branch
Create `release/v<version>` off `develop`. Edit `__version__` in `src/paddock/__init__.py` directly (Hatch reads the version from there). Commit the file with `uv run git commit` and push the branch.

### 6. Open release PR
```bash
gh pr create --base main --title "Release v<version>" --body-file release-<version>.md
```
**Stop here. Wait for the user to confirm the PR is merged before continuing.**

### 7. Switch to `main`
```bash
git checkout main && git pull
```

### 8. Build
```bash
rm -rf dist
uv build
```
Artefacts land in `dist/`. Run from the repo root. Nothing under `dist/` is
tracked, so removing the whole directory is safe — and necessary: under zsh
`rm -f dist/*` aborts with `no matches found` when `dist/` is empty or absent,
and otherwise skips uv's `.gitignore`. `uv build` recreates both.

### 9. Tag and push
```bash
git tag -a <version> -m "Release <version>"
git push origin <version>
```
`<version>` must match `__version__` in `src/paddock/__init__.py`;
`pyproject.toml` declares the version dynamic and does not carry it.

### 10. Create GitHub release

**a. Append checksums to the release notes file:**
```bash
echo -e "\n# SHA256 Checksums" >> release-<version>.md
shasum -a 256 dist/phx_paddock-* >> release-<version>.md
```

**b. GPG-sign the document and each build artefact:**
```bash
GPG_KEY=$(git config user.email)
gpg --local-user "$GPG_KEY" --clearsign release-<version>.md   # → release-<version>.md.asc
for f in dist/phx_paddock-*; do gpg --local-user "$GPG_KEY" --detach-sign "$f"; done
# Creates dist/phx_paddock-*.sig alongside each artefact
```

**c. Build the release body** — concatenate the notes and the signed copy:
```
<contents of release-<version>.md>

---

````
<contents of release-<version>.md.asc>
````
```
Write this to `release-<version>-body.md`.

**d. Create the release and upload all artefacts:**
```bash
gh release create <version> dist/* \
  --title "Paddock v<version>" \
  --notes-file release-<version>-body.md
```
`dist/*` picks up the `.whl`, `.tar.gz`, and `.sig` files.

### 11. Upload to PyPI
```bash
# Publishes only if the keyring can supply the token
keyring get https://upload.pypi.org/legacy/ __token__ >/dev/null 2>&1 && \
  uv publish --username __token__
```
The token comes from the developer's keyring: `[tool.uv]` in `pyproject.toml`
sets `keyring-provider = "subprocess"`, so uv shells out to a `keyring`
executable on `PATH`. Run the check first — it exits non-zero when the keyring
cannot supply the token, and prints nothing either way. Never echo the token to
confirm it; that puts a live credential in the transcript.

**If the check fails, stop here** and ask the developer to set
`UV_PUBLISH_TOKEN` (which takes precedence over the keyring) and run the publish
themselves. You cannot export it into their shell, and discovering this by
running the upload means failing the release's one irreversible step. Once they
have published, carry on from step 12.

### 12. Merge `main` back into `develop`
Without this, `develop` keeps the old `__version__`, and the next release PR
conflicts with `main` on that line. Merge from a branch rather than opening a PR
with `main` as its head: `main` is protected, so conflicts can't be resolved
there.

First, merge on a branch, and check the exit code before going on:
```bash
git checkout develop && git pull && git checkout -b merge/v<version> && \
  git merge --no-ff --no-edit origin/main
```
If `git merge` exits non-zero, it stopped on conflicts (likeliest after a
hotfix). Resolve them on `merge/v<version>`, `git add` the resolved files, then
`uv run git commit --no-edit`, which keeps git's merge message rather than
opening an editor. Only once the merge is committed, push it and open the PR:
```bash
git push -u origin merge/v<version> && \
  gh pr create --base develop --title "Merge v<version> back into develop" \
  --body "Brings the v<version> release merge and version bump back into \`develop\`, so the next release branch starts from them."
```
Merge the PR with a merge commit, the only method the branch rulesets allow: a
squash would leave `main`'s commits out of `develop`'s history and bring the
conflict back.

**Stop here. Wait for the user to confirm the PR is merged before continuing.**

### 13. Clean up
```bash
rm -f release-<version>.md release-<version>.md.asc release-<version>-body.md
rm -rf dist
```
`-f` so a re-run does not fail on a file already removed. `dist` goes too — its
artefacts and `.sig` files are on the GitHub release and PyPI by now. To correct
a release afterwards, fetch those assets back with `gh release download
<version>`: a rebuilt wheel may not be byte-identical, so its checksums would
disagree with the published notes.

## Hotfixes

When a fix to the latest release can't wait for `develop`'s unreleased changes,
work from `main` throughout. Never check out `develop` until step 12, or its
unreleased work ends up in the hotfix:

1. Branch off an up-to-date `main` and commit the fix with `uv run git commit`
   (not the version bump yet):
   ```bash
   git checkout main && git pull
   git checkout -b hotfix/<topic>
   ```
   Push the branch.
2. Instead of step 1, find the last tag with
   `gh release list --limit 1 --json tagName --jq '.[0].tagName'` and gather
   commits with `git log <last-tag>..hotfix/<topic> --oneline`. Then run Phase 1
   steps 2–4, and get the notes and version (normally the next patch) confirmed.
3. Bump `__version__` on `hotfix/<topic>` as in step 5, commit with
   `uv run git commit` and push.
4. Open the PR from the hotfix branch explicitly, so `gh` can't pick up any other
   branch:
   ```bash
   gh pr create --base main --head hotfix/<topic> --title "Release v<version>" --body-file release-<version>.md
   ```
   **Stop here until the user confirms it is merged**, then continue from step 7.
   Step 12's back-merge brings the fix into `develop`.

---

## Writing Release Notes

### Structure
```markdown
# Paddock v<version>
<one-sentence summary of the release character>

> [!CAUTION]
> **Alpha software — here be dragons**
> This is an early release. APIs, configuration formats, and CLI flags may change without notice in future versions. Bugs and crashes are possible.

> [!WARNING]
> **Breaking changes**
> - {what changed}
>   - {migration instructions}
>   - {error you'll see if you don't migrate}

## New features
## Enhancements
## Bug fixes

> [!NOTE]
> **Verifying release artefacts**
> 1. Import the signing key: `curl https://github.com/todofixthis.gpg | gpg --import`
> 2. Download the `.whl` or `.tar.gz` and its matching `.sig` file from the release assets
> 3. Verify: `gpg --verify phx_paddock-<version>-py3-none-any.whl.sig phx_paddock-<version>-py3-none-any.whl`
>
> Key fingerprint: `457997A2A506270F918D7BD1925CC6E316680401`

# SHA256 Checksums
```

Only include the `[!CAUTION]` block for pre-1.0 / alpha releases. Only include the `[!WARNING]` block if there are breaking changes. Omit any section that has no entries.

### Grouping related items
- **2–4 related bullets:** nest as a hierarchical sublist under the parent bullet
- **5+ related bullets:** promote to a `###` subheading within the section

### Content filter

**Always include**
- New capabilities developers can use
- Architectural decisions
- Behaviour changes
- Breaking changes

**Usually omit**
- Technical details of how something works internally
- Configuration consolidation (unless it changes developer-facing behaviour)
- Code organisation changes
- Dependency updates (include only if resolving a critical or high-severity vulnerability)
- Improvements to coding agent instructions

**Always omit**
- Formatting, linting, minor refactoring
- Test coverage updates

### Breaking changes alert
```markdown
> [!WARNING]
> **Breaking changes**
> - `SomeClass.old_method()` removed
>   - Replace with `SomeClass.new_method()`
>   - You'll know you need to migrate if you see: `AttributeError: 'SomeClass' object has no attribute 'old_method'`
```
