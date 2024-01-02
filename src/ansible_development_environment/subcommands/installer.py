"""The installer."""

from __future__ import annotations

import re
import shutil
import subprocess

from pathlib import Path
from typing import TYPE_CHECKING

from ansible_development_environment.collection import (
    Collection,
    parse_collection_request,
)
from ansible_development_environment.utils import (
    builder_introspect,
    collections_from_requirements,
    oxford_join,
    subprocess_run,
)

from .checker import Checker


if TYPE_CHECKING:
    from ansible_development_environment.config import Config
    from ansible_development_environment.output import Output


class Installer:
    """The installer class."""

    def __init__(self: Installer, config: Config, output: Output) -> None:
        """Initialize the installer.

        Args:
            config: The application configuration.
            output: The application output object.
        """
        self._config = config
        self._output = output
        self._current_collection_spec: str

    def run(self: Installer) -> None:
        """Run the installer."""
        if (
            self._config.args.collection_specifier
            and "," in self._config.args.collection_specifier
        ):
            err = "Multiple optional dependencies are not supported at this time."
            self._output.critical(err)

        self._install_core()
        if self._config.args.requirement or self._config.args.cpi:
            self._install_galaxy_requirements()
        if self._config.args.collection_specifier:
            collections = [
                parse_collection_request(
                    string=entry,
                    config=self._config,
                    output=self._output,
                )
                for entry in self._config.args.collection_specifier
            ]
            local_collections = [
                collection for collection in collections if collection.local
            ]
            for local_collection in local_collections:
                self._install_local_collection(collection=local_collection)
                if self._config.args.editable:
                    self._swap_editable_collection(collection=local_collection)
            distant_collections = [
                collection for collection in collections if not collection.local
            ]
            if distant_collections:
                if self._config.args.editable:
                    msg = "Editable installs are only supported for local collections."
                    self._output.critical(msg)
                self._install_galaxy_collections(collections=distant_collections)

        builder_introspect(config=self._config, output=self._output)
        self._pip_install()
        Checker(config=self._config, output=self._output).system_deps()

        if self._config.args.venv and (
            self._config.interpreter != self._config.venv_interpreter
        ):
            msg = "A virtual environment was specified but has not been activated."
            self._output.note(msg)
            msg = (
                "Please activate the virtual environment:"
                f"\nsource {self._config.args.venv}/bin/activate"
            )
            self._output.note(msg)

    def _install_core(self: Installer) -> None:
        """Install ansible-core if not installed already."""
        msg = "Installing ansible-core."
        self._output.info(msg)

        core = self._config.venv_bindir / "ansible"
        if core.exists():
            return
        msg = "Installing ansible-core."
        self._output.debug(msg)
        command = f"{self._config.venv_interpreter} -m pip install ansible-core"
        try:
            subprocess_run(
                command=command,
                verbose=self._config.args.verbose,
                msg=msg,
                output=self._output,
            )
        except subprocess.CalledProcessError as exc:
            err = f"Failed to install ansible-core: {exc}"
            self._output.critical(err)

    def _install_galaxy_collections(
        self: Installer,
        collections: list[Collection],
    ) -> None:
        """Install the collection from galaxy."""
        collections_str = " ".join(
            [f"'{collection.original}'" for collection in collections],
        )
        msg = f"Installing collections from galaxy: {collections_str}"
        self._output.info(msg)

        for collection in collections:
            if collection.site_pkg_path.exists():
                msg = f"Removing installed {collection.site_pkg_path}"
                self._output.debug(msg)
                if collection.site_pkg_path.is_symlink():
                    collection.site_pkg_path.unlink()
                else:
                    shutil.rmtree(collection.site_pkg_path)

        command = (
            f"{self._config.venv_bindir / 'ansible-galaxy'} collection"
            f" install {collections_str}"
            f" -p {self._config.site_pkg_path}"
            " --force"
        )
        env = {
            "ANSIBLE_GALAXY_COLLECTIONS_PATH_WARNING": str(self._config.args.verbose),
        }
        msg = "Running ansible-galaxy to install non-local collection and it's dependencies."
        self._output.debug(msg)
        try:
            proc = subprocess_run(
                command=command,
                env=env,
                verbose=self._config.args.verbose,
                msg=msg,
                output=self._output,
            )
        except subprocess.CalledProcessError as exc:
            err = f"Failed to install collection: {exc}\n{exc.stderr}"
            self._output.critical(err)
            return
        installed = re.findall(r"(\w+\.\w+):.*installed", proc.stdout)
        msg = f"Installed collections include: {oxford_join(installed)}"
        self._output.note(msg)

    def _install_galaxy_requirements(self: Installer) -> None:
        """Install the collections using requirements.yml."""
        if self._config.args.requirement and not self._config.args.cpi:
            msg = f"Installing collections from requirements file: {self._config.args.requirement}"
            self._output.info(msg)
            collections = collections_from_requirements(
                file=self._config.args.requirement,
            )
        elif self._config.args.cpi:
            msg = "Source installing collections from requirements file source-requirement.yml"
            self._output.info(msg)
            collections = collections_from_requirements(
                file=self._config.args.requirement,
            )

        for collection in collections:
            cnamespace = collection["name"].split(".")[0]
            cname = collection["name"].split(".")[1]
            cpath = self._config.site_pkg_collections_path / cnamespace / cname
            if cpath.exists():
                msg = f"Removing installed {cpath}"
                self._output.debug(msg)
                if cpath.is_symlink():
                    cpath.unlink()
                else:
                    shutil.rmtree(cpath)

        command = (
            f"{self._config.venv_bindir / 'ansible-galaxy'} collection"
            f" install -r {self._config.args.requirement}"
            f" -p {self._config.site_pkg_path}"
            " --force"
        )
        work = "Install collections from requirements file"
        try:
            proc = subprocess_run(
                command=command,
                verbose=self._config.args.verbose,
                msg=work,
                output=self._output,
            )
        except subprocess.CalledProcessError as exc:
            err = f"Failed to install collections: {exc} {exc.stderr}"
            self._output.critical(err)

        installed = re.findall(r"(\w+\.\w+):.*installed", proc.stdout)
        if not self._config.args.cpi:
            msg = f"Installed collections include: {oxford_join(installed)}"
        else:
            msg = f"Source installed collections include: {oxford_join(installed)}"
        self._output.note(msg)

    def _copy_git_repo_files(
        self: Installer,
        local_repo_path: Path | None,
        destination_path: Path,
    ) -> None:
        """Copy collection files tracked in git to the build directory.

        Args:
            local_repo_path: The collection local path.
            destination_path: The build destination path.

        """
        if local_repo_path is None:
            msg = "Invalid repo path, no files to copy from Git"
            self._output.info(msg)
            return

        msg = "List collection files using git ls-files."
        self._output.debug(msg)

        try:
            # Get the list of tracked files in the repository
            tracked_files_output = subprocess_run(
                command="git ls-files 2> /dev/null || ls",
                cwd=local_repo_path,
                verbose=self._config.args.verbose,
                msg=msg,
                output=self._output,
            )
        except subprocess.CalledProcessError as exc:
            err = f"Failed to list collection using git ls-files: {exc} {exc.stderr}"
            self._output.critical(err)
            return

        # Get the list of tracked files
        tracked_files = tracked_files_output.stdout.split("\n")

        # Create the destination folder if it doesn't exist
        Path(destination_path).mkdir(parents=True, exist_ok=True)

        for file in tracked_files:
            src_file_path = Path(local_repo_path) / file
            dest_file_path = Path(destination_path) / file

            # Ensure the destination directory for the file exists
            dest_file_path.parent.mkdir(parents=True, exist_ok=True)

            if src_file_path.is_dir():
                # Skip directories
                continue

            try:
                # Copy the file
                shutil.copy2(src_file_path, dest_file_path)
            except shutil.Error as exc:
                err = f"Failed to copy collection to build directory: {exc}"
                self._output.critical(err)

    def _install_local_collection(
        self: Installer,
        collection: Collection,
    ) -> None:
        """Install the collection from the build directory.

        Args:
            collection: The collection object.

        Raises:
            RuntimeError: If tarball is not found or if more than one tarball is found.
        """
        # pylint: disable=too-many-instance-attributes
        msg = f"Installing local collection from: {collection.build_dir}"
        self._output.info(msg)

        self._copy_git_repo_files(
            local_repo_path=collection.path,
            destination_path=collection.build_dir,
        )

        command = (
            f"cd {collection.build_dir} &&"
            f" {self._config.venv_bindir / 'ansible-galaxy'} collection build"
            f" --output-path {collection.build_dir}"
            " --force"
        )

        msg = "Running ansible-galaxy to build collection."
        self._output.debug(msg)

        try:
            subprocess_run(
                command=command,
                verbose=self._config.args.verbose,
                msg=msg,
                output=self._output,
            )
        except subprocess.CalledProcessError as exc:
            err = f"Failed to build collection: {exc} {exc.stderr}"
            self._output.critical(err)

        built = [
            f
            for f in Path(collection.build_dir).iterdir()
            if f.is_file() and f.name.endswith(".tar.gz")
        ]
        if len(built) != 1:
            err = (
                "Expected to find one collection tarball in"
                f"{collection.build_dir}, found {len(built)}"
            )
            raise RuntimeError(err)
        tarball = built[0]

        if collection.site_pkg_path.exists():
            msg = f"Removing installed {collection.site_pkg_path}"
            self._output.debug(msg)
            if collection.site_pkg_path.is_symlink():
                collection.site_pkg_path.unlink()
            else:
                shutil.rmtree(collection.site_pkg_path)

        info_dirs = [
            entry
            for entry in self._config.site_pkg_collections_path.iterdir()
            if entry.is_dir()
            and entry.name.endswith(".info")
            and entry.name.startswith(collection.name)
        ]
        for info_dir in info_dirs:
            msg = f"Removing installed {info_dir}"
            self._output.debug(msg)
            shutil.rmtree(info_dir)

        command = (
            f"{self._config.venv_bindir / 'ansible-galaxy'} collection"
            f" install {tarball} -p {self._config.site_pkg_path}"
            " --force"
        )
        env = {
            "ANSIBLE_GALAXY_COLLECTIONS_PATH_WARNING": str(self._config.args.verbose),
        }
        msg = "Running ansible-galaxy to install a local collection and it's dependencies."
        self._output.debug(msg)
        try:
            proc = subprocess_run(
                command=command,
                env=env,
                verbose=self._config.args.verbose,
                msg=msg,
                output=self._output,
            )
        except subprocess.CalledProcessError as exc:
            err = f"Failed to install collection: {exc} {exc.stderr}"
            self._output.critical(err)
            return

        # ansible-galaxy collection install does not include the galaxy.yml for version
        # nor does it create an info file that can be used to determine the version.
        # preserve the MANIFEST.json file for editable installs
        if not self._config.args.editable:
            shutil.copy(
                collection.build_dir / "galaxy.yml",
                collection.site_pkg_path / "galaxy.yml",
            )
        else:
            shutil.copy(
                collection.site_pkg_path / "MANIFEST.json",
                collection.cache_dir / "MANIFEST.json",
            )

        installed = re.findall(r"(\w+\.\w+):.*installed", proc.stdout)
        msg = f"Installed collections include: {oxford_join(installed)}"
        self._output.note(msg)

    def _swap_editable_collection(self: Installer, collection: Collection) -> None:
        """Swap the installed collection with the current working directory.

        Args:
            collection: The collection object.

        Raises:
            RuntimeError: If the collection path is not set.
        """
        msg = f"Swapping {collection.name} with {collection.path}"
        self._output.info(msg)

        if collection.path is None:
            msg = "Collection path not set"
            raise RuntimeError(msg)
        msg = f"Removing installed {collection.site_pkg_path}"
        self._output.debug(msg)
        if collection.site_pkg_path.exists():
            if collection.site_pkg_path.is_symlink():
                collection.site_pkg_path.unlink()
            else:
                shutil.rmtree(collection.site_pkg_path)

        msg = f"Symlinking {collection.site_pkg_path} to {collection.path}"
        self._output.debug(msg)
        collection.site_pkg_path.symlink_to(collection.path)

    def _pip_install(self: Installer) -> None:
        """Install the dependencies."""
        msg = "Installing python requirements."
        self._output.info(msg)

        command = (
            f"{self._config.venv_interpreter} -m pip install"
            f" -r {self._config.discovered_python_reqs}"
        )

        msg = (
            f"Installing python requirements from {self._config.discovered_python_reqs}"
        )
        self._output.debug(msg)
        work = "Installing python requirements"
        try:
            subprocess_run(
                command=command,
                verbose=self._config.args.verbose,
                msg=work,
                output=self._output,
            )
        except subprocess.CalledProcessError as exc:
            err = (
                "Failed to install requirements from"
                f" {self._config.discovered_python_reqs}: {exc} {exc.stderr}"
            )
            self._output.critical(err)
        else:
            msg = "All python requirements are installed."
            self._output.note(msg)
