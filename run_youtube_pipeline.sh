#!/bin/bash

# Run the full YouTube Feedback backend pipeline
# Fetches new videos/transcripts and then analyzes them.
# Ensure the virtual environment is activated or Python executable is specified directly.

# Use Heroku's Python directly or specify path if needed locally
# e.g., PYTHON_EXEC=".venv/bin/python"
PYTHON_EXEC="python"

echo "================================================="
echo "Starting YouTube Feedback Pipeline Run: $(date)"
echo "================================================="

echo "\
--- Running YouTube Fetcher --- (Using default max-age-days: 7)"
"$PYTHON_EXEC" -m scripts.youtube_fetcher
FETCH_EXIT_CODE=$?
if [ $FETCH_EXIT_CODE -ne 0 ]; then
    echo "ERROR: YouTube Fetcher failed with exit code $FETCH_EXIT_CODE. Stopping pipeline."
    exit $FETCH_EXIT_CODE
fi

echo "\
--- Running YouTube Analyzer Worker ---"
"$PYTHON_EXEC" -m scripts.youtube_analyzer_worker
ANALYZE_EXIT_CODE=$?
if [ $ANALYZE_EXIT_CODE -ne 0 ]; then
    echo "ERROR: YouTube Analyzer failed with exit code $ANALYZE_EXIT_CODE. Stopping pipeline."
    exit $ANALYZE_EXIT_CODE
fi

echo "====================================================="
echo "YouTube Feedback Pipeline Run Finished Successfully: $(date)"
echo "====================================================="
exit 0 