from __future__ import annotations

import glob
import platform
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

from llm_manager.domain.enums import HostKind

_MAX_CONFIG_BYTES = 1024 * 1024
_MAX_INCLUDED_FILES = 128
_WILDCARD_CHARACTERS = frozenset("*?![]")
_SAFE_ALIAS = re.compile(r"[A-Za-z0-9_.][A-Za-z0-9_.@:-]{0,254}")


@dataclass(frozen=True, slots=True)
class HostCandidate:
    host_id: str
    kind: HostKind
    display_name: str
    ssh_alias: str | None = None


class OpenSshConfigAliases:
    def __init__(self, config_path: Path) -> None:
        if not config_path.is_absolute():
            raise ValueError("OpenSSH config path must be absolute")
        self._config_path = config_path
        self._include_root = config_path.parent

    def list_aliases(self) -> tuple[str, ...]:
        aliases: set[str] = set()
        visited: set[Path] = set()
        self._read(self._config_path, visited, aliases)
        return tuple(sorted(aliases, key=str.casefold))

    def _read(self, path: Path, visited: set[Path], aliases: set[str]) -> None:
        if len(visited) >= _MAX_INCLUDED_FILES:
            raise ValueError("OpenSSH config includes too many files")
        identity = path.absolute()
        if identity in visited:
            return
        visited.add(identity)
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            return
        if size > _MAX_CONFIG_BYTES:
            raise ValueError("OpenSSH config file is too large")
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise ValueError("OpenSSH config cannot be read as UTF-8") from error
        for raw_line in text.splitlines():
            try:
                parts = shlex.split(raw_line, comments=True, posix=True)
            except ValueError as error:
                raise ValueError("OpenSSH config contains invalid quoting") from error
            if not parts:
                continue
            keyword = parts[0].lower()
            values = parts[1:]
            if keyword == "host":
                aliases.update(value for value in values if _is_literal_alias(value))
            elif keyword == "include":
                for pattern in values:
                    self._read_includes(pattern, visited, aliases)

    def _read_includes(
        self, pattern: str, visited: set[Path], aliases: set[str]
    ) -> None:
        expanded = Path(pattern).expanduser()
        if not expanded.is_absolute():
            expanded = self._include_root / expanded
        for match in sorted(glob.glob(str(expanded), recursive=False)):
            candidate = Path(match)
            if candidate.is_file():
                self._read(candidate, visited, aliases)


class DiscoverHosts:
    def __init__(self, ssh_config: OpenSshConfigAliases) -> None:
        self._ssh_config = ssh_config

    def execute(self) -> tuple[HostCandidate, ...]:
        local = HostCandidate(
            host_id=f"local:{platform.node()}",
            kind=HostKind.LOCAL,
            display_name="Local",
        )
        remote = tuple(
            HostCandidate(f"ssh:{alias}", HostKind.SSH, alias, alias)
            for alias in self._ssh_config.list_aliases()
        )
        return (local, *remote)


def _is_literal_alias(value: str) -> bool:
    if not value or value.startswith("-") or value.startswith("!"):
        return False
    if any(character in _WILDCARD_CHARACTERS for character in value):
        return False
    return _SAFE_ALIAS.fullmatch(value) is not None
