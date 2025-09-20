# spellchecker: words subkey

import pytest
from helpers import h, p, inline_yaml

from src.chisel_releases_linter import Hunk


def test_hunk_basic() -> None:
    hunk = Hunk(lines=["line1", "line2", "line3"])
    assert hunk.start_line == 1
    assert hunk.end_line == 3
    assert hunk.lines == ["line1", "line2", "line3"]
    assert hunk.indent == 0


def test_hunk_with_indentation() -> None:
    hunk = Hunk(lines=["  line1", "  line2", "  line3"])
    assert hunk.start_line == 1
    assert hunk.end_line == 3
    assert hunk.lines == ["  line1", "  line2", "  line3"]
    assert hunk.indent == 2


def test_hunk_mixed_indentation() -> None:
    hunk = Hunk(lines=[" line1", "  line2", "   line3"])
    assert hunk.start_line == 1
    assert hunk.end_line == 3
    assert hunk.lines == [" line1", "  line2", "   line3"]
    assert hunk.indent == 1


def test_hunk_wrong_indentation() -> None:
    with pytest.raises(ValueError):
        h("""
        line1
       line2
      line3
      """)

    # Cannot go back to the original indentation level once it has increased
    with pytest.raises(ValueError):
        h(
            """
          key:
            subkey1: value
            subkey2: value
          key2: value
          """,
        )

    # But this is fine
    _ = h(
        """
        # a
        # b
        key:
          subkey1: value
          subkey2: value
        """,
    )


# with pytest.raises(ValueError):


def test_hunk_empty() -> None:
    with pytest.raises(ValueError):
        Hunk(lines=[])


def test_parse_yaml_to_hunks_basic() -> None:
    assert p("""
    key1:
      - item1
      - item2

    key2:
      subkey1: value1
      subkey2: value2
    """) == [
        h("""
        key1:
          - item1
          - item2
        """),
        h(
            """
        key2:
          subkey1: value1
          subkey2: value2
        """,
            start_line=5,
        ),
    ]


def test_parse_yaml_to_hunks_with_comments() -> None:
    assert p("""
        # multiline
        # comment
        key1:
          - item1
          - item2

        # multiline
        # comment but there is a gap

        key2:

          # another comment
          subkey1: value1
          subkey2: value2
        """) == [
        h(
            """
        # multiline
        # comment
        key1:
          - item1
          - item2
        """,
            start_line=1,
        ),
        h(
            """
        # multiline
        # comment but there is a gap
        """,
            start_line=7,
        ),
        h(
            """
        key2:

          # another comment
          subkey1: value1
          subkey2: value2
        """,
            start_line=10,
        ),
    ]


def test_parse_yaml_to_hunks_comment_merging() -> None:
    # Two consecutive comments with the same indent parse as a single hunk
    assert p("""
    # comment 1
    # comment 2
    """) == [
        h("""
    # comment 1
    # comment 2
    """)
    ]

    # Two comments separated by a blank line parse as two hunks
    # even though they have the same indentation
    assert p("""
    # comment 1

    # comment 2
    """) == [h("# comment 1"), h("# comment 2", 3)]

    # Two comments with different indentation parse as two hunks
    assert p("""
    # comment 1
      # comment 2
    """) == [h("# comment 1", 1, 0), h("# comment 2", 2, 2)]

    assert p("""
      # comment 1
    # comment 2
    """) == [h("# comment 1", 1, 2), h("# comment 2", 2, 0)]

    assert p("""
    # this
    # comment spans
    # 3 lines
    """) == [
        h("""
    # this
    # comment spans
    # 3 lines
    """)
    ]


def test_parse_yaml_to_hunks_comment_merging_with_following_hunk() -> None:
    # A comment followed by a hunk with the same indentation and no blank line between them
    # should be merged into a single hunk
    assert p("""
    # comment 1
    key: value
    """) == [
        h("""
    # comment 1
    key: value
    """)
    ]

    assert p("""
      # comment 1
      key: value
    """) == [
        h("""
      # comment 1
      key: value
      """)
    ]

    # A comment followed by a hunk with the same indentation but with a blank line between them
    # should not be merged into a single hunk
    assert p("""
    # comment 1

    key: value
    """) == [
        h("# comment 1", 1, 0),
        h("key: value", 3, 0),
    ]

    assert p(
        """
    # comment 1

    key: value
    """,
        indent=2,
    ) == [
        h("# comment 1", 1, 2),
        h("key: value", 3, 2),
    ]

    # A comment followed by a hunk with different indentation should not be merged into a single hunk
    assert p("""
    # comment 1
      key: value
    """) == [
        h("# comment 1", 1, 0),
        h("key: value", 2, 2),
    ]

    assert p("""
      # comment 1
    key: value
    """) == [
        h("# comment 1", 1, 2),
        h("key: value", 2, 0),
    ]
