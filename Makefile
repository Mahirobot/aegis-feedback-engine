.PHONY: install run test clean

install:
	pip install -r requirements.txt

run:
	uvicorn app.main:app --reload

test:
	pytest tests/ -v

clean:
	rm -f feedback.db
	rm -rf __pycache__