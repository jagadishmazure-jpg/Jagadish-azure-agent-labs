.PHONY: install lint test evals cards bicep secrets overlap fixtures
install:          ## venv + dev extras
	python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
lint:
	ruff check . && ruff format --check .
test:             ## every lab + shared layers (offline)
	pytest -q
evals:            ## all five eval gates (exit 1 on regression)
	python scripts/run_all_evals.py
cards:            ## regenerate control-plane/agent-cards
	python scripts/export_agent_cards.py
bicep:            ## compile every lab's infra (never deploys)
	for f in labs/*/infra/main.bicep; do bicep build $$f --stdout > /dev/null || exit 1; done
secrets:
	python scripts/secrets_scan.py
overlap:          ## originality check against local reference files (never committed)
	python scripts/overlap_check.py $(REFS)
fixtures:         ## regenerate synthetic data for every lab
	for d in labs/*/data/gen_fixtures.py; do python $$d; done
