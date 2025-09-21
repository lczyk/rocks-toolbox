import textwrap

from src.chisel_releases_linter import Hunk, ItemHunk, KeyHunk, parse_yaml_to_hunks


def inline_yaml(yaml_str: str, indent: int = 0) -> str:
    yaml_str = textwrap.dedent(yaml_str)
    # remove leading/trailing newlines
    yaml_str = yaml_str.strip("\n")
    # make sure it ends with a newline
    yaml_str += "\n"
    # Add indentation if needed
    if indent > 0:
        yaml_str = textwrap.indent(yaml_str, " " * indent)
    return yaml_str


def p(s: str, indent: int = 0) -> list[Hunk]:
    return parse_yaml_to_hunks(inline_yaml(s, indent=indent))


def h(s: str, start_line: int = 1, indent: int = 0) -> Hunk:
    return Hunk.from_string(inline_yaml(s, indent=indent), start_line=start_line)


def kh(s: str, start_line: int = 1, indent: int = 0) -> KeyHunk:
    return KeyHunk.from_string(inline_yaml(s, indent=indent), start_line=start_line)


def ih(s: str, start_line: int = 1, indent: int = 0) -> ItemHunk:
    return ItemHunk.from_string(inline_yaml(s, indent=indent), start_line=start_line)
