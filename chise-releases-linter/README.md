# chisel-releases-linter

Script to lint [`chisel-releases`](https://https://github.com/canonical/chisel-releases/) repo.

Tested in Python 3.9+.

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