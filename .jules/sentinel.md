## 2025-05-26 - Prompt Injection via direct un-delimited formatting in Prompt Engineer
**Vulnerability:** Untrusted user input (`transcript`) is directly formatted into the system prompt in `src/services/prompt_eng.py` without proper delimiters. This allows an attacker to execute an indirect prompt injection attack to bypass the system prompt instructions.
**Learning:** When writing system prompts that include user data, the user data should be isolated using delimiters like XML tags. Additionally, any untrusted user content should ideally be passed in the user message instead of the system prompt to avoid LLM confusion, if the architecture permits.
**Prevention:** Always structure LLM interactions by either providing clear XML tags separating system instructions from data injected into the system prompt, or pass user content within the user role messages exclusively.
## 2025-05-26 - OOM DoS via Unbounded Audio File Reads
**Vulnerability:** The `handle_voice` handler previously loaded entire downloaded audio files directly into memory without checking their actual size, relying only on Telegram's metadata duration.
**Learning:** Never trust client-provided file sizes or metadata. When processing file uploads, always read the file in chunks and enforce a hard byte limit during the read process to prevent out-of-memory crashes.
**Prevention:** Implement chunked reading with a cumulative size check, returning an error or dropping the connection if the `MAX_BYTES` limit is exceeded.
## 2025-05-26 - Privilege Escalation via Root User in Docker
**Vulnerability:** The `Dockerfile` did not specify a `USER`, causing the container to run as the `root` user.
**Learning:** Running containers as root increases the impact of Remote Code Execution (RCE) vulnerabilities, making container escape easier.
**Prevention:** Always create a non-root user and group using `addgroup` and `adduser`, use `COPY --chown` for application files, and switch to that user using the `USER` directive before the `CMD`.
