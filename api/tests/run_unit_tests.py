#!/usr/bin/env python
"""
Quick test runner for unit tests only.
Runs without database or external dependencies.

Usage:
    python run_unit_tests.py              # Run all unit tests
    python run_unit_tests.py -v           # Verbose output
    python run_unit_tests.py --cov        # With coverage report
"""
import sys
import subprocess


def main():
    """
    Runs the project's unit test suite using pytest.

    The function builds a command line invoking `pytest` on the `tests/` directory with verbose output,
    selection of tests marked as `unit`, and a short traceback format. If the script was called
    with the `--cov` flag, additional arguments are appended to enable coverage measurement for the
    `app` package, produce a terminal report showing missing lines, and generate an HTML coverage
    report.

    The constructed command is executed via :func:`subprocess.run`. The process exit code from pytest
    is then used as this script's exit status by calling `sys.exit` with that return code. No value is
    returned.
    """
    args = [
        "pytest",
        "tests/",
        "-v",
        "-m",
        "unit",  # Only unit tests
        "--tb=short",  # Short traceback format
    ]

    # Add coverage if requested
    if "--cov" in sys.argv:
        args.extend(
            [
                "--cov=app",
                "--cov-report=term-missing",
                "--cov-report=html",
            ]
        )

    # Run pytest
    result = subprocess.run(args)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
