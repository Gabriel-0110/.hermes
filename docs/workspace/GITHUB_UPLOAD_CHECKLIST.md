# GitHub Upload Checklist

## 1) Review what will be committed

- `git status --short`
- Confirm only intended source/docs/config-template files are listed.

## 2) Spot-check secret safety

Search staged files for accidental credentials:

- `git diff --cached`
- Ensure no real API keys, tokens, passwords, or webhook secrets are present.

## 3) Make initial commit

- `git add .`
- `git commit -m "chore: organize workspace for GitHub upload"`

## 4) Connect remote and push

- `git remote add origin <your-repo-url>`
- `git push -u origin main`

## 5) Optional post-push hardening

- Enable GitHub secret scanning and push protection
- Add branch protection rules for `main`
- Add CI checks for lint/tests as needed
