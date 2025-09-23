from bash_dep_finder import commands_in_script


def test_commands_in_script() -> None:
    script = """#!/bin/bash
# Sample Bash script
echo "Hello, World!"
my_function() {
    ls -l
    grep "pattern" file.txt
}
my_function
if [ -f "somefile" ]; then
    cat somefile
fi
"""
    expected_commands = {
        "ls": [5],
        "grep": [6],
        "cat": [10],
    }
    result = commands_in_script(script)
    assert result == expected_commands
