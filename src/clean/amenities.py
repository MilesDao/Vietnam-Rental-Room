"""Keyword-based amenity extraction from Vietnamese listing text.

Curated lexicon (docs/PLAN.md Phase 3), matched against ascii-folded text so
diacritic-dropped spelling variants ("khep kin" vs "khép kín") both hit.
NOT yet manually validated for precision/recall on a sample -- see the
cleaning report's backlog note and PLAN.md's checklist item for that.
"""
from __future__ import annotations

# key -> list of ascii-folded keyword fragments (matched as substrings)
AMENITY_LEXICON: dict[str, list[str]] = {
    "khep_kin": ["khep kin", "wc rieng", "toilet rieng", "ve sinh rieng"],
    "gio_giac_tu_do": ["tu do gio giac", "khong gio giac"],
    "gac_xep": ["gac xep", "gac lung"],
    "ban_cong": ["ban cong"],
    "may_giat": ["may giat"],
    "thang_may": ["thang may"],
    "khong_chung_chu": ["khong chung chu", "ko chung chu", "k chung chu"],
    "chung_chu": ["chung chu"],
    "dieu_hoa": ["dieu hoa", "may lanh"],
    "nong_lanh": ["nong lanh", "binh nong lanh"],
    "tu_lanh": ["tu lanh"],
    "cho_de_xe": ["cho de xe", "gui xe", "ham xe", "bai xe", "de o to"],
    "an_ninh": ["an ninh", "bao ve 24", "camera an ninh"],
    "noi_that_day_du": ["noi that day du", "full noi that", "day du noi that"],
    "cua_so": ["cua so", "thoang mat"],
    "gan_truong_hoc": ["gan truong", "canh truong", "sat truong dai hoc"],
}

# Pairs where the negative phrase is a substring-superset of the positive one
# ("khong chung chu" contains "chung chu"); negation wins.
_NEGATION_OVERRIDES: dict[str, str] = {"khong_chung_chu": "chung_chu"}


def extract_amenities(*texts: str | None) -> dict[str, bool]:
    """OR the lexicon across every text passed in (title, description, ...).

    Callers pass already ascii-folded text (see src.clean.text_clean.ascii_fold);
    this function does not fold itself so it can be applied to text that was
    folded once and reused across multiple lexicons/callers.
    """
    joined = " ".join(t or "" for t in texts)
    flags = {key: any(kw in joined for kw in kws) for key, kws in AMENITY_LEXICON.items()}
    for negative_key, positive_key in _NEGATION_OVERRIDES.items():
        if flags[negative_key]:
            flags[positive_key] = False
    return flags
