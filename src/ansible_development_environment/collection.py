"""A collection abstraction."""
from __future__ import annotations

import re
import sys

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import yaml


if TYPE_CHECKING:
    from .config import Config
    from .output import Output


@dataclass
class Collection:  # pylint: disable=too-many-instance-attributes
    """A collection request specification."""

    config: Config
    path: Path | None = None
    opt_deps: str | None = None
    local: bool | None = None
    cnamespace: str | None = None
    cname: str | None = None
    csource: list[str] | None = None
    specifier: str | None = None
    original: str | None = None

    @property
    def name(self: Collection) -> str:
        """Return the collection name."""
        return f"{self.cnamespace}.{self.cname}"

    @property
    def cache_dir(self: Collection) -> Path:
        """Return the collection cache directory."""
        collection_cache_dir = self.config.venv_cache_dir / self.name
        if not collection_cache_dir.exists():
            collection_cache_dir.mkdir()
        return collection_cache_dir

    @property
    def build_dir(self: Collection) -> Path:
        """Return the collection cache directory."""
        collection_build_dir = self.cache_dir / "build"
        if not collection_build_dir.exists():
            collection_build_dir.mkdir()
        return collection_build_dir

    @property
    def site_pkg_path(self: Collection) -> Path:
        """Return the site packages collection path."""
        if not self.cnamespace or not self.cname:
            msg = "Collection namespace or name not set."
            raise RuntimeError(msg)
        return self.config.site_pkg_collections_path / self.cnamespace / self.cname


def parse_collection_request(  # noqa: PLR0915
    string: str,
    config: Config,
    output: Output,
) -> Collection:
    """Parse a collection request str.

    Args:
        string: The collection request string
        config: The configuration object
        output: The output object
    Returns:
        A collection object
    """
    collection = Collection(config=config, original=string)
    # spec with dep, local
    if "[" in string and "]" in string:
        msg = f"Found optional dependencies in collection request: {string}"
        output.debug(msg)
        path = Path(string.split("[")[0]).expanduser().resolve()
        if not path.exists():
            msg = "Provide an existing path to a collection when specifying optional dependencies."
            output.hint(msg)
            msg = f"Failed to find collection path: {path}"
            output.critical(msg)
        msg = f"Found local collection request with dependencies: {string}"
        output.debug(msg)
        collection.path = path
        msg = f"Setting collection path: {collection.path}"
        collection.opt_deps = string.split("[")[1].split("]")[0]
        msg = f"Setting optional dependencies: {collection.opt_deps}"
        output.debug(msg)
        collection.local = True
        msg = "Setting request as local"
        output.debug(msg)
        get_galaxy(collection=collection, output=output)
        return collection
    # spec without dep, local
    path = Path(string).expanduser().resolve()
    if path.exists():
        msg = f"Found local collection request without dependencies: {string}"
        output.debug(msg)
        msg = f"Setting collection path: {path}"
        output.debug(msg)
        collection.path = path
        msg = "Setting request as local"
        output.debug(msg)
        collection.local = True
        get_galaxy(collection=collection, output=output)
        return collection
    non_local_re = re.compile(
        r"""
        (?P<cnamespace>[A-Za-z0-9]+)    # collection name
        \.                              # dot
        (?P<cname>[A-Za-z0-9]+)         # collection name
        (?P<specifier>[^A-Za-z0-9].*)?   # optional specifier
        """,
        re.VERBOSE,
    )
    matched = non_local_re.match(string)
    if not matched:
        msg = (
            "Specify a valid collection name (ns.n) with an optional version specifier"
        )
        output.hint(msg)
        msg = f"Failed to parse collection request: {string}"
        output.critical(msg)
        sys.exit(1)
    msg = f"Found non-local collection request: {string}"
    output.debug(msg)

    collection.cnamespace = matched.group("cnamespace")
    msg = f"Setting collection namespace: {collection.cnamespace}"
    output.debug(msg)

    collection.cname = matched.group("cname")
    msg = f"Setting collection name: {collection.cname}"
    output.debug(msg)

    if matched.group("specifier"):
        collection.specifier = matched.group("specifier")
        msg = f"Setting collection specifier: {collection.specifier}"
        output.debug(msg)

    collection.local = False
    msg = "Setting request as non-local"
    output.debug(msg)

    return collection


def get_galaxy(collection: Collection, output: Output) -> None:
    """Retrieve the collection name from the galaxy.yml file.

    Args:
        collection: A collection object
        output: The output object
    Raises:
        SystemExit: If the collection name is not found
    """
    if collection is None or collection.path is None:
        msg = "get_galaxy called without a collection or path"
        raise RuntimeError(msg)
    file_name = collection.path / "galaxy.yml"
    if not file_name.exists():
        err = f"Failed to find {file_name} in {collection.path}"
        output.critical(err)

    with file_name.open(encoding="utf-8") as fileh:
        try:
            yaml_file = yaml.safe_load(fileh)
        except yaml.YAMLError as exc:
            err = f"Failed to load yaml file: {exc}"
            output.critical(err)

    try:
        collection.cnamespace = yaml_file["namespace"]
        collection.cname = yaml_file["name"]
        msg = f"Found collection name: {collection.name} from {file_name}."
        output.debug(msg)
    except KeyError as exc:
        err = f"Failed to find collection name in {file_name}: {exc}"
        output.critical(err)
    else:
        return
    raise SystemExit(1)  # We shouldn't be here
