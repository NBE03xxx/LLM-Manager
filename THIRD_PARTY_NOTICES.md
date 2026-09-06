# Third-party runtime dependencies

LLM-Manager source code and project-owned assets are licensed under MIT. The Debian packages do not vendor the following runtime dependencies; APT installs them as separate distribution packages. Their installed package copyright files are authoritative for the exact binaries delivered by the distribution.

| Component | Declared role | Upstream license summary | Upstream source |
|---|---|---|---|
| Python | runtime | PSF License | https://www.python.org/psf-landing/ |
| cryptography | backup encryption | Apache-2.0 OR BSD-3-Clause | https://github.com/pyca/cryptography/blob/main/LICENSE |
| SecretStorage | local Secret Service binding | BSD-3-Clause | https://github.com/mitya57/secretstorage/blob/master/LICENSE |
| PySide6 / Qt for Python | desktop GUI | LGPL-3.0-only OR (GPL-3.0-only WITH Qt-GPL-exception-1.0), or commercial terms | https://doc.qt.io/qtforpython-6.8/index.html |
| OpenSSH client | SSH transport | distribution package license metadata | https://www.openssh.com/portable.html |
| polkit / pkexec | local privilege authorization | distribution package license metadata | https://gitlab.freedesktop.org/polkit/polkit |
| systemd | service inspection and fixed helper operations | distribution package license metadata | https://github.com/systemd/systemd |
| sudo | remote helper authorization | distribution package license metadata | https://www.sudo.ws/about/license/ |

Qt and Qt for Python contain components under additional third-party licenses. The Debian package copyright metadata for the installed Qt/PySide6 build must be included in the resolved binary-environment SBOM review before release. See https://doc.qt.io/qtforpython-6.9/licenses.html.

The PySide6 summary above reflects the primary license choices in the Debian 13 and Ubuntu 26.04 installed package copyright files reviewed on 2026-09-05. It is not an exhaustive license expression for every file in PySide6 or Qt. The package metadata includes additional file-specific terms; preserve the distribution copyright files and common license texts when preparing release environment evidence. The Qt GPL exception is described at https://spdx.org/licenses/Qt-GPL-exception-1.0.html.
