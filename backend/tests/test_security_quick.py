"""Quick demo tests for DVF UI testing - Security checks."""
import time
import hashlib


def test_password_hashing():
    """Verify passwords are hashed, not stored in plain text."""
    time.sleep(1)
    password = "secret123"
    hashed = hashlib.sha256(password.encode()).hexdigest()
    assert hashed != password
    assert len(hashed) == 64


def test_sql_injection_prevention():
    """Verify user input is parameterized."""
    time.sleep(2)
    user_input = "'; DROP TABLE users; --"
    sanitized = user_input.replace("'", "''")
    assert "DROP TABLE" in sanitized  # still in string but safely escaped
    assert sanitized.startswith("''")


def test_cors_headers():
    """Verify CORS headers are set correctly."""
    time.sleep(1)
    headers = {
        "Access-Control-Allow-Origin": "https://dvf.example.com",
        "Access-Control-Allow-Methods": "GET, POST",
    }
    assert "*" not in headers["Access-Control-Allow-Origin"]


def test_token_expiration():
    """Verify expired tokens are rejected."""
    time.sleep(1)
    import time as t
    issued_at = t.time() - 7200  # 2 hours ago
    expires_in = 3600  # 1 hour
    is_expired = (t.time() - issued_at) > expires_in
    assert is_expired


def test_input_length_limits():
    """Verify oversized inputs are rejected."""
    time.sleep(1)
    max_length = 255
    user_input = "a" * 300
    is_valid = len(user_input) <= max_length
    assert not is_valid, "Oversized input should be rejected"
