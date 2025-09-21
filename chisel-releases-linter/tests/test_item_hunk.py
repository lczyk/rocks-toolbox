# spellchecker: words subkey

import pytest
from helpers import ch, ih, inline_yaml

from src.chisel_releases_linter import ItemHunk, parse_list_items


def test_item_hunk_parse_item() -> None:
    assert ItemHunk.parse_item("- item") == "item"
    assert ItemHunk.parse_item("  - item") == "item"
    assert ItemHunk.parse_item("  - item with: colons: in: it") == "item with: colons: in: it"
    assert ItemHunk.parse_item("  -    item with leading spaces") == "item with leading spaces"
    assert ItemHunk.parse_item("  -item without space after dash") == "item without space after dash"
    assert ItemHunk.parse_item("  - item with trailing spaces   ") == "item with trailing spaces"
    assert ItemHunk.parse_item("  - item with comment  # this is a comment") == "item with comment"
    assert ItemHunk.parse_item("  - item with # multiple # comments # here") == "item with"
    assert ItemHunk.parse_item("not an item") is None
    assert ItemHunk.parse_item("  not an item") is None
    assert ItemHunk.parse_item("") is None
    assert ItemHunk.parse_item("   ") is None
    assert ItemHunk.parse_item("# just a comment") is None
    assert ItemHunk.parse_item("  # just a comment with leading spaces") is None
    assert ItemHunk.parse_item("  # - not an item in a comment") is None
    assert ItemHunk.parse_item("  key: value") is None
    assert ItemHunk.parse_item("  - key: value in list") == "key: value in list"


def test_item_hunk_basic() -> None:
    hunk = ih("- item1")
    assert hunk.item == "item1"
    assert hunk.lines == ["- item1"]
    assert hunk.start_line == 1
    assert hunk.end_line == 1

    hunk = ih("""
    # mutliline
    # comment
    - item1
    """)

    assert hunk.item == "item1"
    assert hunk.lines == [
        "# mutliline",
        "# comment",
        "- item1",
    ]


def test_item_hunk_invalid() -> None:
    with pytest.raises(ValueError):
        ih(
            """
            # comment
            """,
        )

    with pytest.raises(ValueError):
        ih(
            """
            not an item
            another line
            """,
        )

    with pytest.raises(ValueError):
        ih(
            """
            key: value
            another line
            """,
        )

    # item must be in the first non-indented lines
    with pytest.raises(ValueError):
        ih(
            """
            # comment line
            # another comment
            not an item
                - item in list
            """,
        )

    # only one item per ItemHunk
    with pytest.raises(ValueError):
        ih(
            """
            - item1
            - item2
            """,
        )


def test_parse_list_items_basic() -> None:
    assert parse_list_items(
        inline_yaml("""
        - item1
        - item2
        - item3
        """)
    )[0] == [
        ih("- item1"),
        ih("- item2", start_line=2),
        ih("- item3", start_line=3),
    ]


def test_parse_list_items_with_comments() -> None:
    assert parse_list_items(
        inline_yaml("""
        # comment
        - item1
        - item2
        # another comment
        - item3
        """)
    )[0] == [
        ih("""
        # comment
        - item1
        """),
        ih("- item2", start_line=3),
        ih(
            """
        # another comment
        - item3
        """,
            start_line=4,
        ),
    ]


def test_parse_list_items_with_gaps() -> None:
    assert parse_list_items(
        inline_yaml("""
        # comment
        - item1

        - item2

        # another comment
        - item3
        """)
    )[0] == [
        ih("""
        # comment
        - item1
        """),
        ih("- item2", start_line=4),
        ih(
            """
        # another comment
        - item3
        """,
            start_line=6,
        ),
    ]


def test_parse_list_items_with_inline_comments() -> None:
    assert parse_list_items(
        inline_yaml("""
        - item1  # comment
        - item2  # another comment
        """)
    )[0] == [
        ih("- item1  # comment"),
        ih("- item2  # another comment", start_line=2),
    ]


def test_parse_list_items_trailing_comment() -> None:
    items, comments = parse_list_items(
        inline_yaml("""
        - item1
        - item2
        # comment
        # another comment
        """)
    )
    assert items == [
        ih("- item1"),
        ih("- item2", start_line=2),
    ]
    assert comments == [
        ch(
            """
        # comment
        # another comment
        """,
            start_line=3,
        )
    ]


def test_parse_list_items_no_items() -> None:
    items, comments = parse_list_items(
        inline_yaml("""
        # comment
        # another comment
        """)
    )
    assert items == []
    assert comments == [
        ch("""
        # comment
        # another comment
        """)
    ]
