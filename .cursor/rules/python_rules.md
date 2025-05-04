# Python Development Rules

## Code Style
- Follow PEP 8 style guidelines
- Use 4 spaces for indentation
- Maximum line length: 88 characters (Black formatter standard)
- Use snake_case for variables and functions
- Use CamelCase for classes
- Use UPPER_CASE for constants

## Project Structure
- Use virtual environments for dependency management
- Maintain requirements.txt or pyproject.toml for dependencies
- Group related functionality into modules
- Use __init__.py to organize package hierarchy

## Documentation
- Document all functions, classes, and modules with docstrings
- Use type hints for function parameters and return values
- Include examples in docstrings for complex functions

## Testing
- Write unit tests for all non-trivial functions
- Use pytest for testing framework
- Aim for at least 80% code coverage
- Mock external API calls in tests

## Error Handling
- Use specific exception types when raising exceptions
- Handle exceptions at appropriate levels of abstraction
- Log errors with appropriate context
- Provide helpful error messages

## Imports
- Group imports in the following order:
  1. Standard library imports
  2. Third-party imports
  3. Local application imports
- Sort imports alphabetically within each group
- Use absolute imports rather than relative imports when possible 