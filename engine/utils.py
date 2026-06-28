"""
Utility functions for course weight, level, department, and major key normalisation.
Shared between rule_engine.py and reasoner.py to avoid circular imports.
"""
import re
from typing import List, Optional
from .models import Catalogue, StudentRecord

_SUFFIX_WEIGHTS = {
    "F": 1.0, "S": 1.0, "FS": 1.0, "SF": 1.0,
    "H": 0.5, "W": 2.0,
    "P": 1.0, "U": 1.0, "L": 1.0, "Z": 1.0,
}

_MAJOR_NAME_TO_KEY = {
    "history": "history",
    "historical studies": "history",
    "economics": "economics",
    "philosophy": "philosophy",
    "politics": "politics_governance",
    "politics & governance": "politics_governance",
    "politics and governance": "politics_governance",
    "political studies": "politics_governance",
    "sociology": "sociology",
    "african studies": "african_studies",
    "gender studies": "gender_studies",
    "linguistics": "linguistics",
    "anthropology": "anthropology",
    "archaeology": "archaeology",
    "psychology": "psychology",
    "social development": "social_development",
    "industrial sociology": "industrial_sociology",
    "applied statistics": "applied_statistics",
    "mathematical statistics": "mathematical_statistics",
    "theatre and dance studies": "theatre_dance_studies",
    "theatre & dance studies": "theatre_dance_studies",
    "the study of religions": "study_of_religions",
    "study of religions": "study_of_religions",
}


def _course_weight(code: str) -> float:
    """Return semester-course equivalent weight from the code suffix."""
    m = re.search(r"\d(\D+)$", code)
    if m:
        suffix = m.group(1).upper()
        return _SUFFIX_WEIGHTS.get(suffix, 1.0)
    return 1.0


def _is_senior(code: str) -> bool:
    """True if the course is 2000-level or above (senior = level 6/7)."""
    m = re.search(r"(\d)\d{3}", code)
    if m:
        return int(m.group(1)) >= 2
    return False


def _is_humanities(code: str, catalogue: Catalogue) -> bool:
    """
    True if the course is offered by a Humanities department.
    We treat all courses in our catalogue as Humanities unless
    they are explicitly non-humanities (e.g. MAM, STA).
    """
    non_humanities_prefixes = {"MAM", "STA"}
    prefix = re.match(r"[A-Z]+", code)
    if prefix and prefix.group() in non_humanities_prefixes:
        return False
    return True


def _normalise_major_keys(declared: List[str], catalogue: Catalogue) -> List[str]:
    """Convert declared major names to catalogue keys."""
    keys = []
    for name in declared:
        key = _MAJOR_NAME_TO_KEY.get(name.lower().strip())
        if key is None:
            # Try direct key lookup
            if name.lower().replace(" ", "_") in catalogue.majors:
                keys.append(name.lower().replace(" ", "_"))
            # else: skip (will generate a warning)
        else:
            keys.append(key)
    return keys


def _infer_programme_key(programme_name: str) -> str:
    """Map the student's programme string to a key in the catalogue."""
    name = programme_name.lower()
    if "philosophy, politics and economics" in name or "ppe" in name:
        return "bsocsc_ppe"
    elif "screen production" in name:
        return "ba_screen_production"
    elif "social work" in name or "bsw" in name:
        return "bsw"
    elif "fine art" in name:
        return "ba_fine_art"
    elif "music" in name or "bmus" in name:
        if "diploma" in name:
            return "diploma_music_performance"
        return "bmus"
    elif "theatre" in name or "performance" in name:
        if "diploma" in name:
            return "diploma_theatre_performance"
        return "ba_theatre_performance"
    elif "adult and community" in name or "acet" in name:
        return "higher_certificate_acet"
    elif "foundation phase" in name:
        return "advanced_certificate_fp"
    elif "intermediate phase" in name:
        return "advanced_certificate_ip"
    elif "extended" in name:
        return "extended_ba_bsocsc"
    return "regular_ba_bsocsc"
