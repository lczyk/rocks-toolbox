# The code is not ment to be importes, but lets check that it imports ot check
# for python-version-specific syntax errors.


def test_imports() -> None:
    import sys

    print(sys.path)
    import multi_apt_cache  # noqa: F401
