"""Pytest configuration for human-readable test names.

This conftest uses test function docstrings as display names in pytest output,
making test reports more readable and understandable.
"""


def pytest_collection_modifyitems(items):
    """
    Modify test items to use docstrings as human-readable names.
    
    For each test function, if it has a docstring, the first non-empty line
    of the docstring becomes the test name in reports. For parameterized tests,
    the parameter ID is preserved.
    """
    for item in items:
        doc = item.function.__doc__
        if doc:
            # Get the first non-empty line from the docstring
            summary = next(
                (line.strip() for line in doc.strip().splitlines() if line.strip()),
                None
            )
            if summary:
                if hasattr(item, "callspec"):
                    # For parameterized tests, preserve parameter id from the original nodeid
                    start = item.nodeid.find('[')
                    param_part = item.nodeid[start:] if start != -1 else ''
                    item._nodeid = summary + param_part
                else:
                    item._nodeid = summary
