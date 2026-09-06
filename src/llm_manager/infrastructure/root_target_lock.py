"""Shared advisory lock for the fixed Ollama drop-in parent inode.

Borrow a securely opened parent FD. Each acquisition opens an independent file
description, so even callers in one process contend. Never delete a lock file
or discard abandoned restore staging to make a target available.
"""
from contextlib import contextmanager
import fcntl
import os

from llm_manager.application.errors import AdapterError


@contextmanager
def locked_root_target(parent_fd, *, busy_code='root_restore_target_busy'):
    fd = os.open('.', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC, dir_fd=parent_fd)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise AdapterError(busy_code, 'root target is busy') from error
        if any(name.startswith('.llm-restore-') for name in os.listdir(fd)):
            raise AdapterError('root_restore_staging_incomplete', 'root target requires reconciliation')
        yield
    finally:
        os.close(fd)
