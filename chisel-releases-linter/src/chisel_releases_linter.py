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
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Protocol
from collections import deque

if TYPE_CHECKING:
    from typing_extensions import Self
else:
    Self = object

__version__ = "0.0.1"
__author__ = "Marcin Konowalczyk"

__changelog__ = [
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
        return getattr(self, "_indent")

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


def parse_yaml_hunks_for_key(contents: str, key: str) -> list[KeyHunk]:
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
            continue
        child_hunks = hunk.get_child_hunks()
        to_process.extend(child_hunks)

    return key_hunks


@dataclass(frozen=True)
class ItemHunk(Hunk):
    """Represents a list item in yaml, and its associated lines. Note that the hunk may have
    a comment attached before the item line."""

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
                object.__setattr__(self, "_item", item)
                object.__setattr__(self, "_item_line_index", i)
                break
        else:
            raise ValueError(f"No list item found in hunk: {self.lines!r}")
        return item, i

    @staticmethod
    def parse_item(line: str) -> str | None:
        """Return the item of the hunk if the line starts a list item, else None."""
        stripped = line.lstrip()
        if not stripped.startswith("- "):
            return None
        stripped = stripped[2:]  # remove the "- "
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


def parse_essential_list_items(contents: str | list[str]) -> tuple[list[ItemHunk], Hunk | None]:
    """Parse lines into list items hunks."""
    lines = contents.splitlines() if isinstance(contents, str) else contents
    hunks: list[ItemHunk] = []
    if not lines:
        return hunks
    parsed_hunks = parse_yaml_to_hunks(lines)
    comment_hunk: Hunk | None = None
    for i, hunk in enumerate(parsed_hunks):
        if i < len(parsed_hunks) - 1:
            ih = ItemHunk(lines=hunk.lines, start_line=hunk.start_line)
            hunks.append(ih)
        else:
            # last hunk.
            # it might be just a comment hunk with no item
            try:
                ih = ItemHunk(lines=hunk.lines, start_line=hunk.start_line)
                hunks.append(ih)
            except ValueError:
                if all(line.lstrip().startswith(COMMENT) or not line.strip() for line in hunk.lines):
                    comment_hunk = hunk
                else:
                    raise

    return hunks, comment_hunk


# def _split_keys_to_hunks(hunk: KeyHunk) -> list[KeyHunk]:
#     lines = hunk.lines[hunk.key_line_index + 1 :]
#     hunks: list[Hunk] = []
#     key_lines: list[int] = []
#     for i, line in enumerate(lines):
#         stripped = line.lstrip()
#         if KeyHunk.parse_key(stripped) is not None:
#             key_lines.append(i)
#     hunks = []
#     for i, start_line in enumerate(key_lines):
#         end_line = key_lines[i + 1] if i + 1 < len(key_lines) else len(lines)
#         hunk_lines = lines[start_line:end_line]
#         hunks.append(Hunk(lines=hunk_lines, start_line=hunk.start_line + 1 + hunk.key_line_index + start_line))
#     # convert to KeyHunk
#     return [KeyHunk(lines=h.lines, start_line=h.start_line) for h in hunks]


# def split_keys_to_hunks(hunk: KeyHunk) -> list[KeyHunk]:
#     """Just like parse_yaml_hunks_for_key, but splits the content lines into hunks for each key."""

#     def start_func(line: str) -> bool:
#         stripped = line.lstrip()
#         return KeyHunk.parse_key(stripped) is not None

#     def stop_func(start_line: str, next_line: str) -> bool:
#         start_stripped = start_line.lstrip()
#         start_indentation = len(start_line) - len(start_stripped)
#         next_stripped = next_line.lstrip()
#         next_indentation = len(next_line) - len(next_stripped)
#         if not next_stripped:
#             return False  # empty lines are part of the hunk
#         return next_indentation <= start_indentation

#     _hunks = parse_yaml_hunks(hunk.content, start_func, stop_func)
#     hunks = [KeyHunk(lines=h.lines, start_line=hunk.start_line + 1 + h.start_line) for h in _hunks]
#     # make sure the hunks are contiguous ...

#     return hunks


class Stage(Protocol):
    def __init__(self, contents: str, *, filename: str) -> None: ...

    def process(self) -> str: ...


class EssentialsSorter:
    def __init__(self, contents: str, *, filename: str) -> None:
        self.contents = contents
        self.filename = filename

    def _process(self) -> None:
        hunks = parse_yaml_hunks_for_key(self.contents, "essential")
        if not hunks:
            logging.debug(f"No 'essential' hunks found in '{self.filename}'")
            return

        for hunk in hunks:
            item_hunks, _ = parse_essential_list_items(hunk.lines[hunk.key_line_index + 1 :])
            items = [ih.item for ih in item_hunks]
            # unique_items = set(items)
            # if len(items) != len(unique_items):
            #     # print(items)
            #     duplicate_items = [item for item in items if items.count(item) > 1]
            #     logging.warning(
            #         f"'essential' key at lines {hunk.start_line + 1}-{hunk.end_line} "
            #         f"in '{self.filename}' has duplicate items: {set(duplicate_items)}"
            #     )
            #     continue
            sorted_items = sort_by_bytes(items)
            if items != sorted_items:
                logging.info(
                    f"'essential' key at lines {hunk.start_line + 1}-{hunk.end_line} "
                    f"in '{self.filename}' is not sorted. Should be:"
                )
                for v in sorted_items:
                    indent = " " * item_hunks[0].indentation
                    print(f"{indent}- {v}")

                # # create new hunk lines with sorted items
                # new_hunk_lines = [hunk.lines[0]]  # key line
                # indentation = " " * (len(hunk.lines[0]) - len(hunk.lines[0].lstrip()) + 2)  # +2 for "- "
                # for item in sorted_items:
                #     new_hunk_lines.append(f"{indentation}- {item}")
                # # preserve any trailing empty lines from the original hunk
                # for line in reversed(hunk.lines):
                #     if not line.strip():
                #         new_hunk_lines.append(line)
                #     else:
                #         break
                # new_hunk = replace(hunk, lines=new_hunk_lines)

                # # replace the hunk in contents
                # self.contents = (
                #     self.contents[: hunk.start_line]
                #     + "\n".join(new_hunk.lines)
                #     + self.contents[hunk.end_line :]
                # )

    def process(self) -> str:
        self._process()
        return self.contents


if TYPE_CHECKING:
    _essentials_sorter: Stage = EssentialsSorter.__new__(EssentialsSorter)


class ContentsSorter:
    def __init__(self, contents: str, *, filename: str) -> None:
        self.contents = contents
        self.filename = filename

    def _process(self) -> None:
        hunks = parse_yaml_hunks_for_key(self.contents, "contents")
        if not hunks:
            logging.debug(f"No 'contents' hunks found in '{self.filename}'")
            return
        for hunk in hunks:
            key_hunks = _split_keys_to_hunks(hunk)
            keys = [kh.key for kh in key_hunks]
            sorted_keys = sort_by_bytes(keys)
            if keys != sorted_keys:
                logging.info(
                    f"'contents' key at lines {hunk.start_line + 1}-{hunk.end_line} "
                    f"in '{self.filename}' is not sorted. Should be:"
                )
                for k in sorted_keys:
                    indent = " " * key_hunks[0].indentation
                    print(f"{indent}{k}:")

                # Find the first difference and log it
                for i, (k1, k2) in enumerate(zip(keys, sorted_keys)):
                    if k1 != k2:
                        logging.info(f"First difference at position {i}: '{k1}' should be '{k2}'")
                        break

    def process(self) -> str:
        self._process()
        return self.contents


if TYPE_CHECKING:
    _contents_sorter: Stage = ContentsSorter.__new__(ContentsSorter)


class CopyrightSliceExists(Stage):
    def __init__(self, contents: str, *, filename: str) -> None:
        self.contents = contents
        self.filename = filename

    def _process(self) -> None:
        hunks = parse_yaml_hunks_for_key(self.contents, "copyright")
        if not hunks:
            logging.info(f"No 'copyright' hunk found in '{self.filename}'")
            return

    def process(self) -> str:
        self._process()
        return self.contents


if TYPE_CHECKING:
    _copyright_slice_exists: Stage = CopyrightSliceExists.__new__(CopyrightSliceExists)


class CopyrightSliceIsLast(Stage):
    def __init__(self, contents: str, *, filename: str) -> None:
        self.contents = contents
        self.filename = filename

    def _process(self) -> None:
        copyright_hunks = parse_yaml_hunks_for_key(self.contents, "copyright")
        if not copyright_hunks:
            logging.debug(f"No 'copyright' hunk found in '{self.filename}'")
            return

        if len(copyright_hunks) > 1:
            logging.warning(f"Multiple 'copyright' hunks found in '{self.filename}'")
            return

        copyright_hunk = copyright_hunks[0]

        slices_hunks = parse_yaml_hunks_for_key(self.contents, "slices")
        if not slices_hunks:
            logging.debug(f"No 'slices' hunk found in '{self.filename}'")
            return

        if len(slices_hunks) > 1:
            logging.warning(f"Multiple 'slices' hunks found in '{self.filename}'")
            return

        slices_hunk = slices_hunks[0]

        slices_key_hunks = _split_keys_to_hunks(slices_hunk)

        # the last key_hunk should be a copyright hunk
        last_key_hunk = slices_key_hunks[-1]
        if copyright_hunk != last_key_hunk:
            # print('---')
            # print(self.filename)
            # print(copyright_hunk)
            # print(last_key_hunk)
            logging.info(
                f"'copyright' hunk at lines {copyright_hunk.start_line + 1}-{copyright_hunk.end_line} "
                f"in '{self.filename}' is not the last slice. It should be after the last slice "
                f"at lines {last_key_hunk.start_line + 1}-{last_key_hunk.end_line}."
            )

    def process(self) -> str:
        self._process()
        return self.contents


if TYPE_CHECKING:
    _copyright_slice_is_last: Stage = CopyrightSliceIsLast.__new__(CopyrightSliceIsLast)


class SliceKeysOrder(Stage):
    def __init__(self, contents: str, *, filename: str) -> None:
        self.contents = contents
        self.filename = filename

    def _process(self) -> None:
        slices_hunks = parse_yaml_hunks_for_key(self.contents, "slices")
        if not slices_hunks:
            logging.debug(f"No 'slices' hunk found in '{self.filename}'")
            return

        if len(slices_hunks) > 1:
            logging.warning(f"Multiple 'slices' hunks found in '{self.filename}'")
            return

        slices_hunk = slices_hunks[0]
        slice_key_hunks = _split_keys_to_hunks(slices_hunk)

        for slice_hunk in slice_key_hunks:
            key_hunks = _split_keys_to_hunks(slice_hunk)
            if not key_hunks:
                logging.warning(
                    f"No keys found in slice at lines {slice_hunk.start_line + 1}-{slice_hunk.end_line} in '{self.filename}'"
                )
                continue
            # we can have up to two keys: 'essential' and 'contents'
            # If both are present, 'essential' must come first
            keys = [kh.key for kh in key_hunks]
            # allowed keys in the order they should appear
            allowed_keys = ["essential", "contents", "mutate"]
            if len(keys) > len(allowed_keys):
                logging.warning(
                    f"Too many keys {keys} in slice at lines "
                    f"{slice_hunk.start_line + 1}-{slice_hunk.end_line} in '{self.filename}'. "
                    f"Allowed keys are 'essential' and 'contents'. Got {keys}."
                )
                continue
            if not all(k in allowed_keys for k in keys):
                logging.warning(
                    f"Unexpected keys {keys} in slice at lines "
                    f"{slice_hunk.start_line + 1}-{slice_hunk.end_line} in '{self.filename}'. "
                    f"Allowed keys are 'essential' and 'contents'. Got {keys}."
                )
                continue
            if keys != sorted(keys, key=lambda k: allowed_keys.index(k)):
                logging.info(
                    f"Keys {keys} in slice at lines "
                    f"{slice_hunk.start_line + 1}-{slice_hunk.end_line} in '{self.filename}' "
                    f"are not in the correct order. Should be:"
                )
                for k in allowed_keys:
                    if k in keys:
                        indent = " " * key_hunks[0].indentation
                        print(f"{indent}{k}:")

            # There should be no gap between the keys hunks
            for i in range(len(key_hunks) - 1):
                this_hunk = key_hunks[i]
                next_hunk = key_hunks[i + 1]
                # if key_hunks[i].end_line != key_hunks[i + 1].start_line:
                #     logging.warning(
                #         f"Unexpected gap between keys '{key_hunks[i].key}' and '{key_hunks[i + 1].key}' "
                #         f"in slice at lines {slice_hunk.start_line + 1}-{slice_hunk.end_line} in '{self.filename}'. "
                #         f"Lines {key_hunks[i].end_line + 1}-{key_hunks[i + 1].start_line} are empty."
                #     )
                if this_hunk.end_line != next_hunk.start_line:
                    # TODO: hunks are not contiguous so we trigger on comments etc
                    logging.warning(
                        f"Unexpected gap between keys '{this_hunk.key}' and '{next_hunk.key}' "
                        f"in slice at lines {slice_hunk.start_line + 1}-{slice_hunk.end_line} in '{self.filename}'. "
                        f"Lines {this_hunk.end_line + 1}-{next_hunk.start_line} are empty."
                    )

    def process(self) -> str:
        self._process()
        return self.contents


if TYPE_CHECKING:
    _slice_keys_order: Stage = SliceKeysOrder.__new__(SliceKeysOrder)


class NoGapBetweenSlicesKeyAndContents(Stage):
    def __init__(self, contents: str, *, filename: str) -> None:
        self.contents = contents
        self.filename = filename

    def _process(self) -> None:
        slices_hunks = parse_yaml_hunks_for_key(self.contents, "slices")
        if not slices_hunks:
            logging.debug(f"No 'slices' hunk found in '{self.filename}'")
            return

        if len(slices_hunks) > 1:
            logging.warning(f"Multiple 'slices' hunks found in '{self.filename}'")
            return

        slices_hunk = slices_hunks[0]
        slice_key_hunks = _split_keys_to_hunks(slices_hunk)

        if not slice_key_hunks:
            logging.warning(f"No slice keys found in 'slices' hunk in '{self.filename}'")
            return

        first_key_hunk = slice_key_hunks[0]

        if slices_hunk.start_line + 1 != first_key_hunk.start_line:
            # logging.warning(
            #     f"Unexpected gap between 'slices:' key and the first slice key "
            #     f"in '{self.filename}'. Lines {slices_hunk.start_line + 1}-{first_key_hunk.start_line} are empty."
            # )
            # TODO: for now the hunks parsing + comments is not quite right,
            #       so we need to namually go through the lines to check for gaps
            lines_in_between = slices_hunk.lines[1 : first_key_hunk.start_line - slices_hunk.start_line]
            # make sure all lines in between are comments. They should not be empty
            stripped_lines = [line.strip() for line in lines_in_between if line.strip()]
            if any(line and not line.startswith(COMMENT) for line in stripped_lines):
                logging.warning(
                    f"Unexpected gap between 'slices:' key and the first slice key "
                    f"in '{self.filename}'. Lines {slices_hunk.start_line + 1}-{first_key_hunk.start_line} are empty."
                )

    def process(self) -> str:
        self._process()
        return self.contents


if TYPE_CHECKING:
    _no_gap_between_slices_key_and_contents: Stage = NoGapBetweenSlicesKeyAndContents.__new__(
        NoGapBetweenSlicesKeyAndContents
    )


class FilesHaveNewlineAtEnd(Stage):
    def __init__(self, contents: str, *, filename: str) -> None:
        self.contents = contents
        self.filename = filename

    def _process(self) -> None:
        lines = self.contents.splitlines()
        if not lines:
            logging.warning(f"File '{self.filename}' is empty.")
            return
        # print(f"===='{self.filename}'====")
        # print(lines[-2].replace(" ", "."))
        # print(lines[-1].replace(" ", "."))

        trailing_newlines = 0
        for line in reversed(self.contents):
            stripped = line.strip()
            if not stripped:
                trailing_newlines += 1
            else:
                break
        # print(f"trailing_newlines: {trailing_newlines}")

        # if len(lines[-1]) > 0 and lines[-1][-1] == "\n":
        #     # last line ends with a newline, so we have at least one trailing newline
        #     trailing_newlines = 1
        # for line in reversed(lines):
        #     if line.strip():
        #         break
        #     trailing_newlines += 1
        if trailing_newlines == 0:
            logging.info(f"File '{self.filename}' does not end with a newline.")
        elif trailing_newlines > 1:
            logging.info(f"File '{self.filename}' has {trailing_newlines} trailing newlines. Should have exactly one.")

    def process(self) -> str:
        self._process()
        return self.contents


if TYPE_CHECKING:
    _files_have_newline_st_end: Stage = FilesHaveNewlineAtEnd.__new__(FilesHaveNewlineAtEnd)


def test_all_slices(directory: Path) -> None:
    slices_dir = directory / "slices"
    if not slices_dir.is_dir():
        raise FileNotFoundError(f"'slices' directory not found in {directory}")

    # list all the .yaml files in the slices directory
    yaml_files = list(slices_dir.glob("*.yaml"))
    if not yaml_files:
        logging.warning(f"No .yaml files found in {slices_dir}")
        return

    logging.info(f"Found {len(yaml_files)} .yaml files in {slices_dir}")

    stages: list[type[Stage]] = [
        EssentialsSorter,
        # ContentsSorter,
        CopyrightSliceExists,
        # CopyrightSliceIsLast,
        # SliceKeysOrder,
        # NoGapBetweenSlicesKeyAndContents,
    ]

    for yaml_file in yaml_files:
        relative_path = yaml_file.relative_to(directory)
        # if yaml_file.name != "dpkg.yaml":
        #     continue
        contents = yaml_file.read_text()

        logging.debug(f"Processing file: {relative_path}")

        for stage_cls in stages:
            # contents = stage(contents, filename=str(yaml_file))
            stage = stage_cls(contents, filename=str(relative_path))
            contents = stage.process()


def test_all_test_files(directory: Path) -> None:
    tests_dir = args.directory / "tests" / "spread" / "integration"
    if not tests_dir.is_dir():
        raise FileNotFoundError(f"'tests' directory not found in {args.directory}")

    # get all the .sh files in the tests directory and its subdirectories
    _bash_scripts = list(tests_dir.rglob("**/*.sh"))


def test_all_files(directory: Path) -> None:
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
            contents = stage.process()


## MAIN ########################################################################


def main(args: argparse.Namespace) -> None:
    # check there is a 'slices' directory

    test_all_slices(args.directory)
    test_all_test_files(args.directory)
    test_all_files(args.directory)


################################################################################

## BOILERPLATE #################################################################


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sort slices in SDFs",
    )

    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("directory", type=Path, help="chisel-releases directory")
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
