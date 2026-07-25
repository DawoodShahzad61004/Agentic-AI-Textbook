# Bugs

Numbered bug records for the Langflow learning project. Bugs are numbered sequentially
(`BUG-NNN`) and IDs are never reused.

---

### BUG-001 · Docker cannot pull Langflow image — `lookup auth.docker.io: no such host`

| Field | Detail |
|---|---|
| **Issue** | `docker run langflowai/langflow:latest` failed to download the image with a DNS lookup error. |
| **Found Date** | 2026-07-23 |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | Environment (Docker Desktop / WSL2), not project code |
| **Description** | First run of `docker run -p 7860:7860 langflowai/langflow:latest` reported `Unable to find image locally` (normal), then failed with `lookup auth.docker.io: no such host`. Docker could not resolve Docker Hub's auth/registry hosts. |
| **Root Cause** | Not Langflow and not a missing image. Windows host DNS actually resolved fine (`nslookup auth.docker.io` and `registry-1.docker.io` both returned addresses, and `curl https://auth.docker.io/token` succeeded), so the failure was stale DNS state inside Docker Desktop's internal WSL2/Linux VM rather than on the host. |
| **Solution** | Quit Docker Desktop completely, then `ipconfig /flushdns` and `wsl --shutdown` (Admin), restart Docker Desktop, and retry `docker pull hello-world` then `docker pull langflowai/langflow:latest`. If it recurs, pin explicit DNS (`{"dns":["1.1.1.1","8.8.8.8"]}`) in Docker Engine settings. The pull subsequently succeeded. Ultimately superseded by moving off Docker entirely — see ADR-001. |
| **Date Resolved** | 2026-07-23 |

---

### BUG-002 · Langflow container exits on startup — `Username and password must be set`

| Field | Detail |
|---|---|
| **Issue** | After the image pulled successfully, the Langflow container shut down immediately instead of serving on port 7860. |
| **Found Date** | 2026-07-23 |
| **Status** | Closed |
| **Severity** | MEDIUM |
| **File** | Environment (Docker container config), not project code |
| **Description** | Container logs ended with `Missing credentials: username=langflow, password=not set` followed by `ValueError: Username and password must be set`. The PyTorch and CORS lines in the same log were only warnings and did not cause the shutdown. |
| **Root Cause** | The current `langflowai/langflow:latest` image ships with login enabled by default and refuses to start without superuser credentials. The failed container also still owned the name `langflow`, blocking a clean re-run. |
| **Solution** | `docker rm langflow`, then start with auth env vars: `-e LANGFLOW_AUTO_LOGIN=false -e LANGFLOW_SUPERUSER=langflow -e LANGFLOW_SUPERUSER_PASSWORD="<strong-password>"` (the legacy default password `langflow` is rejected). For a private local experiment, `-e LANGFLOW_AUTO_LOGIN=true` bypasses the login screen. See Research topic 4. Superseded in practice by the local install (ADR-001). |
| **Date Resolved** | 2026-07-23 |

---

### BUG-003 · `python3.14 uv venv` fails — `can't open file '...\uv'`

| Field | Detail |
|---|---|
| **Issue** | Attempt to create a virtual environment errored with a file-not-found on `uv`. |
| **Found Date** | 2026-07-23 |
| **Status** | Closed |
| **Severity** | LOW |
| **File** | Environment (shell command), not project code |
| **Description** | Running `python3.14 uv venv` produced `can't open file 'C:\Users\LOQ\Desktop\Projects\Langflow-learning-project\uv': [Errno 2] No such file or directory`. |
| **Root Cause** | `python3.14 uv venv` tells Python to *execute a script file named `uv`*, so Python searched for `.\uv` and failed. `uv` is a standalone tool, not a Python script argument. |
| **Solution** | Invoke `uv` directly: `uv venv .venv --python 3.12` then `.\.venv\Scripts\Activate.ps1`. See ADR-003 for the Python version choice. |
| **Date Resolved** | 2026-07-23 |

---

### BUG-004 · `uv install langflow` — `unrecognized subcommand 'install'`

| Field | Detail |
|---|---|
| **Issue** | Package install command rejected by `uv`. |
| **Found Date** | 2026-07-23 |
| **Status** | Closed |
| **Severity** | LOW |
| **File** | Environment (shell command), not project code |
| **Description** | `uv install langflow` returned `error: unrecognized subcommand 'install'` with the hint `a similar subcommand exists: 'uv pip install'`. |
| **Root Cause** | `uv` has no top-level `install`; package installation goes through the pip-compatible interface. |
| **Solution** | Use `uv pip install langflow` (later pinned — see BUG-005 and ADR-002). |
| **Date Resolved** | 2026-07-23 |

---

### BUG-005 · `litellm==1.93.0` fails to build on Windows — `link.exe not found`

| Field | Detail |
|---|---|
| **Issue** | `uv pip install langflow` (which resolves langflow 1.11.0) failed while building `litellm==1.93.0` from source. |
| **Found Date** | 2026-07-23 |
| **Status** | Closed |
| **Severity** | HIGH |
| **File** | Environment (dependency build), not project code |
| **Description** | Resolution pulled `litellm==1.93.0` (via `langflow 1.11.0` → `langflow-base[complete] 0.11.0`). The wheel build ran `maturin`, auto-installed a temporary Rust toolchain, began compiling the pyo3 native crates, then failed: `error: linker link.exe not found` / `the msvc targets depend on the msvc linker but link.exe was not found`. |
| **Root Cause** | LiteLLM 1.93.0 ships Linux wheels but **no `win_amd64` wheel**, so Windows falls back to compiling the Rust/pyo3 `python-bridge` from source, which requires the MSVC C++ linker (`link.exe`) from Visual Studio Build Tools — not installed. This was the real blocker; the earlier suspicion that Python 3.14 was at fault was a red herring (the failure reproduced on 3.12 too). |
| **Solution** | Pin an older Langflow release that depends on a LiteLLM version with a prebuilt Windows wheel: `uv pip install --only-binary=litellm "langflow==1.10.2"`, which resolves `litellm==1.91.4` and installs cleanly with no compiler needed. Alternative (heavier): install Microsoft C++ Build Tools with the "Desktop development with C++" workload and build 1.11.0. See ADR-002 and Research topic 3. |
| **Date Resolved** | 2026-07-23 |

---
