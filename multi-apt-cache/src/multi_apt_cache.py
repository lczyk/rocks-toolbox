#!/usr/bin/env python3
"""
Script to fetch and display package lists from Ubuntu repositories for specified ubuntu versions and components.
No dependencies outside of the standard library. Does not use apt or dpkg.

For now all the packages for all the versions and components are printed together to stdout.
In the future we could print them in some nice json format / print them separately / in a table etc.

Use the MULTI_APT_CACHE_DIR environment variable or --cache-dir argument to cache downloaded package lists.

For example:

```
MULTI_APT_CACHE_DIR=~/tmp/multi-apt-cache/ python3 ./multi-apt-cache.py --ubuntu=all --component=all
```

will display all the packages from all supported ubuntu versions and all four components.
This will take a lot of time. The answer ought to be at least 124009 packages (as of 25/08/25).

"""

from __future__ import annotations

import argparse
import gzip
import io
import os
import re
import sys
from typing import Callable

__author__ = "Marcin Konowalczyk"
__version__ = "0.2.1"

__changelog__ = [
    (__version__, "add --jobs + other perf improvements", "@lczyk"),
    ("0.2.0", "change cache format to include version and deps", "@lczyk"),
    ("0.1.3", "add --repo option", "@lczyk"),
    ("0.1.2", "add --refresh-cache option", "@lczyk"),
    ("0.1.1", "retry with old-releases if not found in archive", "@lczyk"),
    ("0.1.0", "inital version", "@lczyk"),
]


# geturl from https://github.com/lczyk/geturl 0.4.4
def geturl(url: str) -> tuple[int, bytes]:
    """Make a GET request to a URL and return the response and status code."""

    import urllib
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(url) as r:
            code = r.getcode()
            res = r.read()

    except urllib.error.HTTPError as e:
        code = e.code
        res = e.read()

    assert isinstance(code, int), "Expected code to be int."
    assert isinstance(res, bytes), "Expected response to be bytes."

    return code, res


def get_package_content(name: str, component: str, repo: str) -> str:
    if component not in ("main", "restricted", "universe", "multiverse"):
        raise ValueError(
            f"Invalid component: {component}. Must be one of 'main', 'restricted', 'universe', or 'multiverse'."
        )
    if repo not in ("main", "security", "updates", "backports"):
        raise ValueError(f"Invalid repo: {repo}. Must be one of '', 'security', 'updates', or 'backports'.")

    if repo != "main":
        name = f"{name}-{repo}"

    package_url = f"https://archive.ubuntu.com/ubuntu/dists/{name}/{component}/binary-amd64/Packages.gz"
    code, res = geturl(package_url)

    if code != 200:
        # retry with old-releases if not found in archive
        package_url = f"https://old-releases.ubuntu.com/ubuntu/dists/{name}/{component}/binary-amd64/Packages.gz"
        code, res = geturl(package_url)

    if code != 200:
        raise RuntimeError(f"Failed to download package list from '{package_url}'. HTTP status code: {code}")

    with gzip.GzipFile(fileobj=io.BytesIO(res)) as f:
        content = f.read().decode("utf-8")

    # print(f"Downloaded {len(content)} bytes from {package_url}")

    return content


_re_cache: dict[tuple[str, ...], re.Pattern[str]] = {}

DEFAULT_FIELDS = ("\nPackage: ", "Version: ", "Depends: ", "Pre-Depends: ", "Recommends: ", "Suggests ")


def _abbreviate_package_content(
    content: str,
    fields: tuple[str, ...] = DEFAULT_FIELDS,
) -> str:
    """Abbreviate package content to only include certain fields."""

    if not fields:
        raise ValueError("At least one field must be specified.")

    if fields in _re_cache:
        compiled_re = _re_cache[fields]
    else:
        pattern = r"^((?:" + "|".join(re.escape(field) for field in fields) + r").*?$)"
        compiled_re = re.compile(pattern, re.MULTILINE)
        _re_cache[fields] = compiled_re

    # remove any line which doe snot mathch the pattern
    abbreviated_lines = re.findall(compiled_re, content)
    abbreviated_content = "\n".join(abbreviated_lines)

    return abbreviated_content


PACKAGE_RE = re.compile(r"^Package:\s*(\S+)", re.MULTILINE)


def _abbreviatd_content_to_package_list(abbreviated_content: str) -> set[str]:
    return set(PACKAGE_RE.findall(abbreviated_content))


def get_package_list(
    name: str,
    component: str,
    repo: str,
    *,
    cache_dir: str | None = None,
    refresh_cache: bool = False,
) -> set[str]:
    # Cache the abbreviated blocks to avoid re-downloading and re-parsing
    abbreviated_content: str | None = None
    read_from_cache = False

    if cache_dir is not None and not refresh_cache:
        cache_file = os.path.join(cache_dir, to_cache_file(name, component, repo))
        if os.path.isfile(cache_file):
            with open(cache_file, encoding="utf-8") as f:
                abbreviated_content = f.read()
            read_from_cache = True

    if abbreviated_content is None:
        content = get_package_content(name, component, repo)
        # abbreviated_blocks = _abbreviate_package_content(content)
        abbreviated_content = _abbreviate_package_content(content)

    if cache_dir is not None and not read_from_cache:
        os.makedirs(cache_dir, exist_ok=True)
        cache_file = os.path.join(cache_dir, to_cache_file(name, component, repo))
        with open(cache_file, "w", encoding="utf-8") as f:
            f.write(abbreviated_content)
            f.write("\n\n")

    # Sanity check
    assert abbreviated_content is not None

    return _abbreviatd_content_to_package_list(abbreviated_content)


def to_cache_file(codename: str, component: str, repo: str) -> str:
    # return f"ubuntu-{codename}-{component}-{repo}-packages.txt"
    return f"ubuntu-{codename}{'' if repo == 'main' else '-' + repo}-{component}-packages.txt"


# no version. default to highest LTS
DEFAULT_UBUNTU_VERSION = "24.04"


def default_version() -> str:
    # Try to get version from /etc/os-release. If not found, default to highest encoded LTS
    try:
        with open("/etc/os-release", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VERSION_ID="):
                    version = line.split("=")[1].strip().strip('"')
                    if version in VERISON_TO_CODENAME or version in VERISON_TO_CODENAME.values():
                        return version
    except Exception:
        pass
    return DEFAULT_UBUNTU_VERSION


VERISON_TO_CODENAME = {
    "16.04": "xenial",
    "16.10": "yakkety",
    "17.04": "zesty",
    "17.10": "artful",
    "18.04": "bionic",
    "18.10": "cosmic",
    "19.04": "disco",
    "19.10": "eoan",
    "20.04": "focal",
    "20.10": "groovy",
    "21.04": "hirsute",
    "21.10": "impish",
    "22.04": "jammy",
    "22.10": "kinetic",
    "23.04": "lunar",
    "23.10": "mantic",
    "24.04": "noble",
    "24.10": "oracular",
    "25.04": "plucky",
    "25.10": "questing",
}


def validate_options(
    options: tuple[str, ...],
    *,
    one_of: tuple[str, ...] | None = None,  # list of strings that mean "one of the options"
    mapping: dict[str, str] | None = None,
    all: str | None = None,  # string that means "all options"
    delimiter: str = "|",  # delimiter between options
) -> Callable[[str], list[str]]:
    options_ = set(options)
    assert all not in options_, "'all' option cannot be one of the valid options."
    mapping_ = mapping or {}
    one_of_sting_ = ", ".join(one_of) if one_of is not None else ", ".join(options)

    def _validator(value: str) -> list[str]:
        if all is not None and value == all:
            return list(options)
        values = value.split(delimiter)
        mapped_values = []
        for v in values:
            mapped_ = v.lower()
            mapped_ = mapping_.get(mapped_, mapped_)

            if mapped_ not in options_:
                raise argparse.ArgumentTypeError(f"Invalid option: {v}. Must be one of {one_of_sting_}.")
            mapped_values.append(mapped_)
        values = mapped_values
        if len(values) < 1:
            raise argparse.ArgumentTypeError("At least one option must be specified.")
        return values

    return _validator


def parse_args() -> argparse.Namespace:
    import argparse

    parser = argparse.ArgumentParser(description="Fetch and display package lists from Ubuntu repositories.")

    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s " + __version__,
        help="Show script version and exit.",
    )

    one_of = ["all"]
    for i, (v, c) in enumerate(VERISON_TO_CODENAME.items()):
        one_of.append(v)
        one_of.append(c)
        if i > 1:
            break
    one_of.append("...")

    _validate_ubuntu = validate_options(
        tuple(VERISON_TO_CODENAME.keys()) + tuple(VERISON_TO_CODENAME.values()),
        one_of=tuple(one_of),
        mapping={v: k for k, v in VERISON_TO_CODENAME.items()},
        all="all",
    )

    parser.register("type", "ubuntu", _validate_ubuntu)

    parser.add_argument(
        "--ubuntu",
        type="ubuntu",
        default=default_version(),
        help=(
            "Ubuntu version to fetch packages for (default: current system version). "
            "Can also be `20.04|22.04` to get packages from multiple versions or `all` to get "
            "packages from all supported versions. Instead of version number codename can "
            "also be used, e.g. `focal|jammy`."
        ),
    )

    parser.register(
        "type",
        "component",
        validate_options(
            ("main", "restricted", "universe", "multiverse"),
            one_of=("[M]ain", "[R]estricted", "[U]niverse", "mu[L]tiverse"),
            mapping={"m": "main", "r": "restricted", "u": "universe", "l": "multiverse"},
            all="all",
        ),
    )

    parser.add_argument(
        "--component",
        type="component",
        default="all",
        help=(
            "Ubuntu component to fetch packages from (default: main). Can also be "
            "`main|restricted` to get packages from both components or `all` to get "
            "packages from all four components."
        ),
    )

    parser.register(
        "type",
        "repos",
        validate_options(
            ("main", "security", "updates", "backports"),
            one_of=("[M]ain", "[S]ecurity", "[U]pdates", "[B]ackports"),
            mapping={"m": "main", "s": "security", "u": "updates", "b": "backports"},
            all="all",
        ),
    )

    parser.add_argument(
        "--repos",
        type="repos",
        default="all",
        help=(
            "Ubuntu repository to fetch packages from (default: main). Can also be "
            "`main|security` to get packages from both repositories or `all` to get "
            "packages from all four repositories."
        ),
    )

    parser.add_argument(
        "--cache-dir",
        type=str,
        default=None,
        help=(
            "Directory to cache downloaded package lists (default: None, no caching). "
            "Can also be set with MULTI_APT_CACHE_DIR environment variable."
        ),
    )

    if os.getenv("MULTI_APT_CACHE_DIR", None) is not None and "--cache-dir" not in " ".join(sys.argv):
        parser.set_defaults(cache_dir=os.getenv("MULTI_APT_CACHE_DIR", None))

    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Do not read from cache, download package lists again even if cached (default: False).",
    )

    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=0,  # -1 means as many as possible, 0 means no parallelism
        help=(
            "Number of parallel jobs (default: 0, no parallelism). Set to -1 to use as many parallel "
            "jobs as possible (determined by os.cpu_count())."
        ),
    )

    parsed = parser.parse_args()

    if parsed.jobs < 0:
        parsed.jobs = os.cpu_count() or 1

    # Sanity checks
    assert isinstance(parsed.ubuntu, list)
    assert isinstance(parsed.component, list)

    return parsed


def main() -> None:
    args = parse_args()

    all_packages: set[str] = set()

    if args.jobs == 0:
        # NOTE: this is the single threaded version. Writing this out as opposed
        #       to using ThreadPoolExecutor with max_workers=1
        #       to make it easier to debug and profile.

        for ubuntu in args.ubuntu:
            codename = VERISON_TO_CODENAME.get(ubuntu, ubuntu)
            for component in args.component:
                for repo in args.repos:
                    all_packages.update(
                        get_package_list(
                            codename,
                            component,
                            repo,
                            cache_dir=args.cache_dir,
                            refresh_cache=args.refresh_cache,
                        )
                    )

    else:
        from concurrent.futures import ThreadPoolExecutor

        futures = []
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            for ubuntu in args.ubuntu:
                codename = VERISON_TO_CODENAME.get(ubuntu, ubuntu)
                for component in args.component:
                    for repo in args.repos:
                        futures.append(  # noqa: PERF401
                            executor.submit(
                                get_package_list,
                                codename,
                                component,
                                repo,
                                cache_dir=args.cache_dir,
                                refresh_cache=args.refresh_cache,
                            )
                        )

        for future in futures:
            all_packages.update(future.result())

    print("\n".join(sorted(all_packages)))


if __name__ == "__main__":
    main()
