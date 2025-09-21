# spellchecker: words subkey
from pathlib import Path

import pytest
from helpers import inline_yaml, kh

from src.chisel_releases_linter import KeyHunk, find_yaml_hunks_for_key


def test_key_hunk_parse_key() -> None:
    assert KeyHunk.parse_key("key: value") == "key"
    assert KeyHunk.parse_key("  key: value") == "key"
    assert KeyHunk.parse_key("key:") == "key"
    assert KeyHunk.parse_key("  key:") == "key"
    assert KeyHunk.parse_key("  : value") is None
    assert KeyHunk.parse_key("no_colon") is None
    assert KeyHunk.parse_key("  no_colon") is None
    assert KeyHunk.parse_key("key: value: with: colons") == "key"
    assert KeyHunk.parse_key("  key: value: with: colons") == "key"
    assert KeyHunk.parse_key("") is None
    assert KeyHunk.parse_key("   ") is None
    assert KeyHunk.parse_key("  - item in list") is None
    assert KeyHunk.parse_key("  - key: value in list") is None
    assert KeyHunk.parse_key("  # comment line") is None
    assert KeyHunk.parse_key("# comment line") is None
    assert KeyHunk.parse_key("  # key: value in comment") is None
    assert KeyHunk.parse_key("# key: value in comment") is None
    assert KeyHunk.parse_key("  # key: value: with: colons in comment") is None
    assert KeyHunk.parse_key("key: value # with a comment") == "key"
    assert KeyHunk.parse_key("key: { nested: map }") == "key"
    assert KeyHunk.parse_key("  key: { nested: map }") == "key"
    assert KeyHunk.parse_key("key: [ nested, list ]") == "key"
    assert KeyHunk.parse_key("  key: [ nested, list ]") == "key"


def test_key_hunk_basic() -> None:
    hunk = kh("""
    key1: value1
      subkey1: value2
      subkey2: value3
    """)
    assert hunk.key == "key1"
    assert hunk.lines == [
        "key1: value1",
        "  subkey1: value2",
        "  subkey2: value3",
    ]


def test_key_hunk_invalid() -> None:
    with pytest.raises(ValueError):
        kh(
            """
        # comment
        """,
        )

    with pytest.raises(ValueError):
        kh(
            """
          - item in list
          - another item
        """,
        )

    with pytest.raises(ValueError):
        kh(
            """
          - key: value in list
          - another item
        """,
        )

    # key must be in the first non-indented lines
    with pytest.raises(ValueError):
        kh(
            """
          # comment line
          # another comment
          - not a key
            key: value
        """,
        )


def test_find_yaml_hunks_for_key() -> None:
    results = find_yaml_hunks_for_key(
        inline_yaml("""
    key1:
        subkey1: value
        subkey2: value
    key2:
        subkey1: value
        subkey2: value
    key1:
        subkey1: value
        subkey2: value
    """),
        "key1",
    )
    assert len(results) == 2
    assert results[0] == kh(
        """
    key1:
        subkey1: value
        subkey2: value
    """,
    )
    assert results[1] == kh(
        """
    key1:
        subkey1: value
        subkey2: value
    """,
        start_line=7,
    )


def test_find_essential_keys(plucky_slices: list[Path]) -> None:
    for path in plucky_slices:
        contents = path.read_text()
        # _ = parse_yaml_to_hunks(contents)
        results = find_yaml_hunks_for_key(contents, "essential")

        # count how many times the word "essential:" appears in the file
        # as a poor proxy for how many essential keys should be found
        expected_count = 0
        for line in filter(
            lambda line: line and not line.startswith("#"),
            map(str.strip, contents.splitlines()),
        ):
            if "essential:" in line:
                expected_count += 1

        assert len(results) == expected_count, f"{path.name}: expected {expected_count}, got {len(results)}"


def test_find_contents_keys(plucky_slices: list[Path]) -> None:
    for path in plucky_slices:
        contents = path.read_text()
        results = find_yaml_hunks_for_key(contents, "contents")

        # count how many times the word "contents:" appears in the file
        # as a poor proxy for how many contents keys should be found
        expected_count = 0
        for line in filter(
            lambda line: line and not line.startswith("#"),
            map(str.strip, contents.splitlines()),
        ):
            if "contents:" in line:
                expected_count += 1

        if path.name == "coreutils.yaml":
            # coreutils.yaml has a "contents:" in a comment, which is incorrectly counted above
            # this is just a check so this is fine
            expected_count -= 1

        assert len(results) == expected_count, f"{path.name}: expected {expected_count}, got {len(results)}"
