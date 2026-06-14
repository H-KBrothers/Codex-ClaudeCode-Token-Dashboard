# GitHub Repository Settings

Recommended settings for publishing this H&K Brothers tool.

## Repository

- Repository name: `Codex-ClaudeCode-Token-Dashboard`
- Owner: `H-KBrothers`
- Visibility: `Private` while iterating, then `Public` when ready to share
- Description: `Local-first usage analytics dashboard for Codex and Claude Code with token, cost, project, session, and cache insights.`
- Website: leave empty unless H&K Brothers has a product page

## Topics

```text
codex
claude-code
ai-tools
developer-tools
token-usage
usage-analytics
local-first
dashboard
python
vanilla-js
sqlite
```

## Features

- Enable Issues: yes
- Enable Projects: optional
- Enable Wiki: no
- Enable Discussions: no for now
- Allow forking: optional
- Sponsorships: no

## Pull Requests

- Allow merge commits: no
- Allow squash merging: yes
- Allow rebase merging: yes
- Always suggest updating pull request branches: yes
- Automatically delete head branches: yes

## Branch Protection

Protect `main` once the repo is pushed:

- Require a pull request before merging
- Require status checks before merging
- Require branches to be up to date before merging
- Require conversation resolution before merging
- Do not allow force pushes
- Do not allow deletions

Suggested required check name after CI is added:

```text
tests
```
