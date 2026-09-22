"""SoundScope Artist Resolver: deterministic query aliases across metadata sources."""

from __future__ import annotations
import re
import unicodedata


def comparable_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(re.sub("[^\\w]+", " ", plain.casefold()).split())


def query_variants(query: str) -> list[str]:
    """Generate conservative artist-name variants without inventing identity."""
    clean = " ".join(query.strip().split())
    if not clean:
        return []
    variants = [clean]
    folded = comparable_name(clean)
    if folded.endswith(" music"):
        base = re.sub("\\s+music\\s*$", "", clean, flags=re.IGNORECASE).strip()
        if base:
            variants.append(base)
    else:
        variants.append(f"{clean} Music")
    out: list[str] = []
    seen: set[str] = set()
    for item in variants:
        key = comparable_name(item)
        if key and key not in seen:
            seen.add(key)
            out.append(item)
    return out


def names_compatible(requested: str, resolved: str) -> bool:
    """Accept exact names or the same name with a provider-style Music suffix."""
    left, right = comparable_name(requested), comparable_name(resolved)
    if not left or not right:
        return False
    if left == right:
        return True
    return left.removesuffix(" music").strip() == right.removesuffix(" music").strip()
