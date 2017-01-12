.PHONY: automatic-target
automatic-target:
	@echo "Nothing to build automatically!" >&2; exit 1

.PHONY: lint
lint:
	./scripts/lint.sh
