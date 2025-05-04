#!/bin/bash

# Run the full Steam Review backend pipeline
# Ensure the virtual environment is activated or Python executable is specified directly.

# Get the directory where the script resides
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$SCRIPT_DIR"
PYTHON_EXEC="$PROJECT_ROOT/.venv/bin/python"

echo "Starting Steam Review Pipeline Run: $(date)"

# Activate virtual environment if needed (alternative)
# source "$PROJECT_ROOT/.venv/bin/activate"

# Check if Python executable exists
if [ ! -f "$PYTHON_EXEC" ]; then
    echo "Error: Python executable not found at $PYTHON_EXEC"
    echo "Please ensure the virtual environment exists and is named .venv"
    exit 1
fi

echo "\
--- Running Fetcher ---"
"$PYTHON_EXEC" -m src.main_fetcher
FETCH_EXIT_CODE=$?
if [ $FETCH_EXIT_CODE -ne 0 ]; then
    echo "Fetcher failed with exit code $FETCH_EXIT_CODE. Stopping pipeline."
    exit $FETCH_EXIT_CODE
fi

echo "\
--- Running Translator ---"
"$PYTHON_EXEC" -m src.run_translator
TRANSLATE_EXIT_CODE=$?
if [ $TRANSLATE_EXIT_CODE -ne 0 ]; then
    echo "Translator failed with exit code $TRANSLATE_EXIT_CODE. Stopping pipeline."
    exit $TRANSLATE_EXIT_CODE
fi

echo "\
--- Running Analyzer ---"
"$PYTHON_EXEC" -m src.run_analyzer
ANALYZE_EXIT_CODE=$?
if [ $ANALYZE_EXIT_CODE -ne 0 ]; then
    echo "Analyzer failed with exit code $ANALYZE_EXIT_CODE. Stopping pipeline."
    exit $ANALYZE_EXIT_CODE
fi

echo "\
Steam Review Pipeline Run Finished Successfully: $(date)"
exit 0 