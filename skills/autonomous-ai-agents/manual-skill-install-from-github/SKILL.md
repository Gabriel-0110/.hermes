---
name: manual-skill-install-from-github
description: Install a Hermes/OpenClaw-style skill directly from a GitHub repository when registry/tap discovery fails or the skill is missing from local installation. Covers verifying installed skills, cloning the repo, locating skill folders, copying them into ~/.hermes/skills, and validating with skill_view.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [skills, github, installation, hermes, troubleshooting]
---

# Manual Skill Install from GitHub

Use this when:
- The user provides a GitHub repo containing skills
- `hermes skills search` does not find the desired skill
- A repo tap is added successfully, but the target skill still does not appear
- A specific skill is missing locally and needs to be installed without waiting on registry indexing

## Workflow

1. Check current installed skills:
   ```bash
   hermes skills list
   ```

2. Clone the source repo to a temp directory:
   ```bash
   git clone --depth 1 <repo-url> <temp-dir>
   ```

3. Inspect the repo layout and confirm the target skill folder exists. Common pattern:
   ```
   skills/<skill-name>/SKILL.md
   ```

4. Read the repo README and target `SKILL.md` to verify:
   - exact skill name
   - whether it requires linked files like `references/`
   - any auth/setup notes

5. If useful, add the repo as a tap anyway:
   ```bash
   hermes skills tap add <repo-url>
   hermes skills tap list
   ```
   But do not rely on tap search succeeding.

6. If discovery still fails, install manually by copying the full skill directory into Hermes local skills:
   ```bash
   mkdir -p ~/.hermes/skills/<skill-name>
   cp -R <cloned-repo>/skills/<skill-name>/. ~/.hermes/skills/<skill-name>/
   ```

7. Verify installation in two ways:
   ```bash
   hermes skills list
   ```
   and load it directly:
   ```text
   skill_view("<skill-name>")
   ```

## Important Findings

- A GitHub repo can be a valid skills source and still fail to appear in `hermes skills search` after `hermes skills tap add`.
- Even when a skill appears in `hermes skills search`, the installable identifier may be a full hub path like:
  - `skills-sh/obra/superpowers/writing-plans`
  - `skills-sh/browser-use/browser-use/browser-use`
  - `skills-sh/vercel-labs/agent-browser/agent-browser`
  - `skills-sh/anthropics/skills/skill-creator`
- Community skills may be blocked by Hermes's scanner unless installed with:
  ```bash
  hermes skills install --yes --force <identifier>
  ```
  This is especially common for skills that explicitly allow shell-capable tools.
- Trusted skills may still produce `CAUTION` verdicts, but Hermes can allow them without `--force`; `--yes` is still needed for non-interactive installs.
- GitHub-backed fetches can fail with unauthenticated API rate limiting (`60 requests/hour`). If Hermes reports:
  ```text
  Hint: GitHub API rate limit exhausted (unauthenticated: 60 requests/hour)
  ```
  either set `GITHUB_TOKEN` / authenticate `gh`, or bypass the hub fetch and install manually from git.
- In that case, manual installation by copying the skill folder into `~/.hermes/skills/<skill-name>` works reliably.
- Prefer sparse checkout for large repos when only a few skills are needed:
  ```bash
  git clone --depth 1 --filter=blob:none --sparse <repo-url> repo
  cd repo
  git sparse-checkout set skills/<skill-name>
  ```
- Preserve the entire skill directory, not just `SKILL.md`, because linked files such as `references/`, `templates/`, scripts, or assets may be required.
- After manual install, Hermes shows the skill as `local` rather than hub-installed.
- Some manually installed skills may duplicate builtin ones by name. Verify by checking both the filesystem and `hermes skills list`; Hermes may still prefer listing the builtin copy first.

## Example: BitMart Repo

For `https://github.com/bitmartexchange/bitmart-skills`, the layout is:
```text
skills/bitmart-wallet-ai/
skills/bitmart-exchange-spot/
skills/bitmart-exchange-futures/
```

When `bitmart-wallet-ai` was missing locally and tap search returned no results, the successful fix was:
```bash
mkdir -p ~/.hermes/skills/bitmart-wallet-ai
cp -R <clone>/skills/bitmart-wallet-ai/. ~/.hermes/skills/bitmart-wallet-ai/
```

Then verify with:
```bash
hermes skills list
```
and
```text
skill_view("bitmart-wallet-ai")
```

## Pitfalls

- Do not assume `hermes skills tap add` means the skill will become searchable immediately.
- Do not copy only `SKILL.md`; include all supporting files.
- Do not claim installation succeeded until both the CLI list and `skill_view()` succeed.
