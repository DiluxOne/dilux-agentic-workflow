include dx.mk

# `make pre-pr` runs what the pull request and the merge queue run, in their
# order: verify.yml, then mutations.yml, then the behavioural layer, then the
# organisation's checks (dx.mk). Every line runs under `bash -euo pipefail` and
# the targets never in parallel, so the first failure stops it there.
#
# Left to CI, and said here so nobody reads them as forgotten: the mutation
# slice of the change (`--changed`: one full run of the suite per fault, over
# two hours on one machine for a change to the validators, which no
# autopilot run fits; mutations.yml runs it in 96 shards, required before a
# merge, #78) and the kill map (472 complete runs of the suite, about 2.5
# hours on one machine; mutations.yml says why). Here, the anchors and the
# cover, which take seconds.
SHELL := bash
.SHELLFLAGS := -euo pipefail -c
.NOTPARALLEL:

# What a pull request is diffed against: its base branch.
BASE ?= origin/main
MODEL ?= opencode/claude-sonnet-5

.PHONY: verify mutations behavioral
pre-pr: verify mutations behavioral

verify:
	python3 scripts/lint_method.py
	python3 scripts/check_versions.py --since "$(BASE)"
	python3 scripts/check_commits.py --since "$(BASE)"
	python3 evals/runner.py --repo . --offline
	python3 evals/runner.py --repo . --offline --control
	python3 scripts/lint_kill_map.py --repo .
	bash scripts/verify_install.sh

mutations:
	python3 scripts/mutate.py --check-anchors
	python3 scripts/mutate.py --cover .github/workflows/mutations.yml

# The layer that needs a model (behavioral.yml, run on demand there). Without
# a key or the CLI it measures nothing, so it says so and is not counted.
behavioral:
	@if [ -z "$${OPENCODE_API_KEY:-}" ] || ! command -v opencode >/dev/null; then \
	  echo "behavioral: skipped, no model configured (OPENCODE_API_KEY and the opencode CLI); behavioral.yml runs it on demand"; \
	else \
	  python3 evals/runner.py --repo . --kinds behavioral --agent opencode --model "$(MODEL)"; \
	  python3 evals/runner.py --repo . --kinds behavioral --agent opencode --model "$(MODEL)" --control; \
	fi
