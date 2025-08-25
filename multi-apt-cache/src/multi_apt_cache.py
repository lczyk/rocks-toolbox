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

__author__ = "Marcin Konowalczyk"
__version__ = "0.1.3"

__changelog__ = [
    (__version__, "add --repo option", "@lczyk"),
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


def get_package_list(name: str, component: str, repo: str) -> set[str]:
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
        # print(f"Warning: Failed to download package list from '{package_url}'. HTTP status code: {code}.
        # Retrying with old-releases.ubuntu.com...")
        package_url = f"https://old-releases.ubuntu.com/ubuntu/dists/{name}/{component}/binary-amd64/Packages.gz"
        # print(f"Retrying with URL: {package_url}")
        code, res = geturl(package_url)

    if code != 200:
        raise RuntimeError(f"Failed to download package list from '{package_url}'. HTTP status code: {code}")

    with gzip.GzipFile(fileobj=io.BytesIO(res)) as f:
        content = f.read().decode("utf-8")

    return set(line.split(" ")[1] for line in content.splitlines() if line.startswith("Package: "))


def to_cache_file(codename: str, component: str, repo: str) -> str:
    return f"ubuntu-{codename}-{component}-{repo}-packages.txt"


def cache_packages_for_component(name: str, component: str, repo: str, packages: set[str], cache_dir: str) -> None:
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, to_cache_file(name, component, repo))
    with open(cache_file, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(packages)))
        f.write("\n")


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
    return "24.04"  # no version. default to highest LTS


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


def parse_args() -> argparse.Namespace:
    import argparse

    parser = argparse.ArgumentParser(description="Fetch and display package lists from Ubuntu repositories.")

    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s " + __version__,
        help="Show script version and exit.",
    )

    def _validate_ubuntu(value: str) -> list[str]:
        if value == "all":
            return list(VERISON_TO_CODENAME.keys())
        versions = value.split("|")
        for v in versions:
            if v not in VERISON_TO_CODENAME and v not in VERISON_TO_CODENAME.values():
                raise argparse.ArgumentTypeError(
                    f"Invalid version: {v}. Must be one of {', '.join(VERISON_TO_CODENAME.keys())} or their codenames."
                )
        if len(versions) < 1:
            raise argparse.ArgumentTypeError("At least one version must be specified.")
        return versions

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

    def _validate_component(value: str) -> list[str]:
        if value == "all":
            return ["main", "restricted", "universe", "multiverse"]
        values = value.split("|")
        for v in values:
            if v not in ("main", "restricted", "universe", "multiverse"):
                raise argparse.ArgumentTypeError(
                    f"Invalid component: {v}. Must be one of 'main', 'restricted', 'universe', or 'multiverse'."
                )
        if len(values) < 1:
            raise argparse.ArgumentTypeError("At least one component must be specified.")
        return values

    parser.register("type", "component", _validate_component)

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

    def _validate_repos(value: str) -> list[str]:
        if value == "all":
            return ["main", "security", "updates", "backports"]
        values = value.split("|")
        for v in values:
            if v not in ("main", "security", "updates", "backports"):
                raise argparse.ArgumentTypeError(
                    f"Invalid repo: {v}. Must be one of '', 'security', 'updates', or 'backports'."
                )
        if len(values) < 1:
            raise argparse.ArgumentTypeError("At least one repo must be specified.")
        return values

    parser.register("type", "repos", _validate_repos)

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

    if os.getenv("MULTI_APT_CACHE_DIR", None) is not None and "--cache-dir" not in " ".join(os.sys.argv):
        parser.set_defaults(cache_dir=os.getenv("MULTI_APT_CACHE_DIR", None))

    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Do not read from cache, download package lists again even if cached (default: False).",
    )

    parsed = parser.parse_args()

    # Sanity checks
    assert isinstance(parsed.ubuntu, list)
    assert isinstance(parsed.component, list)

    return parsed


def main() -> None:
    args = parse_args()

    all_packages: set[str] = set()
    for ubuntu in args.ubuntu:
        codename = VERISON_TO_CODENAME.get(ubuntu, ubuntu)
        for component in args.component:
            for repo in args.repos:
                if args.cache_dir and not args.refresh_cache:
                    cache_file = os.path.join(args.cache_dir, to_cache_file(codename, component, repo))
                    if os.path.isfile(cache_file):
                        with open(cache_file, encoding="utf-8") as f:
                            packages = set(line.strip() for line in f if line.strip())
                        all_packages.update(packages)
                        continue

                packages = get_package_list(codename, component, repo)

                if args.cache_dir:
                    # NOTE: still cache even if --refresh-cache is set, just don't use the cache
                    cache_packages_for_component(codename, component, repo, packages, args.cache_dir)
                all_packages.update(packages)

    print("\n".join(sorted(all_packages)))


if __name__ == "__main__":
    main()
