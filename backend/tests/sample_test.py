def test_sample_success():
    assert 1 + 1 == 2


def test_sample_failure():
    assert "hello".upper() == "HELLO"


def test_another_success():
    assert len("test") == 4


def test_math_operations():
    assert 2 * 3 == 6


def test_string_manipulation():
    assert "world".startswith("w")
