# bash_dep_finder

Find dependencies of a bash script.

Can also output to `--json` and accept multiple files as input.

Tested in Python 3.9+.


```bash
$ bash_dep_finder --lines some_example_script.sh
cat 16
mktemp 40
apt 45,69,69,75
find 47,216
mv 50,114,122,138,146
sudo 71,71,77
tree 94,165
rm 99,111,118,126,135,142,150,156
mkdir 101,113,121,137,145
cp 102
ar 107
tar 110,117,125,134,141,149
ls 168
fzf 216,222
apt-cache 222
cut 222
```

# Installation

The easiest way to use the tool is with [`uvx`](https://docs.astral.sh/uv/guides/tools/):

```bash
uvx --from git+https://github.com/lczyk/rocks-toolbox@bash_dep_finder#subdirectory=bash_dep_finder bash_dep_finder --help
```

or installing it first

```bash
uv tool install git+https://github.com/lczyk/rocks-toolbox@bash_dep_finder#subdirectory=bash_dep_finder
```

Here is a all-in-one scriptlet for bootstrapping uv in a container:

```bash
apt update || sudo apt update
apt install -y curl git || sudo apt install -y curl git
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
uv tool install git+https://github.com/lczyk/rocks-toolbox@bash_dep_finder#subdirectory=bash_dep_finder
```

There are also snap instructions in the `snap` folder, or you can build and install python wheel from this folder in all the usual ways.

<!-- spellchecker: ignore venv pytest mypy -->
## Testing and development

Setup with:

```bash
uv sync && source .venv/bin/activate
```

Test with:

```bash
pytest
```

Format and typecheck with:


```bash
ruff format . && ruff check --fix . && mypy
```


### Tox

To test with [tox](https://tox.wiki/en/latest/index.html), I recommend [tox-uv](https://github.com/tox-dev/tox-uv):

```bash
uv tool install tox --with tox-uv # use uv to install
```

and then just

```bash
tox
```

## TODO

- [ ] `bash`/`dash` mode
- [ ] add a list of known sources to suggest (eg.coreutils, sed, awk etc)
- [ ] test all the bash keywords work by themselves in a rootless env