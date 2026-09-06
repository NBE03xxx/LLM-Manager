"""Explicit administrator-only initialization. No GUI, rotation or repair mode."""
import argparse
import fcntl
import json
import os
import stat
import sys
from contextlib import ExitStack

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken
from .local_root_key_provisioning import ProvisionLocalRootKey
from .root_apply_capture import PRODUCTION_KEY_ID
from .root_backup_evidence import _open_fixed_directory

STATE_DIRECTORIES = ('keys', 'backups', 'executions', 'audit')


def _private_child(parent_fd, name, *, owner_uid=0, owner_gid=0, private=True):
    try:
        os.mkdir(name, 0o700, dir_fd=parent_fd)
        os.fsync(parent_fd)
    except FileExistsError:
        pass
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                 dir_fd=parent_fd)
    metadata = os.fstat(fd)
    mode = stat.S_IMODE(metadata.st_mode)
    if ((metadata.st_uid, metadata.st_gid) != (owner_uid, owner_gid)
            or (mode != 0o700 if private else bool(mode & 0o022))):
        os.close(fd)
        raise AdapterError('unsafe_root_setup_directory', 'root setup directory is unsafe')
    return fd


def initialize_empty_state(parent_fd, *, owner_uid=0, owner_gid=0):
    """Borrow an anchored llm-manager directory; owner overrides are test seams."""
    metadata = os.fstat(parent_fd)
    if (not stat.S_ISDIR(metadata.st_mode) or
            (metadata.st_uid, metadata.st_gid) != (owner_uid, owner_gid)
            or stat.S_IMODE(metadata.st_mode) & 0o022):
        raise AdapterError('unsafe_root_setup_directory', 'root setup parent is unsafe')
    with ExitStack() as stack:
        def child(parent, name):
            fd = _private_child(parent, name, owner_uid=owner_uid, owner_gid=owner_gid)
            stack.callback(os.close, fd)
            return fd
        root = child(parent_fd, 'local-root-restore')
        try:
            fcntl.flock(root, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise AdapterError('root_setup_busy', 'root setup is already active') from error
        if set(os.listdir(root)) - set(STATE_DIRECTORIES):
            raise AdapterError('root_setup_existing_state', 'existing state requires administrator review')
        directories = {name: child(root, name) for name in STATE_DIRECTORIES}
        # Never replace a lost key while backups/history survive, or clean up
        # partial key publication. Only an entirely empty layout is eligible.
        if any(os.listdir(fd) for fd in directories.values()):
            raise AdapterError('root_setup_existing_state', 'existing state requires administrator review')
        ProvisionLocalRootKey(directories['keys'], owner_uid=owner_uid, owner_gid=owner_gid).execute(
            PRODUCTION_KEY_ID, CancellationToken())
        os.fsync(root)


def initialize_production():
    if os.geteuid() != 0:
        raise AdapterError('root_required', 'explicit administrator setup requires root')
    with ExitStack() as stack:
        parent = _open_fixed_directory('/var/lib', private=False)
        stack.callback(os.close, parent)
        # Existing helper receipts may have created this shared parent as 0755.
        # Preserve its mode; only the dedicated restore subtree must be 0700.
        state = _private_child(parent, 'llm-manager', private=False)
        stack.callback(os.close, state)
        initialize_empty_state(state)


def main(argv=None):
    parser = argparse.ArgumentParser(prog='llm-manager-restore-setup', allow_abbrev=False)
    parser.add_argument('command', choices=('initialize',))
    parser.parse_args(argv)
    try:
        initialize_production()
    except (AdapterError, OSError) as error:
        code = error.code if isinstance(error, AdapterError) else 'root_setup_incomplete'
        value, status = {'status': 'failed', 'error_code': code}, 1
    else:
        value, status = {'status': 'initialized', 'key_id': PRODUCTION_KEY_ID}, 0
    sys.stdout.write(json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n')
    return status


if __name__ == '__main__':
    raise SystemExit(main())
