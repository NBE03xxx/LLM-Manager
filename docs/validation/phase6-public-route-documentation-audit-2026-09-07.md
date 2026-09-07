# Phase 6 public route documentation audit — 2026-09-07

README and the user recovery guide were compared with production availability
and the completed Phase 6 validation records. The prior wording grouped all
root and SSH mutation routes under "protocol incomplete", which was no longer
accurate for local-root manual restore.

The public documentation now distinguishes these boundaries:

- local-user and SSH-user Apply are published;
- local-user single-target manual restore is published;
- local-root manual restore has a dedicated implementation and disposable OS
  Gate, but remains unpublished pending active-desktop PolicyKit evidence;
- local-root Apply remains unpublished pending an evidence-based actionable
  Ollama rule;
- SSH-root Apply and SSH-user/root manual restore remain unpublished pending
  their dedicated protocols and Gates.

The recovery guide continues to describe only currently available user actions.
It does not instruct users to invoke the packaged but unpublished local-root
helpers directly. No availability allowlist or executable code was changed.

Six focused production availability/composition tests passed, covering all
Apply and restore route classifications and confirming that production exposes
local-user and SSH-user Apply but only local-user manual restore. `git diff
--check` also passed.
