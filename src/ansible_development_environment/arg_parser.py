"""Parse the command line arguments."""

from __future__ import annotations

import argparse

from argparse import HelpFormatter
from pathlib import Path


try:
    from ._version import version as __version__  # type: ignore[unused-ignore,import-not-found]
except ImportError:  # pragma: no cover
    try:
        import pkg_resources

        __version__ = pkg_resources.get_distribution(
            "ansible_development_environment",
        ).version
    except Exception:  # pylint: disable=broad-except # noqa: BLE001
        # this is the fallback SemVer version picked by setuptools_scm when tag
        # information is not available.
        __version__ = "0.1.dev1"


def common_args(parser: ArgumentParser) -> None:
    """Add common arguments to the parser.

    Args:
        parser: The parser to add the arguments to
    """
    parser.add_argument(
        "--lf",
        "--log-file <file>",
        dest="log_file",
        default=str(Path.cwd() / "ansible-development-environment.log"),
        help="Log file to write to.",
    )
    parser.add_argument(
        "--ll",
        "--log-level <level>",
        dest="log_level",
        default="notset",
        choices=["notset", "debug", "info", "warning", "error", "critical"],
        help="Log level for file output.",
    )
    parser.add_argument(
        "--la",
        "--log-append <bool>",
        dest="log_append",
        choices=["true", "false"],
        default="true",
        help="Append to log file.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Give more CLI output. Option is additive, and can be used up to 3 times.",
    )


def parse() -> argparse.Namespace:
    """Parse the command line arguments.

    Returns:
        The arguments
    """
    parser = ArgumentParser(
        description="A pip-like ansible collection installer.",
        formatter_class=CustomHelpFormatter,
    )

    common_args(parser)

    parser.add_argument(
        "-V",
        "--version",
        action="version",
        help="Show version and exit.",
        version=__version__,
    )

    subparsers = parser.add_subparsers(
        title="Commands",
        dest="subcommand",
        metavar="",
        required=True,
    )

    level1 = ArgumentParser(add_help=False)

    level1.add_argument(
        "--ve",
        "--venv <directory>",
        help="Target virtual environment.",
        dest="venv",
    )

    level1.add_argument(
        "--cpi",
        "--collection-pre-install",
        help="Pre install collections from source, reads requirements-source.yml file.",
        default=False,
        action="store_true",
    )

    level1.add_argument(
        "--na",
        "--no-ansi",
        action="store_true",
        default=False,
        dest="no_ansi",
        help="Disable the use of ANSI codes for terminal hyperlink generation and color.",
    )

    common_args(level1)

    _check = subparsers.add_parser(
        "check",
        formatter_class=CustomHelpFormatter,
        parents=[level1],
        help="Check installed collections",
    )

    _inspect = subparsers.add_parser(
        "inspect",
        formatter_class=CustomHelpFormatter,
        parents=[level1],
        help="Inspect installed collections",
    )

    _list = subparsers.add_parser(
        "list",
        formatter_class=CustomHelpFormatter,
        parents=[level1],
        help="List installed collections",
    )

    _tree = subparsers.add_parser(
        "tree",
        formatter_class=CustomHelpFormatter,
        parents=[level1],
        help="Generate a dependency tree",
    )

    level2 = ArgumentParser(add_help=False, parents=[level1])
    level2.add_argument(
        "collection_specifier",
        help="Collection name or path to collection with extras.",
        nargs="*",
    )
    level2.add_argument(
        "-r",
        "--requirement <file>",
        dest="requirement",
        help="Install from the given requirements file.",
        required=False,
    )

    install = subparsers.add_parser(
        "install",
        formatter_class=CustomHelpFormatter,
        parents=[level2],
        help="Install a collection.",
    )
    install.add_argument(
        "-e",
        "--editable",
        action="store_true",
        help="Install editable.",
    )

    _uninstall = subparsers.add_parser(
        "uninstall",
        formatter_class=CustomHelpFormatter,
        parents=[level2],
        help="Uninstall a collection.",
    )

    # pylint: disable=protected-access
    for grp in parser._action_groups:  # noqa: SLF001
        if grp.title is None:
            continue
        grp.title = grp.title.capitalize()
    for subparser in subparsers.choices.values():
        for grp in subparser._action_groups:  # noqa: SLF001
            if grp.title is None:
                continue
            grp.title = grp.title.capitalize()
    # pylint: enable=protected-access

    return parser.parse_args()


class ArgumentParser(argparse.ArgumentParser):
    """A custom argument parser."""

    def add_argument(  # type: ignore[no-untyped-def, override]
        self: ArgumentParser,
        *args,  # noqa: ANN002
        **kwargs,  # noqa: ANN003
    ) -> None:
        """Add an argument."""
        if "choices" in kwargs:
            kwargs["help"] += f" (choices: {', '.join(kwargs['choices'])})"
        if "default" in kwargs and kwargs["default"] != "==SUPPRESS==":
            kwargs["help"] += f" (default: {kwargs['default']})"
        kwargs["help"] = kwargs["help"][0].upper() + kwargs["help"][1:]
        super().add_argument(*args, **kwargs)


class CustomHelpFormatter(HelpFormatter):
    """A custom help formatter."""

    def __init__(self: CustomHelpFormatter, prog: str) -> None:
        """Initialize the help formatter.

        :param prog: The program name
        """
        long_string = "--abc  --really_really_really_log"
        # 3 here accounts for the spaces in the ljust(6) below
        HelpFormatter.__init__(
            self,
            prog=prog,
            indent_increment=1,
            max_help_position=len(long_string) + 3,
        )

    def _format_action_invocation(
        self: CustomHelpFormatter,
        action: argparse.Action,
    ) -> str:
        """Format the action invocation.

        Args:
            action: The action to format

        Raises:
            ValueError: If more than 2 options are given

        Returns:
            The formatted action invocation
        """
        if not action.option_strings:
            default = self._get_default_metavar_for_positional(action)
            (metavar,) = self._metavar_formatter(action, default)(1)
            return metavar

        if len(action.option_strings) == 1:
            return action.option_strings[0]

        max_variations = 2
        if len(action.option_strings) == max_variations:
            # Account for a --1234 --long-option-name
            return f"{action.option_strings[0].ljust(6)} {action.option_strings[1]}"
        msg = "Too many option strings"
        raise ValueError(msg)
