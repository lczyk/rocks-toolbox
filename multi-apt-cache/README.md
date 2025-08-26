# multi-apt-cache

Script to fetch and display package lists from Ubuntu repositories for specified ubuntu versions and components.
No dependencies outside of the standard library. Does not use apt or dpkg.

For now all the packages for all the versions and components are printed together to stdout.
In the future we could print them in some nice json format / print them separately / in a table etc.

Use the MULTI_APT_CACHE_DIR environment variable or --cache-dir argument to cache downloaded package lists.

For example:

```bash
MULTI_APT_CACHE_DIR=~/tmp/multi-apt-cache/ python3 ./multi_apt_cache.py --jobs=-1 --ubuntu=all --component=all
```

will display all the packages from all supported ubuntu versions and all four components.
This will take a lot of time. The answer ought to be at least 124009 packages (as of 25/08/25).

## Usage

Just copy the single file and run anywhere! :D

```bash
python ./src/availability_matrix.py
```

Tested in Python 3.9+.

## Testing and development

Setup with:

```bash
uv sync && source .venv/bin/activate
```

Test with:

```bash
pytest
```

To test with [tox](https://tox.wiki/en/latest/index.html), I recommend [tox-uv](https://github.com/tox-dev/tox-uv):

```bash
uv tool install tox --with tox-uv # use uv to install
```

and then just

```bash
tox
```
