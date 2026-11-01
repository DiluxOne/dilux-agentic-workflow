# Managed by DiluxOne/.github (scripts/sync-repos.py pre-pr, #479), from its kind's pack
# (kinds/<kind>/pack.yml `pre-pr-make`): do not edit it here, it is rewritten.
# `make pre-pr` is the one check before a pull request. This repository's
# Makefile includes it, and adds its own checks as prerequisites:
#   pre-pr: my-check
.PHONY: pre-pr
define DX_PRE_PR
central=$${DX_CENTRAL:-.dx-central}
test -f "$$central/scripts/agent-manifests.py" || { echo "pre-pr: DX_CENTRAL ($$central) is not a checkout of DiluxOne/.github" >&2; exit 1; }
python3 "$$central/scripts/agent-manifests.py" check .
php "$$central/scripts/review-rules.php" --kind ai-agent-plugin --repo .
endef
export DX_PRE_PR
pre-pr:
	@bash -euo pipefail -c "$$DX_PRE_PR"
