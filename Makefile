# Define the virtual environment directory
VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: run test clean reset-db help

# 1. Run App (Auto-creates venv if missing)
run: $(VENV)/bin/activate
	@echo "Starting Aegis Engine..."
	@# Open browser in background (Mac: open, Linux: xdg-open)
	@((sleep 3 && (open http://127.0.0.1:8000 || xdg-open http://127.0.0.1:8000)) >/dev/null 2>&1 &)
	@$(PYTHON) -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# 2. Run Tests
test: $(VENV)/bin/activate
	@echo "Running Tests..."
	@$(PYTHON) -m pytest tests/ -v

# 3. Setup Virtual Environment (Implicit Target)
# This runs only if .venv doesn't exist OR requirements.txt is newer
$(VENV)/bin/activate: requirements.txt
	@echo "Creating virtual environment..."
	@python3 -m venv $(VENV)
	@echo "Installing dependencies..."
	@$(PIP) install -r requirements.txt
	@touch $(VENV)/bin/activate

# 4. Utilities
clean:
	@echo "Cleaning up..."
	@rm -rf __pycache__
	@find . -name "*.pyc" -delete
	@find . -name "__pycache__" -delete
	@rm -rf .pytest_cache
	@# Optional: Remove venv with 'make clean' if you want a full reset
	@# rm -rf $(VENV)

reset-db:
	@echo "Wiping Database..."
	@rm -f feedback.db