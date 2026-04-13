# Contributing to Distributed Verification Platform

Thank you for your interest in contributing! This document provides guidelines and instructions for contributing to the project.

## Code of Conduct

Please read and follow our [Code of Conduct](CODE_OF_CONDUCT.md) to ensure a respectful and inclusive community.

## Getting Started

### Prerequisites
- Python >= 3.11
- Node.js >= 16
- PostgreSQL (optional, SQLite works for local dev)
- Docker (optional, for containerized development)

### Development Setup

1. **Fork and clone the repository**
   ```bash
   git clone https://github.com/YOUR_USERNAME/DistributedVerificationPlatform.git
   cd DistributedVerificationPlatform
   ```

2. **Set up Python backend**
   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -e .
   ```

3. **Set up Node frontend**
   ```bash
   cd frontend
   npm install
   ```

4. **Configure environment**
   ```bash
   cp backend/.env.example backend/.env
   # Edit DATABASE_URL if needed (defaults to SQLite for local dev)
   ```

## Development Workflow

### Creating a Feature Branch
```bash
git checkout -b feature/your-feature-name
```

### Running Tests

**Backend tests:**
```bash
cd backend
pytest tests/ -v
```

**Run specific test suite:**
```bash
pytest tests/regression/ -v          # Regression tests
pytest tests/unit/ -v                # Unit tests
pytest tests/smoke/ -v               # Smoke tests
```

**Frontend tests:**
```bash
cd frontend
npm test
```

### Starting Development Servers

**Backend (in separate terminal):**
```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Frontend (in separate terminal):**
```bash
cd frontend
npm run dev -- --host 0.0.0.0 --port 5173
```

### Code Style Guidelines

**Python:**
- Follow PEP 8
- Use type hints
- Write docstrings for functions and classes
- Max line length: 88 characters

**TypeScript/React:**
- Use strict TypeScript mode
- Follow ESLint configuration
- Use meaningful component names
- Prefer functional components

### Commit Guidelines

- Write clear, descriptive commit messages
- Use present tense: "Add feature" not "Added feature"
- Reference issues: "Fix #123"
- Keep commits atomic and focused

Example:
```
feat: add distributed test execution queue

- Implement FIFO queue manager for test execution
- Add resource locking mechanism
- Support concurrent test runs from multiple clients

Fixes #45
```

## Pull Request Process

1. **Update your fork**
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Push to your branch**
   ```bash
   git push origin feature/your-feature-name
   ```

3. **Open a Pull Request**
   - Use the provided PR template
   - Describe what your changes do
   - Reference related issues
   - Include screenshots for UI changes

4. **PR Requirements**
   - All tests must pass
   - Code must follow style guidelines
   - Documentation should be updated
   - No merge conflicts

5. **Review Process**
   - Maintainers will review your PR
   - Respond to feedback and suggestions
   - Update your branch as needed
   - PRs are merged once approved

## Reporting Issues

### Bug Reports
Include:
- Clear description of the issue
- Steps to reproduce
- Expected vs actual behavior
- Python/Node.js versions
- OS and environment details
- Stack trace or error logs

### Feature Requests
Include:
- Clear use case
- Potential implementation approach
- Why this feature is valuable
- Any related issues or discussions

## Documentation

- Update README.md if changing user-facing behavior
- Add docstrings to new functions and classes
- Include examples for new features
- Update architecture diagrams if needed

## Testing Requirements

- Add tests for all new features
- Ensure all existing tests pass
- Aim for > 80% code coverage
- Include both unit and integration tests

## Release Process

Releases follow semantic versioning (MAJOR.MINOR.PATCH):
- MAJOR: Breaking changes
- MINOR: New features
- PATCH: Bug fixes

See [CHANGELOG.md](CHANGELOG.md) for version history.

## Questions?

- Open a GitHub discussion
- Check existing issues for similar questions
- Review architecture diagrams in README.md
- Check API documentation at http://localhost:8000/docs

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

Thank you for contributing!
