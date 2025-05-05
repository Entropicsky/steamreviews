# Technical Specification: Excel Report Generation Parallelization

**Date:** 2024-05-05

**Authors:** Gemini

**Status:** Proposed

## 1. Introduction

The current Excel report generation process in the Streamlit application (`streamlit_app.py` calling `src.reporting.excel_generator.generate_summary_report`) experiences significant latency due to sequential calls to the OpenAI API for summarizing reviews for each language and an overall summary. This specification outlines the plan to parallelize these API calls using Python's `asyncio` library to improve the responsiveness of the report generation feature from the user's perspective.

## 2. Goals

*   Reduce the wall-clock time required to generate the Excel report by executing independent LLM API calls concurrently.
*   Maintain the existing report structure and content.
*   Minimize architectural changes, focusing primarily on the `src.reporting.excel_generator` module.
*   Ensure robust error handling within the asynchronous execution flow.

## 3. Non-Goals

*   Moving summary generation to a background scheduled task (This is a potential future step if parallelization is insufficient).
*   Changing the database schema or adding new tables.
*   Altering the core data fetching logic from the database.

## 4. Proposed Solution

The primary change involves refactoring the `generate_summary_report` function in `src/reporting/excel_generator.py` to leverage `asyncio`.

### 4.1. OpenAI Client (`src.openai_client`)

*   **Verify/Implement Async Support:** Ensure the `OpenAIClient` class and its core method (e.g., `get_llm_summary`) support asynchronous execution. The underlying `httpx` library used by the `openai` package supports `async`, so this likely involves:
    *   Defining an `async def` version of the primary method (e.g., `aget_llm_summary`).
    *   Using an `async with openai.AsyncClient(...)` context or equivalent async client initialization.
*   **Error Handling:** Ensure exceptions during async API calls are caught and handled appropriately.

### 4.2. Excel Generator (`src.reporting.excel_generator`)

*   **Convert `generate_summary_report` to `async def`:** The main function needs to become an async function to use `await`.
*   **Identify Independent Tasks:** The LLM calls for each language summary and the overall summary are the independent tasks suitable for parallelization.
*   **Gather Coroutines:**
    *   Iterate through the grouped languages.
    *   For each language, create a coroutine by calling the async OpenAI client method (`await openai_client.aget_llm_summary(...)`) to generate the summary. Store these coroutines in a list.
    *   Create a separate coroutine for the overall summary.
*   **Execute Concurrently using `asyncio.gather`:**
    *   Use `asyncio.gather(*summary_tasks, return_exceptions=True)` to run all the summary generation coroutines concurrently. `return_exceptions=True` is crucial for handling potential failures in individual API calls without stopping the entire process.
*   **Process Results:**
    *   Iterate through the results returned by `asyncio.gather`.
    *   Check if each result is an exception or a successful summary.
    *   Handle failed calls gracefully (e.g., log the error, potentially add a note to the corresponding Excel sheet).
    *   Process successful summaries and Pydantic validation as before.
*   **Excel Writing:** The writing to the `BytesIO` object using `pandas.ExcelWriter` does not need to be async itself, as it's CPU/memory bound, not I/O bound in the same way as network calls. This can happen sequentially after all summaries are gathered.

### 4.3. Streamlit Application (`streamlit_app.py`)

*   **Calling the Async Function:** Streamlit runs in its own event loop. Directly calling `await generate_summary_report(...)` might not work as expected. The standard way to run an async function from sync code (like a Streamlit button handler) is using `asyncio.run()`.
*   **Implementation:** Modify the button handler:
    ```python
    import asyncio
    # ... other imports

    if st.button("Generate & Download Excel Report", key="generate_button"):
        # ... setup code ...
        try:
            with st.spinner("Generating report..."):
                # Run the async function using asyncio.run()
                report_bytes = asyncio.run(generate_summary_report(selected_app_id, start_timestamp))
            
            st.success("Report generated successfully!")
            # ... download button logic ...
        except Exception as e:
            # ... error handling ...
    ```

## 5. Testing Strategy

*   **Unit Tests:**
    *   Add/update tests for the async OpenAI client method (mocking `httpx` or the `openai.AsyncClient`).
    *   Add tests for the refactored `generate_summary_report`, mocking the OpenAI client and verifying that `asyncio.gather` is called and results (including exceptions) are processed correctly.
*   **Integration Tests:**
    *   Run the `generate_summary_report` function locally (outside Streamlit) against a test database (or mocked data) and potentially mock the LLM calls, measuring the execution time compared to the sequential version.
    *   Test the error handling for failed individual LLM calls.
*   **Manual Tests:**
    *   Run the Streamlit app locally.
    *   Generate reports for apps with varying numbers of languages.
    *   Verify the generated Excel file content is correct.
    *   Observe the perceived speed improvement in the UI.
    *   Test scenarios where LLM calls might fail.

## 6. Rollback Plan

*   Revert the changes to `src/reporting/excel_generator.py`, `src/openai_client.py`, and `streamlit_app.py` using Git version control. The changes are relatively contained, making rollback straightforward.

## 7. Future Considerations

*   If parallelization does not provide sufficient performance improvement, the next step would be to implement the background pre-generation architecture discussed previously, storing summaries in the database. 