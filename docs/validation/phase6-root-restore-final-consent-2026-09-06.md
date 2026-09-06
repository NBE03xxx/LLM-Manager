# Phase 6 root restore final consent validation — 2026-09-06

## Scope

This slice adds the unpublished, non-root final consent boundary for one exact
local root restore request. It does not register the route in the normal GUI.

- `RootRestoreReviewSession.approved_request_for_execution()` releases only the
  still-live request covered by the saved review receipt.
- `RootRestoreExecutionSession` binds consent to the request SHA-256, consumes
  execution once, and distinguishes committed, failed, unknown, rejected, and
  unconfirmed outcomes.
- Only an unconfirmed invocation permits one read-only status lookup. It never
  enables a second execute call.
- `RootRestoreExecutionDialog` displays the host, caller UID, backup ID, fixed
  target, expiry, current/original metadata, and request hash. Its execute button
  starts disabled and no button is a default button.
- Closing during work requests cancellation, waits for the worker, discards a
  late result, and leaves an executing operation unconfirmed.
- User-visible state is rendered from fixed English/Japanese catalog entries;
  helper output is not shown.

## Automated evidence

Focused host run:

```text
python3 -m unittest tests.test_root_restore_review_session \
  tests.test_root_restore_execution_session \
  tests.test_root_restore_execution_dialog -v
Ran 22 tests in 0.007s
OK (skipped=4)
```

The four skips are the PySide6 runtime cases because PySide6 is not installed on
the host. The missing-runtime boundary test passed. The runtime cases cover exact
metadata and consent, single dispatch, unconfirmed status reconciliation, narrow
layout/default-button behavior, and close waiting with a non-cooperative task.

The same source artifact was then run on Ubuntu 26.04 with Python 3.14.4 and
PySide6 6.10.2. Host and guest both verified artifact SHA-256
`67887eb7aea06a22238a1b9ff76f1f9b92b29932b5865cad6712bed564cb2b50`:

```text
python3 -m unittest tests.test_root_restore_execution_dialog -v
Ran 5 tests in 0.375s
OK (skipped=1)
```

All four PySide6 runtime cases passed. The one skip is the inverse missing-runtime
case and is expected when PySide6 is installed.

Full host regression:

```text
Ran 758 tests in 1.594s
OK (skipped=35)
```

This is 722 passing tests, 35 expected PySide6 skips, and zero failures. The
following checks also passed:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m compileall -q src tests setup.py
bash -n packaging/remote/build-deb.sh packaging/remote/verify-deb.sh \
  packaging/verify-deb.sh packaging/bin/llm-manager \
  packaging/bin/llm-manager-restore-review \
  packaging/bin/llm-manager-restore-execute
desktop-file-validate packaging/desktop/io.github.nbe03xxx.llm-manager.desktop
git diff --check
```

A fresh development package was built from an out-of-tree copy with
`dpkg-buildpackage -us -uc -b`. Its build-time suite passed, and
`packaging/verify-deb.sh` verified the launchers, distinct PolicyKit actions,
manpages, desktop integration, notices, SBOM, permissions, and dependencies.
Archive inspection confirmed that the new execute client and both final-consent
UI modules are installed. Package metadata is `llm-manager 0.1.0~dev0`,
architecture `all`, installed size 1089 KiB. SHA-256:

```text
8b97f31d125a7b6a89dcc68fc4207732f6fffdf9e9ba6f51350275d11a26ef64
```

## Limits and next gate

The Ubuntu VM began and ended `shut off`; the transferred artifact and extraction
directory were deleted from guest and host. No package, PolicyKit prompt, system
service, target file, SSH configuration, or production state was changed. The
fresh development deb is package-composition evidence only and was not installed.
The next gate is a separately bounded installed PolicyKit/provisioning/OS test.
The normal GUI route remains unpublished until that gate is complete.
