# Teardown Scripts

Pre-defined teardown scripts for post-test cleanup and environment reset.

These scripts run **after** test execution completes, regardless of test outcome.
They follow industry best practices for test teardown:

| Script | Purpose |
|--------|---------|
| `cleanup_temp_files.py` | Remove `__pycache__`, `.pytest_cache`, temp files |
| `archive_test_logs.py` | Archive reports to timestamped backup directory |
| `reset_test_database.py` | Clean up test-specific database files |
| `generate_summary.py` | Print pass/fail summary from latest report |

## Usage

These scripts can be used as templates when creating teardown configurations
in the UI. Click a script name under "Quick Templates" to pre-fill the form.

## Custom Scripts

Add your own `.py` scripts to this directory. They will appear automatically
in the teardown configuration UI. Scripts should:

1. Print progress messages prefixed with a tag (e.g., `[Cleanup]`)
2. Print a final `PASSED` or `FAILED` status line
3. Return exit code 0 on success, non-zero on failure
4. Default `on_failure` for teardown steps is `continue` (best practice:
   teardown should complete all steps even if some fail)
