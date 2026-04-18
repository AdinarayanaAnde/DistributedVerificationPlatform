# Setup Scripts

Pre-defined environment setup scripts that run before test execution.
Place Python scripts here and they will be available in the DVP Setup panel.

## Convention

- Scripts must be `.py` files
- Each script should be self-contained and idempotent
- Use `print()` for status output (captured in run logs)
- Exit code 0 = success, non-zero = failure
