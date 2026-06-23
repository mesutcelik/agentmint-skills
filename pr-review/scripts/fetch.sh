#!/bin/sh
# Fetch PR metadata + full diff. Output goes to stdout; the agent reads it.
# Usage: fetch.sh OWNER/REPO PR_NUMBER
set -e
REPO="$1"; PR="$2"
if [ -z "$REPO" ] || [ -z "$PR" ]; then
  echo "usage: fetch.sh OWNER/REPO PR_NUMBER" >&2
  exit 2
fi
GH_TOKEN=$(cat /workspace/.github_pat)
export GH_TOKEN

echo "=== PR #$PR on $REPO ==="
gh pr view "$PR" --repo "$REPO" \
  --json title,author,body,baseRefName,headRefName,additions,deletions,changedFiles,state,mergeable \
  --template '{{.title}}
Author: {{.author.login}}    State: {{.state}}    Mergeable: {{.mergeable}}
Base: {{.baseRefName}} <- Head: {{.headRefName}}
Files: {{.changedFiles}} changed (+{{.additions}}/-{{.deletions}})

Body:
{{.body}}

'

echo "=== DIFF ==="
gh pr diff "$PR" --repo "$REPO"
