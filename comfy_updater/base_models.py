"""Roll Civitai's base-model strings up into families.

Civitai records a base model per *version*, spelled however the creator or the
platform happened to write it. A real library turns up `Flux.1 D`,
`Flux.2 Klein 9B` and `Flux.2 Klein 9B-base` as three separate values, and four
different spellings of Wan Video. Grouping on the raw string shatters the list,
so the panel groups on the family and still prints the exact value on each row.

Unknown values are kept verbatim rather than swept into "Other", so a base
model released next month gets its own group instead of disappearing.
"""

from __future__ import annotations

# Ordered: the first matching prefix wins, so put longer, more specific
# prefixes before the shorter ones they start with.
_FAMILY_PREFIXES: tuple[tuple[str, str], ...] = (
    ("stable diffusion 1", "SD 1.5"),
    ("stable diffusion 2", "SD 2"),
    ("stable diffusion 3", "SD 3"),
    ("sd 1", "SD 1.5"),
    ("sd1", "SD 1.5"),
    ("sd 2", "SD 2"),
    ("sd2", "SD 2"),
    ("sd 3", "SD 3"),
    ("sd3", "SD 3"),
    ("sdxl", "SDXL"),
    ("stable cascade", "Stable Cascade"),
    ("svd", "SVD"),
    ("stable video", "SVD"),
    ("pony", "Pony"),
    ("illustrious", "Illustrious"),
    ("noobai", "NoobAI"),
    ("flux", "Flux"),
    ("wan", "Wan"),
    ("zimage", "Z-Image"),
    ("z-image", "Z-Image"),
    ("z image", "Z-Image"),
    ("ltxv", "LTXV"),
    ("ltx", "LTXV"),
    ("hunyuan", "Hunyuan"),
    ("qwen", "Qwen"),
    ("chroma", "Chroma"),
    ("anima", "Anima"),
    ("krea", "Krea"),
    ("minimax", "MiniMax"),
    ("hidream", "HiDream"),
    ("kolors", "Kolors"),
    ("aura", "AuraFlow"),
    ("playground", "Playground"),
    ("pixart", "PixArt"),
    ("mochi", "Mochi"),
    ("cogvideo", "CogVideoX"),
    ("open ai", "OpenAI"),
    ("openai", "OpenAI"),
)

UNKNOWN_FAMILY = "Unknown"


def base_family(base_model: str | None) -> str:
    """Return the family label for a Civitai base-model string."""
    value = (base_model or "").strip()
    if not value:
        return UNKNOWN_FAMILY

    lowered = value.lower()
    for prefix, family in _FAMILY_PREFIXES:
        if lowered.startswith(prefix):
            return family
    return value


def family_sort_key(family: str) -> tuple[int, str]:
    """Sort families alphabetically but keep the catch-all last."""
    return (1, "") if family == UNKNOWN_FAMILY else (0, family.lower())
