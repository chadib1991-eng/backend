"""
UAE mobile phone validation.
Business rule: national number must match ^5[024568]\d{7}$
The phonenumbers library may accept more; our rule wins.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class Phone:
    e164: str      # +971501234567
    local: str     # 0501234567
    digits: str    # 971501234567   (for Meta / Snap hashing)
    tiktok: str    # +971501234567  (for TikTok hashing – same as e164)


_NATIONAL_RE = re.compile(r"^5[024568]\d{7}$")


def parse_uae_mobile(raw: str) -> Optional[Phone]:
    """
    Accept:  0501234567 | 501234567 | +971501234567
             971501234567 | 00971501234567
    Reject: landlines (04...), wrong mobile prefix, wrong length.
    Returns None if invalid.
    """
    if not raw:
        return None

    # Strip decorators
    cleaned = re.sub(r"[\s\-\(\)]", "", raw)

    # Work on digits only after stripping a leading +
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]

    # Must be digits from here
    if not cleaned.isdigit():
        return None

    # Derive national number
    if cleaned.startswith("00971"):
        national = cleaned[5:]
    elif cleaned.startswith("971"):
        national = cleaned[3:]
    elif cleaned.startswith("0"):
        national = cleaned[1:]
    else:
        national = cleaned

    if not _NATIONAL_RE.match(national):
        return None

    return Phone(
        e164=f"+971{national}",
        local=f"0{national}",
        digits=f"971{national}",
        tiktok=f"+971{national}",
    )
