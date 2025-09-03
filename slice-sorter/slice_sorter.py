#!/usr/bin/env python3
"""
Script to sort slices in SDF files.
"""
# spell-checker: ignore Marcin Konowalczyk lczyk
# spell-checker: words levelname
# mypy: disable-error-code="unused-ignore"

from __future__ import annotations

import argparse
import logging
import sys

__version__ = "0.0.0"
__author__ = "Marcin Konowalczyk"

__changelog__ = [
    ("0.0.0", "boilerplate", "@lczyk"),
]

################################################################################


## MAIN ########################################################################


def main(args: argparse.Namespace) -> None:
    print("hi")


################################################################################

## BOILERPLATE #################################################################


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sort slices in SDFs",
    )

    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
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
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Modify the files in place. By default, the script only prints the changes that would be made.",
    )

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
