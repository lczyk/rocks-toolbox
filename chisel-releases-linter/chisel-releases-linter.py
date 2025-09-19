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
from typing import TYPE_CHECKING, Callable, Protocol

__version__ = "0.0.0"
__author__ = "Marcin Konowalczyk"

__changelog__ = [
    ("0.0.0", "boilerplate", "@lczyk"),
]


################################################################################

# adapted from https://github.com/lczyk/find_in_json v0.1.0

_missing = object()
_any = object()
ANY = _any


def find_in_json(
    json: object,
    *,
    key: str | int | None = None,
    value: object = _any,
) -> list[list[str | int]]:
    """Find all instances in a JSON object (dict or list) matching the given key and/or value.
    Returns a list of "paths" to the matching elements, where each path is a list of keys and/or
    indices. If no matches are found, returns an empty list. If no key
    and no value is specified, returns the list of all paths in the JSON object."""
    key = None if key is ANY else key  # should not happen, but let's not break
    if key is None and value is _any:
        matcher = lambda k, v: True  # noqa: E731
    elif key is None and value is not _any:
        matcher = lambda k, v: v == value  # noqa: E731
    elif key is not None and value is _any:
        matcher = lambda k, v: k == key  # noqa: E731
    else:
        matcher = lambda k, v: k == key and v == value  # noqa: E731

    return _find_in_json(json, matcher, None, None)


def path_to_str(path: Path) -> str:
    """Convert a path (list of keys and indices) to a dot-separated string representation."""
    parts: list[str] = [f"[{p}]" if isinstance(p, int) else str(p) for p in path]
    return ".".join(parts)


def str_to_path(path: str) -> Path:
    """Convert a dot-separated string representation of a path to a list of keys and indices."""
    parts = path.split(".")
    result: Path = []
    for part in parts:
        if part.startswith("[") and part.endswith("]"):
            index_str = part[1:-1]
            result.append(int(index_str))
        else:
            result.append(part)
    return result


def get_by_path(
    data: object,
    path: Path,
    *,
    default: object = _missing,
    wrap_index: bool = True,
    raise_error: bool = True,
) -> object:
    """Get the value from a JSON object (dict or list) by the given path.
    If the path is invalid, returns an error message
    and a missing value object. If the path is valid, returns an empty error message and the value.
    If wrap is True, negative indices and indices greater than the length of the list are wrapped around."""
    msg, value = _get_by_path(data, path, wrap_index)
    if msg:
        if default is not _missing:
            return default
        elif raise_error:
            raise KeyError(msg)
        else:
            # NOTE: this is a bit hairy, since None is a valid value, but i guess if someone
            #       does not set the default and sets raise_error to False, they know what they are doing
            return None
    return value


def set_by_path(
    data: object,
    path: Path,
    value: object,
    *,
    wrap_index: bool = True,
    raise_error: bool = True,
) -> bool:
    """Set the value in a JSON object (dict or list) by the given path.
    If the path is invalid, returns an error message. If the path is valid, sets the value and returns True.
    """

    msg = _set_by_path(data, path, value, wrap_index)
    if msg and raise_error:
        raise KeyError(msg)
    return msg == ""


### Internal ###########################################################################################################


# list[str | int]: TypeAlias = "list[str | int]"


def _find_in_json(
    json: object,
    matcher_fun: Callable[[str | int, object], bool],
    _matches: list[list[str | int]] | None,
    _stack: list[str | int] | None,
) -> list[list[str | int]]:
    matches: list[list[str | int]] = _matches if _matches is not None else []
    stack: list[str | int] = _stack if _stack is not None else []

    if isinstance(json, dict):
        for k, v in json.items():
            stack = [*stack, k] if stack else [k]
            if matcher_fun(k, v):
                matches.append(stack.copy())
            _find_in_json(v, matcher_fun, matches, stack)
            stack.pop()

    elif isinstance(json, list):
        for key, v in enumerate(json):
            stack = [*stack, key] if stack else [key]
            if matcher_fun(key, v):
                matches.append(stack.copy())
            _find_in_json(v, matcher_fun, matches, stack)
            stack.pop()
    else:
        pass

    return matches


def _wrap_index(index: int, N: int) -> int:
    # wrap around once
    index = index + N if index < 0 else index
    index = index - N if index >= N else index
    return index


def _get_by_path(json: object, path: Path, wrap: bool = True) -> tuple[str, object]:
    current = json
    for part in path:
        if isinstance(current, dict):
            if not isinstance(part, str):
                return f"Invalid path. Expected string key for dict, got {part!r}", _missing
            value = current.get(part, _missing)
            if value is _missing:
                return f"Key not found: {part!r}", _missing
            current = value
        elif isinstance(current, list):
            if not isinstance(part, int):
                return f"Invalid path. Expected integer index for list, got {part!r}", _missing
            index = _wrap_index(part, len(current)) if wrap else part
            if index < 0 or index >= len(current):
                return f"Index out of range: {index}", _missing
            current = current[index]
        else:
            return f"Invalid path. Expected dict or list, got {current!r}", _missing
    return "", current


def _set_by_path(json: object, path: Path, value: object, wrap: bool = True) -> str:
    current = json
    for i, part in enumerate(path):
        if i == len(path) - 1:
            # last part, set the value
            if isinstance(current, dict):
                if not isinstance(part, str):
                    return f"Invalid path. Expected string key for dict, got {part!r}"
                current[part] = value
                return ""
            elif isinstance(current, list):
                if not isinstance(part, int):
                    return f"Invalid path. Expected integer index for list, got {part!r}"
                index = _wrap_index(part, len(current)) if wrap else part
                if index < 0 or index >= len(current):
                    return f"Index out of range: {index}"
                current[index] = value
                return ""
            else:
                return f"Invalid path. Expected dict or list, got {current!r}"
        # traverse the path
        elif isinstance(current, dict):
            if not isinstance(part, str):
                return f"Invalid path. Expected string key for dict, got {part!r}"
            if part not in current or not isinstance(current[part], (dict, list)):
                # create a new dict if the key does not exist or is not a dict/list
                current[part] = {}
            current = current[part]
        elif isinstance(current, list):
            if not isinstance(part, int):
                return f"Invalid path. Expected integer index for list, got {part!r}"
            index = _wrap_index(part, len(current)) if wrap else part
            if index < 0 or index >= len(current):
                return f"Index out of range: {index}"
            if not isinstance(current[index], (dict, list)):
                # create a new dict if the element is not a dict/list
                current[index] = {}
            current = current[index]
        else:
            return f"Invalid path. Expected dict or list, got {current!r}"
    return ""


################################################################################


def sort_by_bytes(slices: list[str]) -> list[str]:
    """Sort in the same way LC_ALL=C sort works in the shell."""
    return sorted(slices, key=lambda s: s.encode("utf-8"))


# def sort_slices(data: dict) -> tuple[bool, dict]:
#     ok = True
#     essential_key_paths = find_in_json(data, key="essential")
#     for path in essential_key_paths:
#         value = get_by_path(data, path)
#         if not isinstance(value, list):
#             logging.error(f"Invalid 'essential' key at path {path_to_str(path)}: expected a list, got {value!r}")
#             ok = False
#             continue
#         sorted_value = sort_by_bytes(value)
#         if value != sorted_value:
#             logging.info(f"'essential' key at path {path_to_str(path)} is not sorted. Should be:")
#             for v in sorted_value:
#                 print(f" - {v}")
#             ok = False
#             # update the data with the sorted value
#             set_by_path(data, path, sorted_value)

#     contents_key_paths = find_in_json(data, key="contents")
#     for path in contents_key_paths:
#         value = get_by_path(data, path)
#         if not isinstance(value, dict):
#             logging.error(f"Invalid 'contents' key at path {path_to_str(path)}: expected a dict, got {value!r}")
#             ok = False
#             continue
#         keys = list(value.keys())
#         sorted_keys = sort_by_bytes(keys)
#         if keys != sorted_keys:
#             logging.info(f"'contents' key at path {path_to_str(path)} is not sorted. Should be:")
#             for k in sorted_keys:
#                 print(f" {k}")
#             ok = False
#             # update the data with the sorted value
#             sorted_dict = {k: value[k] for k in sorted_keys}
#             set_by_path(data, path, sorted_dict)

#     return ok, data


@dataclass(frozen=True)
class Hunk:
    """Represents a key in yaml, and its associated lines."""

    start_line: int = field()
    lines: list[str] = field(repr=False)

    def __post_init__(self) -> None:
        if not self.lines:
            raise ValueError("Hunk must have at least one line.")

        # Make sure the hunk does not end with any empty lines
        for i in range(len(self.lines) - 1, -1, -1):
            line = self.lines[i]
            if line.strip():
                break
        else:
            raise ValueError("Hunk cannot be empty or only whitespace.")

    @property
    def end_line(self) -> int:
        return self.start_line + len(self.lines)  # exclusive

    @property
    def indentation(self) -> int:
        return len(self.lines[0]) - len(self.lines[0].lstrip())

    @property
    def whole(self) -> str:
        return "\n".join(self.lines)

    def __repr__(self) -> str:
        return f"Hunk({self.start_line + 1}-{self.end_line})"


@dataclass(frozen=True)
class KeyHunk(Hunk):
    """Represents a key in yaml, and its associated lines."""

    def __post_init__(self) -> None:
        super().__post_init__()
        _ = self._parse_key()

    def _parse_key(self) -> tuple[str, int]:
        for i, line in enumerate(self.lines):
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
        if not stripped or stripped.startswith("#"):
            return None
        if ":" not in stripped:
            return None
        key = stripped.split(":", 1)[0].rstrip()
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
        return f"YamlKeyHunk({self.key}, {self.start_line + 1}-{self.end_line})"

    @property
    def content_lines(self) -> list[str]:
        """Return the lines of the hunk, excluding the key line."""
        return self.lines[self.key_line_index + 1 :]

    @property
    def content(self) -> str:
        """Return the content of the hunk as a single string, excluding the key line."""
        return "\n".join(self.content_lines)


@dataclass(frozen=True)
class ListItemHunk(Hunk):
    """Represents a list item in yaml, and its associated lines."""

    def __post_init__(self) -> None:
        super().__post_init__()
        _ = self._parse_item()

    def _parse_item(self) -> str:
        for line in self.lines:
            item = self.parse_item(line)
            if item is not None:
                object.__setattr__(self, "_item", item)
                break
        else:
            raise ValueError(f"No list item found in hunk: {self.lines!r}")
        return item

    @staticmethod
    def parse_item(line: str) -> str | None:
        """Return True if the line starts a list item, else False."""
        stripped = line.lstrip()
        if not stripped.startswith("- "):
            return None
        stripped = stripped[2:]  # remove the "- "
        # it may have a comment at the end
        if "#" in stripped:
            stripped = stripped.split("#", 1)[0].rstrip()
        return stripped if stripped else None

    @property
    def item(self) -> str:
        item = getattr(self, "_item", None)
        if item is None:
            item = self._parse_item()
        return item

    def __repr__(self) -> str:
        return f"ListItemHunk({self.start_line + 1}-{self.end_line})"


def parse_yaml_hunks(
    contents: str,
    start_func: Callable[[str], bool],
    stop_func: Callable[[str, str], bool],
) -> list[Hunk]:
    """General function to parse yaml hunks based on start and stop functions."""
    lines = contents.splitlines()
    hunks: list[Hunk] = []

    i = 0
    while i < len(lines):
        line = lines[i]
        # stripped = line.lstrip()
        # if stripped.startswith(f"{key}:"):
        if start_func(line):
            # start of a hunk
            start_line = i
            hunk_lines = [line]
            i += 1
            # collect all lines that are indented more than the key line
            # start_indentation = len(line) - len(stripped)
            while i < len(lines):
                next_line = lines[i]
                # next_stripped = next_line.lstrip()
                # next_indentation = len(next_line) - len(next_stripped)
                if stop_func(line, next_line):
                    break
                else:
                    # if next_indentation > start_indentation or not next_stripped:
                    hunk_lines.append(next_line)
                    i += 1
                # else:
                #     break
            hunks.append(Hunk(lines=hunk_lines, start_line=start_line))
        else:
            i += 1

    # Go through all the hunks and remove any trailing empty lines
    for idx, hunk in enumerate(hunks):
        lines = hunk.lines
        while lines and not lines[-1].strip():
            lines.pop()
        if not lines:
            raise ValueError("Hunk cannot be empty after removing trailing empty lines.")
        hunks[idx] = replace(hunk, lines=lines)

    return hunks


def parse_yaml_hunks_for_key(contents: str, key: str) -> list[KeyHunk]:
    """Parse the contents of a yaml file and extract hunks for the given key."""

    def start_func(line: str) -> bool:
        stripped = line.lstrip()
        return stripped.startswith(f"{key}:")

    def stop_func(start_line: str, next_line: str) -> bool:
        start_stripped = start_line.lstrip()
        start_indentation = len(start_line) - len(start_stripped)
        next_stripped = next_line.lstrip()
        next_indentation = len(next_line) - len(next_stripped)
        if not next_stripped:
            return False  # empty lines are part of the hunk
        return next_indentation <= start_indentation

    hunks = parse_yaml_hunks(contents, start_func, stop_func)

    # Make sure the hunks are
    return [KeyHunk(lines=h.lines, start_line=h.start_line) for h in hunks]


# def parse_yaml_hunks_for_list_key(contents: str, key: str) -> list[YamlKeyHunk]:
# def parse_list_items(lines: list[str]) -> list[ListItem]:
def split_list_items_to_hunks(hunk: KeyHunk) -> list[ListItemHunk]:
    lines = hunk.content_lines
    hunks: list[Hunk] = []
    item_lines: list[int] = []

    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("- "):
            item_lines.append(i)

    hunks = []
    for i, start_line in enumerate(item_lines):
        end_line = item_lines[i + 1] if i + 1 < len(item_lines) else len(lines)
        hunk_lines = lines[start_line:end_line]
        hunks.append(Hunk(lines=hunk_lines, start_line=hunk.start_line + 1 + start_line))

    # convert to ListItemHunk
    return [ListItemHunk(lines=h.lines, start_line=h.start_line) for h in hunks]


def split_keys_to_hunks(hunk: KeyHunk) -> list[KeyHunk]:
    """Just like parse_yaml_hunks_for_key, but splits the content lines into hunks for each key."""

    def start_func(line: str) -> bool:
        stripped = line.lstrip()
        return KeyHunk.parse_key(stripped) is not None

    def stop_func(start_line: str, next_line: str) -> bool:
        start_stripped = start_line.lstrip()
        start_indentation = len(start_line) - len(start_stripped)
        next_stripped = next_line.lstrip()
        next_indentation = len(next_line) - len(next_stripped)
        if not next_stripped:
            return False  # empty lines are part of the hunk
        return next_indentation <= start_indentation

    _hunks = parse_yaml_hunks(hunk.content, start_func, stop_func)
    hunks = [KeyHunk(lines=h.lines, start_line=hunk.start_line + 1 + h.start_line) for h in _hunks]
    # make sure the hunks are contiguous ...

    return hunks


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
            item_hunks = split_list_items_to_hunks(hunk)
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
            key_hunks = split_keys_to_hunks(hunk)
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

        slices_key_hunks = split_keys_to_hunks(slices_hunk)

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
        slice_key_hunks = split_keys_to_hunks(slices_hunk)

        for slice_hunk in slice_key_hunks:
            key_hunks = split_keys_to_hunks(slice_hunk)
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
        slice_key_hunks = split_keys_to_hunks(slices_hunk)

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
            if any(line and not line.startswith("#") for line in stripped_lines):
                logging.warning(
                    f"Unexpected gap between 'slices:' key and the first slice key "
                    f"in '{self.filename}'. Lines {slices_hunk.start_line + 1}-{first_key_hunk.start_line} are empty."
                )

    def process(self) -> str:
        self._process()
        return self.contents

if TYPE_CHECKING:
    _no_gap_between_slices_key_and_contents: Stage = NoGapBetweenSlicesKeyAndContents.__new__(NoGapBetweenSlicesKeyAndContents)


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
        ContentsSorter,
        CopyrightSliceExists,
        CopyrightSliceIsLast,
        SliceKeysOrder,
        NoGapBetweenSlicesKeyAndContents,
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
