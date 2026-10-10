.PHONY: setup db run offline test clean down
setup:   ## install dependencies
	pip install -r requirements.txt
db:      ## start PostgreSQL in Docker
	docker compose up -d
run:     ## run pipeline against the live API
	python main.py
offline: ## run with bundled sample data (no internet)
	python main.py --offline
test:    ## run unit + integration tests
	python -m pytest -v
down:    ## stop database
	docker compose down
clean:
	rm -rf .pytest_cache __pycache__ */__pycache__ logs/*.log*
