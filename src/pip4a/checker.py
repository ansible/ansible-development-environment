"""The dependency checker."""

from __future__ import annotations

import json
import logging
import subprocess

from typing import TYPE_CHECKING

from packaging.specifiers import SpecifierSet
from packaging.version import Version

from .utils import (
    builder_introspect,
    collect_manifests,
    hint,
    note,
    oxford_join,
    subprocess_run,
)


if TYPE_CHECKING:
    from .config import Config


logger = logging.getLogger(__name__)


class Checker:
    """The dependency checker."""

    def __init__(self: Checker, config: Config) -> None:
        """Initialize the checker."""
        self._config: Config = config
        self._collections_missing: bool

    def run(self: Checker) -> None:
        """Run the checker."""
        self._collection_deps()
        self._python_deps()

    def _collection_deps(self: Checker) -> None:
        collections = collect_manifests(
            target=self._config.site_pkg_collections_path,
            venv_cache_dir=self._config.venv_cache_dir,
        )
        missing = False
        for collection_name, details in collections.items():
            msg = f"Checking dependencies for {collection_name}."
            logger.debug(msg)
            deps = details["collection_info"]["dependencies"]
            if not deps:
                msg = f"Collection {collection_name} has no dependencies."
                logger.debug(msg)
                continue
            for dep, version in deps.items():
                spec = SpecifierSet(version)
                if dep in collections:
                    dep_version = collections[dep]["collection_info"]["version"]
                    dep_spec = Version(dep_version)
                    if not spec.contains(dep_spec):
                        err = (
                            f"Collection {collection_name} requires {dep} {version}"
                            f" but {dep} {dep_version} is installed."
                        )
                        logger.warning(err)
                        missing = True

                    else:
                        msg = (
                            f"\N{check mark} Collection {collection_name} requires {dep} {version}"
                            f" and {dep} {dep_version} is installed."
                        )
                        logger.debug(msg)
                else:
                    err = (
                        f"Collection {collection_name} requires"
                        f" {dep} {version} but it is not installed."
                    )
                    logger.warning(err)
                    msg = f"Try running `pip4a install {dep}`"
                    hint(msg)
                    missing = True

        if not missing:
            msg = "\N{check mark} All dependant collections are installed."
            note(msg)
        self._collections_missing = missing

    def _python_deps(self: Checker) -> None:
        """Check Python dependencies."""
        builder_introspect(config=self._config)

        missing_file = self._config.venv_cache_dir / "pip-report.txt"
        command = (
            f"{self._config.venv_interpreter} -m pip install -r"
            f" {self._config.discovered_python_reqs} --dry-run"
            f" --report {missing_file}"
        )

        try:
            subprocess_run(command=command, verbose=self._config.args.verbose)
        except subprocess.CalledProcessError as exc:
            err = f"Failed to check python dependencies: {exc}"
            logger.critical(err)
        with missing_file.open() as file:
            pip_report = json.load(file)

        if "install" not in pip_report or not pip_report["install"]:
            msg = "\N{check mark} All Python dependencies are installed."
            note(msg)
            return

        missing = [
            f"{package['metadata']['name']}=={package['metadata']['version']}"
            for package in pip_report["install"]
        ]

        err = f"Missing Python dependencies: {oxford_join(missing)}"
        logger.warning(err)
        msg = f"Try running `pip install {' '.join(missing)}`."
        hint(msg)
        if self._collections_missing:
            err = "Python packages required by missing collections are not included."
            logger.warning(err)