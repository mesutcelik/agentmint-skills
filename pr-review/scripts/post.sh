#!/bin/sh
# Post the agent's review markdown as a PR comment.
# Usage: post.sh OWNER/REPO PR_NUMBER
set -e
REPO="$1"; PR="$2"
if [ -z "$REPO" ] || [ -z "$PR" ]; then
  echo "usage: post.sh OWNER/REPO PR_NUMBER" >&2
  exit 2
fi
REVIEW=/workspace/home/pr-review/review-out.md
if [ ! -s "$REVIEW" ]; then
  echo "ERROR: $REVIEW missing or empty — generate the review first" >&2
  exit 3
fi

GH_TOKEN=$(cat /workspace/.github_pat)
export GH_TOKEN

# Use `gh pr comment` (general PR comment) rather than `gh pr review` so we
# don't require approval/changes-requested status — this is a conversational
# review delivered as a single comment.
URL=$(gh pr comment "$PR" --repo "$REPO" --body-file "$REVIEW")
echo "Posted to: $URL"
