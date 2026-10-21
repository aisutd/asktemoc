# Thin wrapper; the logic lives in scripts/dev.sh (Windows: scripts/dev.ps1).
.PHONY: setup seed api web test
setup seed api web test:
	@scripts/dev.sh $@
