"""Quality gate: blocks secrets, noise and oversized transcripts from long-term memory."""
import re

SECRET_PATTERNS = [
    (r"(api[_-]?key|apikey|token|password|passwd|secret|private[_-]?key)\s*[:=]\s*\S+", "credential assignment"),
    (r"\b(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}|lpat_[A-Za-z0-9_]+)\b", "known token prefix"),
    (r"\b[0-9]{8,10}:[A-Za-z0-9_-]{35}\b", "bot token shape"),
    (r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----", "PEM private key"),
    (r"\b[A-Za-z0-9]{32,}\b(?=.*\b(key|secret|token)\b)", "long string near key-word"),
]

MIN_CONTENT_LEN = 12
MAX_CONTENT_LEN = 4000


def quality_gate(content: str, kind: str = "memory") -> tuple[bool, str]:
    """Long-term-value + secret gate. Returns (ok, reason).

    Blocks: secrets, too-short noise, raw transcripts (> MAX_CONTENT_LEN chars).
    """
    if not content or len(content.strip()) < MIN_CONTENT_LEN:
        return False, "too short to have long-term value"
    if len(content) > MAX_CONTENT_LEN:
        return False, "too long — likely raw transcript; summarize first"
    for pat, label in SECRET_PATTERNS:
        if re.search(pat, content, re.IGNORECASE):
            return False, f"secret detected ({label})"
    return True, ""
