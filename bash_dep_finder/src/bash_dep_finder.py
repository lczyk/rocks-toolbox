import argparse
import os
import sys

import tree_sitter_bash
from tree_sitter import Language, Node, Parser

LANGUAGE = Language(tree_sitter_bash.language())

# spellchecker: ignore Marcin Konowalczyk lczyk
__author__ = "Marcin Konowalczyk @lczyk"
__version__ = "0.1.2"

__all__ = ["commands_in_script"]

# spellchecker: ignore coproc esac
# https://www.gnu.org/software/bash/manual/html_node/Reserved-Words.html
_KEYWORDS = """
if then elif else fi time for in until while do done case esac coproc
select function { } [[ ]] !
"""
KEYWORDS: set[str] = set(_KEYWORDS.split())

# spellchecker: ignore getopts shopt unalias mapfile readarray compgen compopt pushd popd
# https://github.com/bminor/bash/tree/master/builtins
_BUILTINS = """
hash echo bind getopts export readonly exit logout printf cd pwd shopt type
trap set unset alias unalias mapfile readarray jobs disown history builtin
command ulimit shift declare typeset local ! for for (( select time case if
while until coproc function { } % (( )) [[ ]] variables caller fc : true
false exec umask suspend let complete compgen compopt source . break continue
wait read fg bg help enable eval pushd popd dirs times kill test [ return
"""

BUILTINS: set[str] = set(_BUILTINS.split())

## MAIN ##


def commands_in_script(script_source: "str | bytes") -> dict[str, list[int]]:
    _script_source: bytes
    if isinstance(script_source, str):  # noqa: SIM108
        _script_source = script_source.encode("utf-8")
    else:
        _script_source = script_source
    parser = Parser(LANGUAGE)
    tree = parser.parse(_script_source)
    root_node = tree.root_node

    commands: list[tuple[str, int]] = []
    function_definitions: set[str] = set()

    def extract_commands(node: Node) -> None:
        if node.type == "command":
            command_name_node = node.child_by_field_name("name")
            if command_name_node:
                text_bytes = command_name_node.text
                if text_bytes:
                    command = text_bytes.decode("utf-8")
                    lineno = command_name_node.start_point[0] + 1
                    commands.append((command, lineno))
        elif node.type == "function_definition":
            func_name_node = node.child_by_field_name("name")
            if func_name_node:
                test_bytes = func_name_node.text
                if test_bytes:
                    function_definitions.add(test_bytes.decode("utf-8"))
        for child in node.children:
            extract_commands(child)

    extract_commands(root_node)

    # group by command name
    command_dict: dict[str, list[int]] = {}
    for cmd, lineno in commands:
        if cmd not in command_dict:
            command_dict[cmd] = []
        command_dict[cmd].append(lineno)

    # Filter out function definitions, keywords, and builtins
    def filter_command(cmd: str) -> bool:
        if cmd in function_definitions:
            return False
        if cmd in KEYWORDS:
            return False
        return cmd not in BUILTINS

    command_dict = {cmd: lines for cmd, lines in command_dict.items() if filter_command(cmd)}

    return command_dict


def main() -> None:
    args = parse_args()

    # Collect commands from all scripts
    command_dict: dict[str, dict[str, list[int]]] = {}
    for script in args.scripts:
        if not os.path.isfile(script):
            print(f"Error: {script} is not a valid file.", file=sys.stderr)
            sys.exit(1)
        with open(script, encoding="utf-8") as f:
            script_source = f.read()
        script_commands = commands_in_script(script_source)
        command_dict[script] = script_commands

    # Print to stdout. Make sure we work with pipes.
    # https://docs.python.org/3/library/signal.html#note-on-sigpipe
    # spellchecker: ignore WRONLY
    try:
        print(format_result(command_dict, args.format, args.lines))
        sys.stdout.flush()
    except BrokenPipeError:
        # Gracefully handle broken pipe when e.g. piping to head
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        sys.exit(1)


def format_result(
    command_dict: dict[str, dict[str, list[int]]],
    fmt: str,
    lines: bool = False,
) -> str:
    out: str = ""
    if fmt == "plain":
        for script, commands in command_dict.items():
            out += f"# {script}\n"
            if lines:
                for cmd, lineno in commands.items():
                    out += cmd + " " + ",".join(map(str, sorted(lineno))) + "\n"
            else:
                for cmd in sorted(commands.keys()):
                    out += f"{cmd}\n"

    elif fmt == "json":
        # NOTE: json output always includes line numbers if --lines is set
        import json  # noqa: PLC0415

        # sort line numbers for consistency
        # command_dict = {cmd: sorted(lines) for cmd, lines in command_dict.items()}
        # json_output = {cmd: lines for cmd, lines in sorted(command_dict.items())}
        json_output: list[dict] = []
        for script, commands in command_dict.items():
            entry = {"script": script, "commands": {}}
            for cmd, lineno in commands.items():
                entry["commands"][cmd] = sorted(lineno)  # type: ignore[index]
            json_output.append(entry)
        out = json.dumps(json_output, indent=2)
    else:
        raise ValueError(f"Unknown format: {fmt}")

    # remove trailing newline
    out = out.rstrip("\n")
    return out


## BOILERPLATE ##


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Find dependencies in a Bash script.")
    parser.add_argument("scripts", nargs="+", type=str, help="Path to the Bash script to analyze.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--lines", action="store_true", help="Show line numbers where commands are used.")

    # Custom type for --format argument
    def format_type(fmt: str) -> str:
        fmt = fmt.lower()
        if fmt not in {"plain", "json"}:
            raise argparse.ArgumentTypeError(f"Invalid format: {fmt}. Choose from plain or json.")
        return fmt

    parser.register("type", "format", format_type)
    parser.add_argument(
        "--format",
        type="format",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format. Shorthand for --format=json.",
    )

    args = parser.parse_args()
    if args.json and args.format:
        parser.error("Cannot use --json and --format together.")
    elif args.json:
        args.format = "json"
    if not args.format:
        args.format = "plain"
    return args


## ENTRYPOINT ##

if __name__ == "__main__":
    main()
