#!/bin/sh
# Provision the pr-review scripts into the agent's writable workspace.
# Run from init_command at agent.create time when not using `skills: [...]`
# auto-installation.
set -e
DEST=/workspace/home/pr-review
mkdir -p "$DEST"
# When called via curl-pipe, scripts are fetched alongside this installer.
# When run from a cloned skill dir, copy local files.
SRC_DIR="${SKILL_DIR:-$(dirname "$(readlink -f "$0")")}"
cp "$SRC_DIR/fetch.sh" "$DEST/fetch.sh"
cp "$SRC_DIR/post.sh" "$DEST/post.sh"
chmod +x "$DEST/fetch.sh" "$DEST/post.sh"
echo "pr-review installed at $DEST"
