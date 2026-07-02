.PHONY: test test-quick clean lint

test:
	python3 -m pytest tests/ -v

test-quick:
	python3 -m pytest tests/ --tb=short -q

lint:
	python3 -m flake8 src/ tests/ || true

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete
