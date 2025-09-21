#!/usr/bin/env python3
"""
Script to lint chisel-releases repo
"""
# spell-checker: ignore Marcin Konowalczyk lczyk
# spell-checker: words levelname
# mypy: disable-error-code="unused-ignore"

from __future__ import annotations

import argparse
import logging
import sys
from collections import deque
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from typing_extensions import Self
else:
    Self = object

__version__ = "0.0.2"
__author__ = "Marcin Konowalczyk"

__changelog__ = [
    ("0.0.2", "linting notes", "@lczyk"),
    ("0.0.1", "hunk implementation", "@lczyk"),
    ("0.0.0", "boilerplate", "@lczyk"),
]

COMMENT = "#"

################################################################################


def sort_by_bytes(slices: list[str]) -> list[str]:
    """Sort in the same way LC_ALL=C sort works in the shell."""
    return sorted(slices, key=lambda s: s.encode("utf-8"))


@dataclass(frozen=True)
class Hunk:
    """Hunk is a contiguous block of lines in a yaml file, starting at start_line
    and ending at end_line (inclusive). It must not start or end with an empty line.
    All the lines must have the same, or greater, indentation."""

    lines: list[str] = field(repr=False)
    start_line: int = 1

    @staticmethod
    def line_indent(line: str) -> int:
        return len(line) - len(line.lstrip())

    def __post_init__(self) -> None:
        # We check a bunch of invariants here
        if not self.lines:
            raise ValueError("Hunk must have at least one line.")

        # Make sure the hunk does not start or end with empty lines
        if not self.lines[0].strip():
            raise ValueError("Hunk cannot start with an empty line.")
        if not self.lines[-1].strip():
            print(self.lines)
            raise ValueError("Hunk cannot end with an empty line.")

        indent = self.indent
        increased = False
        for _i, line in enumerate(self.lines):
            if not line.strip():
                continue
            # Make sure that the indentation of all lines is the same or greater
            line_indent = self.line_indent(line)
            if line_indent < indent:
                raise ValueError("All lines in a hunk must have the same or greater indentation.")
            if line_indent > indent:
                # the indentation has increased
                increased = True
            if line_indent == indent and increased:
                raise ValueError("Hunk indentation cannot decrease back to the original level.")

        if self.start_line <= 0:
            raise ValueError("start_line must be > 0.")

    @property
    def end_line(self) -> int:
        return self.start_line + len(self.lines) - 1

    @property
    def indent(self) -> int:
        if not hasattr(self, "_indent"):
            object.__setattr__(self, "_indent", self.line_indent(self.lines[0]))
        return self._indent

    def __repr__(self) -> str:
        if self.start_line == self.end_line:
            # one-line hunk
            return f"Hunk({self.start_line}, indent={self.indent})"
        else:
            return f"Hunk({self.start_line}-{self.end_line}, indent={self.indent})"

    @classmethod
    def from_string(cls, contents: str, start_line: int = 1) -> Self:
        lines = contents.splitlines()
        return cls(lines=lines, start_line=start_line)

    def get_child_hunks(self) -> list[Hunk]:
        """Get child hunks of this hunk, i.e., hunks that are indented more than this hunk."""
        # find first line who's indentation is greater than self.indent
        start_index = None
        for i, line in enumerate(self.lines):
            stripped = line.lstrip()
            if not stripped:
                continue
            line_indent = self.line_indent(line)
            if line_indent > self.indent:
                start_index = i
                break
        if start_index is None:
            # no child hunks
            return []
        child_lines = self.lines[start_index:]
        child_hunks = parse_yaml_to_hunks(child_lines)
        # adjust the start_line of the child hunks
        for i, hunk in enumerate(child_hunks):
            child_hunks[i] = replace(hunk, start_line=self.start_line + start_index + hunk.start_line - 1)
        return child_hunks


def parse_yaml_to_hunks(
    contents: str | list[str],
) -> list[Hunk]:
    """Parse the contents of a yaml file into hunks."""
    lines = contents.splitlines() if isinstance(contents, str) else contents
    hunks: list[Hunk] = []
    if not lines:
        return hunks

    # Parse the lines into hunks
    # For now parse any comment lines as one-line hunks
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        if not stripped:
            i += 1
            continue
        # start of a hunk
        start_line = i
        hunk_lines = [line]
        i += 1
        if stripped.startswith(COMMENT):
            # comment line, hunk is just this line
            hunks.append(Hunk(lines=hunk_lines, start_line=start_line + 1))
            continue
        # collect all lines that are indented as much as, or more than, the first line
        start_indentation = len(line) - len(stripped)
        while i < len(lines):
            next_line = lines[i]
            next_stripped = next_line.lstrip()
            next_indentation = len(next_line) - len(next_stripped)
            if next_indentation > start_indentation or not next_stripped:
                hunk_lines.append(next_line)
                i += 1
            else:
                break

        # walk backwards and remove any trailing empty lines
        while hunk_lines and not hunk_lines[-1].strip():
            hunk_lines.pop()
            i -= 1
        if not hunk_lines:
            raise ValueError("Hunk cannot be empty after removing trailing empty lines.")

        try:
            hunk = Hunk(lines=hunk_lines, start_line=start_line + 1)
        except ValueError as e:
            end_line = start_line + len(hunk_lines)
            raise ValueError(f"Error parsing hunk at lines {start_line + 1}-{end_line}: {e}") from e
        hunks.append(hunk)

    def is_comment(hunk: Hunk) -> bool:
        return len(hunk.lines) >= 1 and hunk.lines[0].lstrip().startswith(COMMENT)

    merged_hunks: list[Hunk]

    # Merge any consecutive comment hunks with the same indentation
    # if there is no empty line between them
    # We repeat this until no more merges are possible
    any_merged = True
    while any_merged:
        merged_hunks = []
        i = 0
        while i < len(hunks):
            hunk = hunks[i]
            i += 1
            if not is_comment(hunk):
                merged_hunks.append(hunk)
                continue
            # we are a comment hunk
            comment_lines = list(hunk.lines)
            while i < len(hunks):
                next_hunk = hunks[i]
                if (
                    is_comment(next_hunk)
                    and next_hunk.indent == hunk.indent
                    and next_hunk.start_line == hunk.end_line + 1
                ):
                    comment_lines.extend(next_hunk.lines)
                    i += 1
                else:
                    break
            merged_hunks.append(Hunk(lines=comment_lines, start_line=hunk.start_line))

        any_merged = len(merged_hunks) < len(hunks)
        hunks = merged_hunks

    # # now merge any comment hunks with any following hunk
    # if they have the same indentation and if there is no empty line between them
    merged_hunks = []
    i = 0
    while i < len(hunks):
        hunk = hunks[i]
        i += 1
        if not is_comment(hunk):
            # just a normal hunk
            merged_hunks.append(hunk)
            continue
        if i >= len(hunks):
            # we are the last hunk, just add us
            merged_hunks.append(hunk)
            continue
        # NOTE: we don't assert here that len(hunk.lines) == 1 because we may have
        #       merged multiple comment hunks above
        next_hunk = hunks[i]
        if next_hunk.indent == hunk.indent and next_hunk.start_line == hunk.end_line + 1:
            # we should not be in a situation where we have two consecutive
            # comment hunks with the same indent
            if is_comment(next_hunk):
                print()
                print("---")
                print("\n".join(hunk.lines))
                print("---")
                print("\n".join(next_hunk.lines))
                raise AssertionError(
                    f"Unexpected consecutive comment hunks at lines {hunk.start_line}-{next_hunk.end_line}"
                )
            merged_hunks.append(
                Hunk(
                    lines=hunk.lines + next_hunk.lines,
                    start_line=hunk.start_line,
                )
            )
            i += 1
        else:
            merged_hunks.append(hunk)

    hunks = merged_hunks

    return hunks


@dataclass(frozen=True)
class KeyHunk(Hunk):
    """Represents a key in yaml, and its associated lines. Note that the hunk may have
    a comment attached before the key line."""

    def __post_init__(self) -> None:
        super().__post_init__()
        _ = self._parse_key()

    def _parse_key(self) -> tuple[str, int]:
        # Parse the key from the lines
        for i, line in enumerate(self.lines):
            line_indent = self.line_indent(line)
            if line_indent > self.indent:
                # We must have a key in the first non-indented lines
                raise ValueError(f"No key found in hunk: {self.lines!r}")
            key = self.parse_key(line)
            if key is not None:
                object.__setattr__(self, "_key", key)
                object.__setattr__(self, "_key_line_index", i)
                break
        else:
            raise ValueError(f"No key found in hunk: {self.lines!r}")
        return key, i

    @staticmethod
    def parse_key(line: str) -> str | None:
        """Return the key of the hunk if the line starts a hunk, else None."""
        stripped = line.lstrip()
        if not stripped or stripped.startswith(COMMENT):
            return None
        if ":" not in stripped:
            return None
        key = stripped.split(":", 1)[0].rstrip()
        if not key:
            return None
        if key.startswith("- "):
            return None
        return key if key else None

    @property
    def key(self) -> str:
        key = getattr(self, "_key", None)
        if key is None:
            key, _ = self._parse_key()
        return key

    @property
    def key_line_index(self) -> int:
        key_index = getattr(self, "_key_line_index", None)
        if key_index is None:
            _, key_index = self._parse_key()
        return key_index

    def __repr__(self) -> str:
        if self.start_line == self.end_line:
            # one-line hunk
            return f"KeyHunk({self.start_line}, indent={self.indent}, key={self.key!r})"
        else:
            return f"KeyHunk({self.start_line}-{self.end_line}, indent={self.indent}, key={self.key!r})"


def find_yaml_hunks_for_key(contents: str, key: str) -> list[KeyHunk]:
    hunks = parse_yaml_to_hunks(contents)
    key_hunks = []

    to_process = deque(hunks)
    while to_process:
        hunk = to_process.popleft()
        try:
            kh = KeyHunk(lines=hunk.lines, start_line=hunk.start_line)
            if kh.key == key:
                key_hunks.append(kh)
        except ValueError:
            # not a key hunk
            continue
        child_hunks = hunk.get_child_hunks()
        to_process.extend(child_hunks)

    return key_hunks


@dataclass(frozen=True)
class ItemHunk(Hunk):
    """Represents a list item in yaml, and its associated lines. Note that the hunk may have
    a comment attached before the item line. Only one item per ItemHunk is allowed."""

    def __post_init__(self) -> None:
        super().__post_init__()
        _ = self._parse_item()

    def _parse_item(self) -> tuple[str, int]:
        for i, line in enumerate(self.lines):
            line_indent = self.line_indent(line)
            if line_indent > self.indent:
                # We must have an item in the first non-indented lines
                raise ValueError(f"No list item found in hunk: {self.lines!r}")
            item = self.parse_item(line)
            if item is not None:
                if hasattr(self, "_item"):
                    raise ValueError(f"Multiple list items found in hunk: {self.lines!r}")
                else:
                    object.__setattr__(self, "_item", item)
                    object.__setattr__(self, "_item_line_index", i)
        if not hasattr(self, "_item"):
            raise ValueError(f"No list item found in hunk: {self.lines!r}")
        return self._item, self._item_line_index

    @staticmethod
    def parse_item(line: str) -> str | None:
        """Return the item of the hunk if the line starts a list item, else None."""
        stripped = line.strip()
        if not stripped.startswith("-"):
            return None
        stripped = stripped[1:]  # remove the "-"
        stripped = stripped.lstrip()
        # it may have a comment at the end
        if COMMENT in stripped:
            stripped = stripped.split(COMMENT, 1)[0].rstrip()
        return stripped if stripped else None

    @property
    def item(self) -> str:
        item = getattr(self, "_item", None)
        if item is None:
            item, _ = self._parse_item()
        return item

    @property
    def item_line_index(self) -> int:
        item_index = getattr(self, "_item_line_index", None)
        if item_index is None:
            _, item_index = self._parse_item()
        return item_index

    def __repr__(self) -> str:
        if self.start_line == self.end_line:
            # one-line hunk
            return f"ItemHunk({self.start_line}, indent={self.indent}, item={self.item!r})"
        else:
            return f"ItemHunk({self.start_line}-{self.end_line}, indent={self.indent}, item={self.item!r})"


def parse_list_items(
    contents: str | list[str],
    start_line: int = 1,
) -> tuple[list[ItemHunk], list[Hunk]]:
    """Parse lines into list items hunks."""
    lines = contents.splitlines() if isinstance(contents, str) else contents
    item_hunks: list[ItemHunk] = []
    comment_hunks: list[Hunk] = []
    if not lines:
        return item_hunks, comment_hunks
    parsed_hunks = parse_yaml_to_hunks(lines)
    for hunk in parsed_hunks:
        try:
            ih = ItemHunk(lines=hunk.lines, start_line=hunk.start_line)
            item_hunks.append(ih)
        except ValueError:  # noqa: PERF203
            if all(line.lstrip().startswith(COMMENT) or not line.strip() for line in hunk.lines):
                comment_hunks.append(hunk)
            else:
                raise

    # Adjust the start_line of the hunks
    for i, hunk in enumerate(item_hunks):
        item_hunks[i] = replace(hunk, start_line=start_line + hunk.start_line - 1)

    for i, hunk in enumerate(comment_hunks):
        comment_hunks[i] = replace(hunk, start_line=start_line + hunk.start_line - 1)

    return item_hunks, comment_hunks


def parse_key_children(contents: str | list[str], start_line: int = 1) -> tuple[list[KeyHunk], list[Hunk]]:
    """Parse lines into key hunks."""
    lines = contents.splitlines() if isinstance(contents, str) else contents
    key_hunks: list[KeyHunk] = []
    comment_hunks: list[Hunk] = []
    if not lines:
        return key_hunks, comment_hunks
    parsed_hunks = parse_yaml_to_hunks(lines)
    for hunk in parsed_hunks:
        try:
            kh = KeyHunk(lines=hunk.lines, start_line=hunk.start_line)
            key_hunks.append(kh)
        except ValueError:  # noqa: PERF203
            # might be a comment hunk
            if all(line.lstrip().startswith(COMMENT) or not line.strip() for line in hunk.lines):
                comment_hunks.append(hunk)
            else:
                raise

    # Adjust the start_line of the hunks
    for i, hunk in enumerate(key_hunks):
        key_hunks[i] = replace(hunk, start_line=start_line + hunk.start_line - 1)
    for i, hunk in enumerate(comment_hunks):
        comment_hunks[i] = replace(hunk, start_line=start_line + hunk.start_line - 1)

    return key_hunks, comment_hunks


@dataclass(frozen=True)
class LintingNote:
    message: str
    filename: str | Path | None = None
    start_line: int | None = None
    end_line: int | None = None
    hint: str = ""
    issue: bool = False
    issuer: str = ""

    def get_location(self) -> str | None:
        if self.filename is None:
            return None
        if self.start_line is None:
            return str(self.filename)
        if self.end_line is None or self.end_line == self.start_line:
            return f"{self.filename}:{self.start_line}"
        return f"{self.filename}:{self.start_line}-{self.end_line}"

    def __str__(self) -> str:
        location = self.get_location()
        level = "ISSUE" if self.issue else "NOTE"
        # issuer = f"[{self.issuer}] " if self.issuer else ""
        result = f"{level}:"
        result = f"{result} {self.message}"
        if location is not None:
            result = f"{result} {location}"
        return result


class Stage(Protocol):
    notes: list[LintingNote]

    def __init__(self, contents: str, *, filename: str) -> None: ...

    def process(self) -> None: ...


class LintingNoteMixin:
    notes: list[LintingNote]
    __filename: str

    def __init__(self) -> None:
        _filename = getattr(self, "filename", None)
        if not _filename:
            raise ValueError("LintingNoteMixin requires 'filename' attribute to be set.")
        self.__filename = _filename
        self.notes = []

    def _note(self, message: str, start_line: int = 1, end_line: int | None = None) -> None:
        if end_line is None:
            end_line = start_line
        assert end_line >= start_line
        self.notes.append(
            LintingNote(
                message=message,
                filename=self.__filename,
                start_line=start_line,
                end_line=end_line,
                issuer=self.__class__.__name__,
            )
        )

    def _issue(self, message: str, hint: str = "", start_line: int = 1, end_line: int | None = None) -> None:
        if end_line is None:
            end_line = start_line
        assert end_line >= start_line
        self.notes.append(
            LintingNote(
                message=message,
                hint=hint,
                filename=self.__filename,
                start_line=start_line,
                end_line=end_line,
                issue=True,
                issuer=self.__class__.__name__,
            )
        )


class StageMixin(LintingNoteMixin):
    def __init__(self, contents: str, *, filename: str) -> None:
        self.contents = contents
        self.filename = filename
        super().__init__()


class EssentialsSorter(StageMixin):
    def process(self) -> None:
        hunks = find_yaml_hunks_for_key(self.contents, "essential")
        if not hunks:
            self._note("No 'essentials' hunks found")
            return

        for hunk in hunks:
            item_hunks, _ = parse_list_items(
                hunk.lines[hunk.key_line_index + 1 :],
                start_line=hunk.start_line + hunk.key_line_index + 1,
            )
            items = [ih.item for ih in item_hunks]
            if not items:
                self._issue(
                    f"'essential' key at lines {hunk.start_line + 1}-{hunk.end_line} in '{self.filename}' has no items",
                    start_line=hunk.start_line,
                    end_line=hunk.end_line,
                )
                continue
            # Check for duplicates
            unique_items: set[str] = set()
            duplicates: set[str] = set()
            for item in items:
                if item in unique_items:
                    duplicates.add(item)
                else:
                    unique_items.add(item)
            if duplicates:
                message = "'essential' key has duplicate items"
                if len(duplicates) == 1:
                    hint = f"The duplicate item is: '{next(iter(duplicates))}'"
                elif len(duplicates) <= 5:
                    hint = "The duplicate items are: " + ", ".join(f"'{d}'" for d in duplicates)
                else:
                    hint = f"There are {len(duplicates)} duplicate items. The first 5 are: " + ", ".join(
                        f"'{d}'" for d in list(duplicates)[:5]
                    )
                self._issue(message, hint=hint, start_line=hunk.start_line, end_line=hunk.end_line)
                continue
            sorted_items = sort_by_bytes(items)
            if items != sorted_items:
                message = (
                    f"'essential' key at lines {hunk.start_line + 1}-{hunk.end_line} "
                    f"in '{self.filename}' is not sorted."
                )
                hint = "The items should be sorted in byte order (LC_ALL=C). The correct order is:"
                for v in sorted_items:
                    indent = " " * item_hunks[0].indent
                    # message += f"\n{indent}- {v}"
                    hint += f"\n{indent}- {v}"
                self._issue(message, hint=hint, start_line=hunk.start_line, end_line=hunk.end_line)


if TYPE_CHECKING:
    _essentials_sorter: Stage = EssentialsSorter.__new__(EssentialsSorter)


class ContentsSorter(LintingNoteMixin):
    def __init__(self, contents: str, *, filename: str) -> None:
        self.contents = contents
        self.filename = filename
        super().__init__()

    def process(self) -> None:
        hunks = find_yaml_hunks_for_key(self.contents, "contents")
        if not hunks:
            self._note("No 'contents' hunks found")
            return
        for hunk in hunks:
            key_hunks, _ = parse_key_children(
                hunk.lines[hunk.key_line_index + 1 :],
                start_line=hunk.start_line + hunk.key_line_index + 1,
            )
            if not key_hunks:
                self._issue("The 'contents' key has no sub-keys", start_line=hunk.start_line, end_line=hunk.end_line)
                continue

            keys = [kh.key for kh in key_hunks]

            if len(keys) != len(set(keys)):
                duplicate_keys = [key for key in keys if keys.count(key) > 1]
                message = "'contents' has duplicate keys"
                # construct the hint.
                if len(duplicate_keys) == 1:
                    hint = f"The duplicate key is: '{duplicate_keys[0]}'"
                elif len(duplicate_keys) <= 5:
                    hint = "The duplicate keys are: " + ", ".join(f"'{k}'" for k in set(duplicate_keys))
                else:
                    hint = f"There are {len(set(duplicate_keys))} duplicate keys. The first 5 are: " + ", ".join(
                        f"'{k}'" for k in set(duplicate_keys[:5])
                    )
                self._issue(message, hint=hint, start_line=hunk.start_line, end_line=hunk.end_line)
                continue

            sorted_keys = sort_by_bytes(keys)
            if keys != sorted_keys:
                message = "'contents' is not sorted"
                # construct the hint.
                hint = "The keys should be sorted in byte order (LC_ALL=C)\n"
                if len(keys) <= 10:
                    hint += "The correct order is:\n"
                    for k in sorted_keys:
                        hint += f"  {k}:\n"
                else:
                    # Find the first difference
                    first_diff_index = 0
                    for i, (k1, k2) in enumerate(zip(keys, sorted_keys)):
                        if k1 != k2:
                            first_diff_index = i
                            break

                    first_diff_line_num = key_hunks[first_diff_index].start_line
                    hint += (
                        f"The first difference is at line {first_diff_line_num}:\n"
                        f"  '{keys[first_diff_index]}' should be '{sorted_keys[first_diff_index]}'"
                    )

                self._issue(message, hint=hint, start_line=hunk.start_line, end_line=hunk.end_line)


if TYPE_CHECKING:
    _contents_sorter: Stage = ContentsSorter.__new__(ContentsSorter)


class CopyrightSliceExists(LintingNoteMixin):
    def __init__(self, contents: str, *, filename: str) -> None:
        self.contents = contents
        self.filename = filename
        super().__init__()

    def process(self) -> None:
        hunks = find_yaml_hunks_for_key(self.contents, "copyright")
        if not hunks:
            self._issue("The 'copyright' slice is missing")
            return


if TYPE_CHECKING:
    _copyright_slice_exists: Stage = CopyrightSliceExists.__new__(CopyrightSliceExists)


class CopyrightSliceIsLast(LintingNoteMixin):
    def __init__(self, contents: str, *, filename: str) -> None:
        self.contents = contents
        self.filename = filename
        super().__init__()

    def process(self) -> None:
        copyright_hunks = find_yaml_hunks_for_key(self.contents, "copyright")
        if not copyright_hunks:
            self._issue("The 'copyright' slice is missing")
            return

        if len(copyright_hunks) > 1:
            self._issue("Multiple 'copyright' slices found")
            return

        copyright_hunk = copyright_hunks[0]

        slices_hunks = find_yaml_hunks_for_key(self.contents, "slices")
        if not slices_hunks:
            self._issue("The 'slices' section is missing")
            return

        if len(slices_hunks) > 1:
            self._issue("Multiple 'slices' sections found")
            return

        slices_hunk = slices_hunks[0]

        slices_key_hunks, _ = parse_key_children(
            slices_hunk.lines[slices_hunk.key_line_index + 1 :],
            start_line=slices_hunk.start_line + slices_hunk.key_line_index + 1,
        )
        if not slices_key_hunks:
            self._issue(
                "The 'slices' section has no slices",
                start_line=slices_hunk.start_line,
                end_line=slices_hunk.end_line,
            )
            return

        # the last key_hunk should be a copyright hunk
        last_key_hunk = slices_key_hunks[-1]
        if copyright_hunk != last_key_hunk:
            self._issue(
                message="'copyright' slice is not the last slice",
                start_line=copyright_hunk.start_line,
                end_line=copyright_hunk.end_line,
            )


if TYPE_CHECKING:
    _copyright_slice_is_last: Stage = CopyrightSliceIsLast.__new__(CopyrightSliceIsLast)


class SliceKeysOrder(LintingNoteMixin):
    def __init__(self, contents: str, *, filename: str) -> None:
        self.contents = contents
        self.filename = filename
        super().__init__()

    def process(self) -> None:
        slices_hunks = find_yaml_hunks_for_key(self.contents, "slices")
        if not slices_hunks:
            self._issue(f"No 'slices' hunk found in '{self.filename}'")
            return

        if len(slices_hunks) > 1:
            self._issue(f"Multiple 'slices' hunks found in '{self.filename}'")
            return

        slices_hunk = slices_hunks[0]
        slice_key_hunks, _ = parse_key_children(
            slices_hunk.lines[slices_hunk.key_line_index + 1 :],
            start_line=slices_hunk.start_line + slices_hunk.key_line_index + 1,
        )

        for slice_hunk in slice_key_hunks:
            key_hunks, _ = parse_key_children(
                slice_hunk.lines[slice_hunk.key_line_index + 1 :],
                start_line=slice_hunk.start_line + slice_hunk.key_line_index + 1,
            )
            if not key_hunks:
                self._issue("The slice has no keys", start_line=slice_hunk.start_line)
                continue
            # we can have up to two keys: 'essential' and 'contents'
            # If both are present, 'essential' must come first
            keys = [kh.key for kh in key_hunks]
            # allowed keys in the order they should appear
            allowed_keys = ["essential", "contents", "mutate"]
            keys_set = set(keys)
            allowed_keys_set = set(allowed_keys)
            if not keys_set.issubset(allowed_keys_set):
                extra_keys = keys_set - allowed_keys_set
                hint = f"Allowed keys are: {', '.join(allowed_keys)}"
                self._issue(
                    f"Unexpected keys {extra_keys} in slice '{slice_hunk.key}'",
                    hint=hint,
                    start_line=slice_hunk.start_line,
                    end_line=slice_hunk.end_line,
                )
                continue
            if keys != sorted(keys, key=lambda k: allowed_keys.index(k)):
                message = f"Keys in slice '{slice_hunk.key}' are not in the correct order"
                hint = "The correct order is:\n"
                for k in allowed_keys:
                    if k in keys:
                        indent = " " * key_hunks[0].indent
                        hint += f"{indent}{k}:\n"
                self._issue(
                    message,
                    hint=hint,
                    start_line=slice_hunk.start_line,
                    end_line=slice_hunk.end_line,
                )


if TYPE_CHECKING:
    _slice_keys_order: Stage = SliceKeysOrder.__new__(SliceKeysOrder)


class NoContentsEssentialGap(LintingNoteMixin):
    def __init__(self, contents: str, *, filename: str) -> None:
        self.contents = contents
        self.filename = filename
        super().__init__()

    def process(self) -> None:
        slices_hunks = find_yaml_hunks_for_key(self.contents, "slices")
        if not slices_hunks:
            # self._issue(f"No 'slices' hunk found in '{self.filename}'")
            return

        if len(slices_hunks) > 1:
            # self._issue(f"Multiple 'slices' hunks found in '{self.filename}'")
            return

        slices_hunk = slices_hunks[0]
        slice_key_hunks, _ = parse_key_children(
            slices_hunk.lines[slices_hunk.key_line_index + 1 :],
            start_line=slices_hunk.start_line + slices_hunk.key_line_index + 1,
        )

        for slice_hunk in slice_key_hunks:
            key_hunks, _ = parse_key_children(
                slice_hunk.lines[slice_hunk.key_line_index + 1 :],
                start_line=slice_hunk.start_line + slice_hunk.key_line_index + 1,
            )
            if not key_hunks:
                self._issue("The slice has no keys", start_line=slice_hunk.start_line)
                continue
            # There should be no gap between the keys hunks
            for i in range(len(key_hunks) - 1):
                this_hunk = key_hunks[i]
                next_hunk = key_hunks[i + 1]
                if this_hunk.end_line + 1 != next_hunk.start_line:
                    self._issue(
                        f"Unexpected gap between keys '{this_hunk.key}' and '{next_hunk.key}' "
                        f"in slice '{slice_hunk.key}'",
                        start_line=this_hunk.end_line + 1,
                        end_line=next_hunk.start_line - 1,
                    )


if TYPE_CHECKING:
    _no_contents_essential_gap: Stage = NoContentsEssentialGap.__new__(NoContentsEssentialGap)


class NoGapBetweenSlicesKeyAndContents(LintingNoteMixin):
    def __init__(self, contents: str, *, filename: str) -> None:
        self.contents = contents
        self.filename = filename
        super().__init__()

    def process(self) -> None:
        slices_hunks = find_yaml_hunks_for_key(self.contents, "slices")
        if not slices_hunks:
            # self._issue(f"No 'slices' hunk found in '{self.filename}'")
            return

        if len(slices_hunks) > 1:
            # self._issue(f"Multiple 'slices' hunks found in '{self.filename}'")
            return

        slices_hunk = slices_hunks[0]
        slice_key_hunks, _ = parse_key_children(
            slices_hunk.lines[slices_hunk.key_line_index + 1 :],
            start_line=slices_hunk.start_line + slices_hunk.key_line_index + 1,
        )

        if not slice_key_hunks:
            # self._issue("The 'slices' section has no slices", start_line=slices_hunk.start_line)
            return

        first_key_hunk = slice_key_hunks[0]

        if slices_hunk.start_line + slices_hunk.key_line_index + 1 != first_key_hunk.start_line:
            self._issue(
                f"Unexpected gap between 'slices' key and first slice '{first_key_hunk.key}'",
                start_line=slices_hunk.start_line,
            )


if TYPE_CHECKING:
    _no_gap_between_slices_key_and_contents: Stage = NoGapBetweenSlicesKeyAndContents.__new__(
        NoGapBetweenSlicesKeyAndContents
    )


class FilesHaveNewlineAtEnd(LintingNoteMixin):
    def __init__(self, contents: str, *, filename: str) -> None:
        self.contents = contents
        self.filename = filename
        super().__init__()

    def process(self) -> None:
        lines = self.contents.splitlines()
        if not lines:
            self._issue("File is empty")
            return

        trailing_newlines = 0
        for line in reversed(self.contents):
            stripped = line.strip()
            if not stripped:
                trailing_newlines += 1
            else:
                break

        if trailing_newlines == 0:
            self._issue("File does not end with a newline", start_line=len(lines))
        elif trailing_newlines > 1:
            self._issue(
                f"File has {trailing_newlines} trailing newlines. Should have exactly one",
                start_line=len(lines) - trailing_newlines + 1,
            )


if TYPE_CHECKING:
    _files_have_newline_st_end: Stage = FilesHaveNewlineAtEnd.__new__(FilesHaveNewlineAtEnd)


def test_all_slices(directory: Path) -> list[LintingNote]:
    slices_dir = directory / "slices"
    if not slices_dir.is_dir():
        raise FileNotFoundError(f"'slices' directory not found in {directory}")

    # list all the .yaml files in the slices directory
    notes: list[LintingNote] = []

    yaml_files = list(slices_dir.glob("*.yaml"))
    if not yaml_files:
        notes.append(LintingNote(message=f"No .yaml files found in {slices_dir}", issue=True))
        return notes

    stages: list[type[Stage]] = [
        EssentialsSorter,
        ContentsSorter,
        CopyrightSliceExists,
        CopyrightSliceIsLast,
        SliceKeysOrder,
        NoContentsEssentialGap,
        NoGapBetweenSlicesKeyAndContents,
    ]

    notes.append(LintingNote(message=f"Found {len(yaml_files)} .yaml files in {slices_dir}"))

    for yaml_file in yaml_files:
        relative_path = yaml_file.relative_to(directory)
        # if yaml_file.name != "dpkg.yaml":
        #     continue
        contents = yaml_file.read_text()

        logging.debug(f"Processing file: {relative_path}")

        for stage_cls in stages:
            # contents = stage(contents, filename=str(yaml_file))
            stage = stage_cls(contents, filename=str(relative_path))
            # NOTE: for now we just blow up with an exception. Ha.
            stage.process()
            notes.extend(stage.notes)

    return notes


def test_all_test_files(directory: Path) -> list[LintingNote]:
    tests_dir = args.directory / "tests" / "spread" / "integration"
    if not tests_dir.is_dir():
        raise FileNotFoundError(f"'tests' directory not found in {args.directory}")

    # get all the .sh files in the tests directory and its subdirectories
    _bash_scripts = list(tests_dir.rglob("**/*.sh"))

    return []


def test_all_files(directory: Path) -> list[LintingNote]:
    all_files = list(directory.rglob("**/*"))
    all_files = [f for f in all_files if f.is_file()]

    stages: list[type[Stage]] = [
        FilesHaveNewlineAtEnd,
    ]

    # prefixes to skip
    skip_prefixes = (
        ".git",
        "tests/tmp",
        "rootfs",
    )

    notes: list[LintingNote] = []

    for file in all_files:
        relative_path = file.relative_to(directory)
        if any(str(relative_path).startswith(prefix) for prefix in skip_prefixes):
            logging.debug(f"Skipping file in '{skip_prefixes}': {relative_path}")
            continue

        try:
            contents = file.read_text()
        except UnicodeDecodeError:
            # non-unicode file. must be some binary blob. skip it
            logging.debug(f"Skipping binary file: {relative_path}")
            continue

        logging.debug(f"Processing file: {relative_path}")

        for stage_cls in stages:
            stage = stage_cls(contents, filename=str(relative_path))
            stage.process()
            notes.extend(stage.notes)

    return notes


def maybe_colorize(text: str, *, no_color: bool) -> str:
    if no_color:
        return text

    YELLOW = "\033[33m"
    CYAN = "\033[36m"
    NC = "\033[0m"  # No Color
    if "ISSUE" in text:
        text = text.replace("ISSUE", f"{YELLOW}ISSUE{NC}")  # Yellow
    if "NOTE" in text:
        text = text.replace("NOTE", f"{CYAN}NOTE{NC}")  # Cyan
    if "HINT" in text:
        text = text.replace("HINT", f"{CYAN}HINT{NC}")  # Cyan
    return text


## MAIN ########################################################################


def main(args: argparse.Namespace) -> None:
    slices_notes = test_all_slices(args.directory)
    test_file_notes = test_all_test_files(args.directory)
    all_files_notes = test_all_files(args.directory)

    all_notes = slices_notes + test_file_notes + all_files_notes

    any_issues = False
    for note in all_notes:
        print(maybe_colorize(str(note), no_color=args.no_color))
        if note.issue:
            any_issues = True
        if args.hint and note.hint:
            hint_lines = note.hint.splitlines()
            print(maybe_colorize(f".HINT: {hint_lines[0]}", no_color=args.no_color))
            for hint_line in hint_lines[1:]:
                print(f"       {hint_line}")

    if not any_issues:
        message = "No issues found"
        if not args.no_color:
            # party
            message += " 🎂🥳"
        print(message)
        sys.exit(0)
    else:
        sys.exit(1)


################################################################################

## BOILERPLATE #################################################################


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sort slices in SDFs",
    )

    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("directory", type=Path, help="chisel-releases directory")
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output (if colorlog is installed).",
    )
    parser.add_argument(
        "--hint",
        action="store_true",
        help="Show hints for fixing issues (if available).",
    )
    # parser.add_argument(
    #     "--log-level",
    #     type=str,
    #     default="info",
    #     choices=["debug", "info", "warning", "error", "fatal", "critical"],
    #     help="Set the logging level (default: info).",
    # )
    # parser.add_argument(
    #     "--jobs",
    #     "-j",
    #     type=int,
    #     default=1,  # -1 = as many as possible, 1 = no parallelism
    #     help="Number of parallel jobs to use when fetching PR details. Default is 1 (no parallelism).",
    # )
    # parser.add_argument(
    #     "--in-place",
    #     action="store_true",
    #     help="Modify the files in place. By default, the script only prints the changes that would be made.",
    # )

    args = parser.parse_args()
    # if args.jobs == 0 or args.jobs < -1:
    #     parser.error("--jobs must be a positive integer or -1 for unlimited.")
    # args.jobs = None if args.jobs == -1 else args.jobs  # None = as many as possible
    return args


def setup_logging(log_level: str) -> None:
    _logger = logging.getLogger()
    handler = logging.StreamHandler()
    fmt = "%(asctime)s %(levelname)s %(message)s"
    datefmt = "%Y-%m-%dT%H:%M:%S"
    formatter: type[logging.Formatter] = logging.Formatter
    # Try to use colorlog for colored output
    try:
        import colorlog  # type: ignore

        fmt = fmt.replace("%(levelname)s", "%(log_color)s%(levelname)s%(reset)s")
        formatter = colorlog.ColoredFormatter  # type: ignore
    except ImportError:
        pass

    handler.setFormatter(formatter(fmt, datefmt))  # type: ignore
    _logger.addHandler(handler)
    log_level = "critical" if log_level.lower() == "fatal" else log_level
    _logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))


## ENTRYPOINT ##################################################################

if __name__ == "__main__":
    args = parse_args()
    setup_logging("info")
    logging.debug("Parsed args: %s", args)

    try:
        main(args)

    except NotImplementedError as e:
        logging.error("Not implemented: %s", e)
        sys.exit(99)

    except Exception as e:
        e_str = str(e)
        e_str = e_str or "An unknown error occurred."
        logging.critical(e_str, exc_info=True)
        sys.exit(1)
