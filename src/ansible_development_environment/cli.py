"""CLI entrypoint."""

from __future__ import annotations

import os
import site
import sys

from pathlib import Path
from typing import TYPE_CHECKING

from ansible_development_environment import subcommands

from .arg_parser import parse
from .config import Config
from .output import Output
from .utils import TermFeatures


if TYPE_CHECKING:
    from argparse import Namespace


class Cli:
    """The Cli class."""

    def __init__(self: Cli) -> None:
        """Initialize the CLI and parse CLI args."""
        self.args: Namespace
        self.config: Config
        self.output: Output
        self.term_features: TermFeatures

    def parse_args(self: Cli) -> None:
        """Parse the command line arguments."""
        self.args = parse()
        if hasattr(self.args, "requirement") and self.args.requirement:
            self.args.requirement = Path(self.args.requirement).expanduser().resolve()
        if self.args.cpi:
            self.args.requirement = (
                Path(".config/source-requirements.yml").expanduser().resolve()
            )

    def init_output(self: Cli) -> None:
        """Initialize the output object."""
        if not sys.stdout.isatty():
            self.term_features = TermFeatures(color=False, links=False)
        else:
            self.term_features = TermFeatures(
                color=False if os.environ.get("NO_COLOR") else not self.args.no_ansi,
                links=not self.args.no_ansi,
            )

        self.output = Output(
            log_append=self.args.log_append,
            log_file=self.args.log_file,
            log_level=self.args.log_level,
            term_features=self.term_features,
            verbosity=self.args.verbose,
        )

    def args_sanity(self: Cli) -> None:
        """Perform some sanity checking on the args."""
        # Missing args
        if (
            hasattr(self.args, "requirement")
            and self.args.requirement
            and not self.args.requirement.exists()
        ):
            err = f"Requirements file not found: {self.args.requirement}"
            self.output.critical(err)

        # Multiple editable collections
        if (
            hasattr(self.args, "collection_specifier")
            and len(self.args.collection_specifier) > 1
            and hasattr(self.args, "editable")
            and self.args.editable
        ):
            err = "Editable can only be used with a single collection specifier."
            self.output.critical(err)

        # Editable with requirements file
        if (
            hasattr(self.args, "requirement")
            and self.args.requirement
            and hasattr(self.args, "editable")
            and self.args.editable
        ):
            err = "Editable can not be used with a requirements file."
            self.output.critical(err)

    def ensure_isolated(self: Cli) -> None:
        """Ensure the environment is isolated."""
        env_vars = os.environ
        errored = False
        if "ANSIBLE_COLLECTIONS_PATHS" in env_vars:
            err = "ANSIBLE_COLLECTIONS_PATHS is set"
            self.output.error(err)
            hint = "Run `unset ANSIBLE_COLLECTIONS_PATHS` to unset it."
            self.output.hint(hint)
            errored = True
        if "ANSIBLE_COLLECTION_PATH" in env_vars:
            err = "ANSIBLE_COLLECTION_PATH is set"
            self.output.error(err)
            hint = "Run `unset ANSIBLE_COLLECTION_PATH` to unset it."
            self.output.hint(hint)
            errored = True

        home_coll = Path.home() / ".ansible/collections/ansible_collections"
        if home_coll.exists() and tuple(home_coll.iterdir()):
            err = f"Collections found in {home_coll}"
            self.output.error(err)
            hint = "Run `rm -rf ~/.ansible/collections` to remove them."
            self.output.hint(hint)
            errored = True

        usr_coll = Path("/usr/share/ansible/collections")
        if usr_coll.exists() and tuple(usr_coll.iterdir()):
            err = f"Collections found in {usr_coll}"
            self.output.error(err)
            hint = "Run `sudo rm -rf /usr/share/ansible/collections` to remove them."
            self.output.hint(hint)
            errored = True

        if "VIRTUAL_ENV" not in env_vars and not self.args.venv:
            err = (
                "Unable to use user site packages directory:"
                f" {site.getusersitepackages()}, please activate or specify a virtual environment"
            )
            self.output.error(err)
            hint = (
                "Use `--venv <directory>` to specify a virtual environment"
                " or enable an existing one."
            )
            self.output.hint(hint)
            errored = True

        if errored:
            err = (
                "The development environment is not isolated,"
                " please resolve the above errors."
            )

            self.output.critical(err)

    def run(self: Cli) -> None:
        """Run the application."""
        self.config = Config(
            args=self.args,
            output=self.output,
            term_features=self.term_features,
        )
        self.config.init()

        subcommand_cls = getattr(subcommands, self.config.args.subcommand.capitalize())
        subcommand = subcommand_cls(config=self.config, output=self.output)
        subcommand.run()
        self._exit()

    def _exit(self: Cli) -> None:
        """Exit the application setting the return code."""
        if self.output.call_count["error"]:
            sys.exit(1)
        if self.output.call_count["warning"]:
            sys.exit(2)
        sys.exit(0)


def main() -> None:
    """Entry point for ansible-creator CLI."""
    cli = Cli()
    cli.parse_args()
    cli.init_output()
    cli.args_sanity()
    cli.ensure_isolated()
    cli.run()


if __name__ == "__main__":
    main()
