#!/bin/bash
# Claim a step of the build plan, so no one else starts it.
#
#   scripts/claim-step.sh 12      claim Prompt 12
#
# A step is claimed by the existence of its branch on GitHub. The branch name
# for each step is fixed in docs/BUILD-PLAN.md's status table, so everyone
# claiming a step pushes to the same branch, and GitHub accepts only the
# first push. This script reads the table from origin/main, refuses a step
# that is done, waiting on the author, or already claimed, then creates the
# branch, marks the step "Claimed", commits, and pushes without force.
# Open a draft pull request for the branch straight afterwards.
# See "Claiming a step" in docs/BUILD-PLAN.md. Written for macOS's bash 3.2.

set -euo pipefail

cd "$(dirname "$0")/.."
PLAN="docs/BUILD-PLAN.md"

if [ $# -ne 1 ] || [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    sed -n '2,13p' "$0"
    [ $# -eq 1 ] && exit 0
    exit 2
fi
STEP="$1"
case "$STEP" in
    ''|*[!0-9]*) echo "The step must be a number, such as 12." >&2; exit 2 ;;
esac

fail() { echo "$1" >&2; exit 1; }

if [ -n "$(git status --porcelain)" ]; then
    fail "Commit or stash your changes first; claiming switches branches."
fi

git fetch --quiet origin main

# The status table row for this step, as it stands on main:
# | # | Step | Status | Branch | Commit or PR |
ROW="$(git show origin/main:"$PLAN" | grep -E "^\| ${STEP} \|" || true)"
[ -n "$ROW" ] || fail "There is no Prompt $STEP in the status table on main."

cell() { printf '%s\n' "$ROW" | awk -F'|' -v n="$1" '{ gsub(/^ +| +$/, "", $n); print $n }'; }
TITLE="$(cell 3)"
STATUS="$(cell 4)"
BRANCH="$(cell 5 | tr -d '`')"

case "$STATUS" in
    Done*) fail "Prompt $STEP is already done: $STATUS." ;;
    Waiting*) fail "Prompt $STEP is waiting on the author: $STATUS. Once the author has supplied what it needs, change its status on main first." ;;
    Claimed*) fail "Prompt $STEP is already claimed on main: $STATUS." ;;
esac
[ -n "$BRANCH" ] || fail "Prompt $STEP has no branch named in the status table."

if git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; then
    fail "Prompt $STEP is claimed: the branch $BRANCH already exists on GitHub. Do not work on it."
fi
if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
    fail "A local branch $BRANCH already exists but is not on GitHub. Delete it or push it yourself."
fi

ORIGINAL="$(git rev-parse --abbrev-ref HEAD)"
git switch --quiet -c "$BRANCH" origin/main

# Mark the step claimed in this branch's copy of the table.
awk -v step="$STEP" 'BEGIN { FS = OFS = "|" }
    $0 ~ "^\\| " step " \\|" { $4 = " Claimed "; print; next }
    { print }' "$PLAN" > "$PLAN.tmp"
mv "$PLAN.tmp" "$PLAN"

CLAIMANT="$(git config user.name || echo unknown) on $(hostname)"
git commit --quiet -am "Claim Prompt $STEP: $TITLE" -m "Claimed-by: $CLAIMANT"

if ! git push --quiet -u origin "$BRANCH"; then
    git switch --quiet "$ORIGINAL"
    git branch --quiet -D "$BRANCH"
    if git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; then
        fail "Someone else claimed Prompt $STEP first: $BRANCH now exists on GitHub. Do not work on it."
    fi
    fail "The push to $BRANCH failed and the step is still unclaimed. Try again."
fi

echo "Claimed Prompt $STEP on $BRANCH."
echo "Now open a draft pull request for $BRANCH against main, titled"
echo "  Prompt $STEP: $TITLE"
echo "following .github/pull_request_template.md."
