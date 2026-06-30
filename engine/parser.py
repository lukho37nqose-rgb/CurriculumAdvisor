"""
UCT transcript PDF parser.
Extracts raw facts only — no conclusions about graduation status.

UCT transcript line format (from UCT_SRETSRPT.pdf):
  Name: Nqose, Lukho
  Campus ID: NQSLUK001
  Programme: Bachelor of Social Science
  Specialisation: African Studies Major

  Course lines:
    PHI 1024F Introduction To Philosophy 05 18 57 3
    ASL 1201S Representations of Africa 0        (no result yet)
"""
import re
from pathlib import Path
from typing import Optional
from .models import StudentRecord, CourseResult


_NAME_RE = re.compile(r"^Name:\s+(.+)", re.IGNORECASE)
_ID_RE = re.compile(r"^Campus\s+ID:\s+([A-Z0-9]+)", re.IGNORECASE)
_PROG_RE = re.compile(r"^Programme:\s+(.+)", re.IGNORECASE)
_SPEC_RE = re.compile(r"^Specialisation:\s+(.+)$", re.IGNORECASE)

_COURSE_RE = re.compile(
    r"^([A-Z]{2,4})\s+(\d{4}[A-Z]{1,2})\s+(.+?)\s+"
    r"(\d{2})\s+(\d{2})\s+(\d+)\s+(\S+)\s*$"
)
_COURSE_NO_RESULT_RE = re.compile(
    r"^([A-Z]{2,4})\s+(\d{4}[A-Z]{1,2})\s+(.+?)\s+0\s*$"
)


def _parse_grade(grade_str: str) -> Optional[str]:
    g = grade_str.strip()
    if g in ("1", "2+", "2-", "3", "F", "P", "PA", "UP", "SP", "FS"):
        return g
    return None


def _normalise_name(raw: str) -> str:
    """Convert 'Nqose, Lukho Student Records Office' -> 'Lukho Nqose'."""
    # Strip "Student Records Office" if present
    raw = re.sub(r"\s+Student\s+Records\s+Office.*$", "", raw, flags=re.IGNORECASE)
    if "," in raw:
        parts = [p.strip() for p in raw.split(",", 1)]
        return f"{parts[1]} {parts[0]}"
    return raw.strip()


def parse_transcript_text(text: str) -> StudentRecord:
    """Parse raw text extracted from a UCT transcript PDF."""
    lines = text.splitlines()
    student_id = ""
    name = ""
    programme = ""
    declared_majors: list[str] = []
    results: list[CourseResult] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        m = _NAME_RE.match(line)
        if m and not name:
            name = _normalise_name(m.group(1))
            continue

        m = _ID_RE.match(line)
        if m and not student_id:
            student_id = m.group(1).strip()
            continue

        m = _PROG_RE.match(line)
        if m and not programme:
            programme = m.group(1).strip()
            continue

        m = _SPEC_RE.match(line)
        if m:
            major_name = m.group(1).strip()
            # Clean up common trailing noise words
            major_name = re.sub(r"\s+(Major|Specialisation|Specialization|Stream|Programme)\s*$", "", major_name, flags=re.IGNORECASE)
            if major_name not in declared_majors:
                declared_majors.append(major_name)
            continue

        m = _COURSE_RE.match(line)
        if m:
            dept, num, course_name, nqf_level_str, nqf_credits_str, mark_str, grade_str = m.groups()
            code = f"{dept}{num}"
            results.append(CourseResult(
                code=code,
                name=course_name.strip(),
                nqf_level=int(nqf_level_str),
                nqf_credits=int(nqf_credits_str),
                mark=int(mark_str),
                grade=_parse_grade(grade_str),
            ))
            continue

        m = _COURSE_NO_RESULT_RE.match(line)
        if m:
            dept, num, course_name = m.groups()
            code = f"{dept}{num}"
            results.append(CourseResult(
                code=code,
                name=course_name.strip(),
                nqf_level=_infer_nqf_level(num),
                nqf_credits=_infer_nqf_credits(num),
                mark=None,
                grade=None,
            ))
            continue

    return StudentRecord(
        student_id=student_id,
        name=name,
        programme=programme,
        declared_majors=declared_majors,
        results=results,
    )


def parse_transcript_pdf(pdf_path) -> StudentRecord:
    """Extract text from a UCT transcript PDF and parse it."""
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ImportError("pypdf is required: pip install pypdf")

    reader = PdfReader(str(pdf_path))
    full_text = ""
    for page in reader.pages:
        full_text += (page.extract_text() or "") + "\n"
    return parse_transcript_text(full_text)


def _infer_nqf_level(course_num: str) -> int:
    if course_num and course_num[0].isdigit():
        return {1: 5, 2: 6, 3: 7}.get(int(course_num[0]), 5)
    return 5


def _infer_nqf_credits(course_num: str) -> int:
    if course_num and course_num[0].isdigit():
        return {1: 18, 2: 24, 3: 30}.get(int(course_num[0]), 18)
    return 18
