---
name: pr-review
description: Review a GitHub PR and post the review as a comment. Reads a PAT from /workspace/.github_pat. Uses native `gh` CLI only (no extensions). Bypasses opencode's `$()`-in-tool-call hang by keeping all command substitution inside pre-shipped scripts.
license: MIT
metadata:
  version: "0.1.0"
---

# pr-review

Review a GitHub PR end-to-end: fetch metadata + diff, generate a review, post it as a comment.

## When to use

The user asks something like "review PR #42 in owner/repo" or "review pr 322". You can ALSO be given just a PR number when the repo is implicit from the persona.

## Prerequisites

- A GitHub PAT (fine-grained, scoped to the target repo) at `/workspace/.github_pat`
- The PAT must have **read** access to Contents + Pull requests, and **write** access to Pull requests (so the review can be posted as a comment)
- The `gh` CLI is pre-installed in the AgentMint box (verified)

## Step-by-step

**Step 1 — fetch PR data (one bash tool call):**

```
bash /workspace/home/pr-review/fetch.sh <OWNER>/<REPO> <PR_NUMBER>
```

The script prints: PR title, author, body, files changed, additions/deletions, and the full unified diff. All output goes to stdout; capture and read it.

**Step 2 — read and reason.** Identify concrete issues: bugs, missing tests, unclear naming, security risks, style problems, scope creep. Be specific. Reference exact lines and files where possible.

**Step 3 — write your review to disk** (use the **file write tool**, not a bash heredoc — opencode's bash dispatch hangs on `$()` in tool calls):

```
write_file /workspace/home/pr-review/review-out.md
```

Content: a brief markdown review (≤500 words). Lead with summary + verdict (LGTM / approve-with-nits / changes-requested). Then bulleted findings.

**Step 4 — post the review as a PR comment (one bash tool call):**

```
bash /workspace/home/pr-review/post.sh <OWNER>/<REPO> <PR_NUMBER>
```

The script reads `/workspace/home/pr-review/review-out.md` and posts it via `gh pr comment`. It prints the URL of the posted comment on success.

**Step 5 — report.** Tell the user: PR reviewed, link to the posted comment, one-line summary of your findings.

## Why pre-shipped scripts (not inline commands)

opencode's bash-tool dispatcher hangs (~5 min, then completes with empty output) when the model's tool call contains `$(...)` command substitution reading from a workspace file. By keeping all `$(cat /workspace/.github_pat)` inside scripts that you invoke via `bash <path>`, the model's emitted command has no `$()` — opencode dispatches it cleanly. See `scripts/fetch.sh` and `scripts/post.sh` for the actual gh invocations.

## Provisioning

The two scripts must exist at `/workspace/home/pr-review/`. AgentMint operators install this skill either:

- via `agent.create` with `skills: ["mesutcelik/agentmint-skills/pr-review"]` (preferred), or
- via `init_command` that writes the scripts directly (fallback when skill cloning isn't wired in)

See `scripts/install.sh` for the exact provisioning logic — copies `fetch.sh` + `post.sh` into the agent's workspace.

## Never echo the PAT

The PAT is read into a shell variable inside each script and passed to `gh` via env var. It is never printed to stdout. If `gh auth status` would print a redacted token, that's fine — it's already masked. Do not `cat` `/workspace/.github_pat`, do not echo `$GH_TOKEN`, do not include the PAT in the review text.
