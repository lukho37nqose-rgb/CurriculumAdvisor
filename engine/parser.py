"""UCT transcript parser.

The parser extracts facts only. Programme rules, credits and course status are
interpreted later against the selected handbook catalogue.
"""

import re

from .models import CourseResult, StudentRecord

_NAME_RE = re.compile(r"^Name:\s+(.+)", re.IGNORECASE)
_ID_RE = re.compile(r"^Campus\s+ID:\s+([A-Z0-9]+)", re.IGNORECASE)
_PROG_RE = re.compile(r"^Programme:\s+(.+)", re.IGNORECASE)
_SPEC_RE = re.compile(r"^Specialisation:\s+(.+)$", re.IGNORECASE)
_YEAR_RE = re.compile(r"^(?:Academic\s+Year|Year)?:?\s*(20\d{2})\s*$", re.IGNORECASE)

# Standard numeric result row:
# PHI 1024F Introduction To Philosophy 05 18 57 3
_COURSE_RE = re.compile(
    r"^([A-Z]{2,4})\s+(\d{4}[A-Z]{1,2})\s+(.+?)\s+"
    r"(\d{2})\s+(\d{1,2})\s+(\d{1,3})\s+(\S+)\s*$",
    re.IGNORECASE,
)

# Status-only rows such as AB, DPR, INC, DE, PA, UP or SP.
# Transcript result-status tokens; this is not a password or other credential.
_STATUS_TOKEN = (  # nosec B105
    r"A/SF|UF\s+SM|DPR|INC|EXA|GIP|ATT|LOA|OSS|AB|DE|OS|PA|UP|SP|SF|FS|UF|F|P"
)
_COURSE_STATUS_RE = re.compile(
    rf"^([A-Z]{{2,4}})\s+(\d{{4}}[A-Z]{{1,2}})\s+(.+?)\s+"
    rf"(\d{{2}})\s+(\d{{1,2}})\s+({_STATUS_TOKEN})\s*$",
    re.IGNORECASE,
)
_COURSE_NO_RESULT_RE = re.compile(
    r"^([A-Z]{2,4})\s+(\d{4}[A-Z]{1,2})\s+(.+?)\s+0\s*$",
    re.IGNORECASE,
)

_VALID_GRADES = {
    "1",
    "2+",
    "2-",
    "3",
    "F",
    "P",
    "PA",
    "UP",
    "SP",
    "FS",
    "SF",
    "A/SF",
    "AB",
    "DPR",
    "INC",
    "DE",
    "OS",
    "ATT",
    "GIP",
    "LOA",
    "EXA",
    "UF",
    "UF SM",
    "OSS",
}


class TranscriptPdfError(ValueError):
    """A stable, user-safe error raised for unsupported transcript PDFs."""


def _parse_grade(grade_str: str) -> str | None:
    grade = " ".join(grade_str.strip().upper().split())
    return grade if grade in _VALID_GRADES else None


def _normalise_name(raw: str) -> str:
    raw = re.sub(r"\s+Student\s+Records\s+Office.*$", "", raw, flags=re.IGNORECASE)
    if "," in raw:
        surname, given = [part.strip() for part in raw.split(",", 1)]
        return f"{given} {surname}"
    return raw.strip()


def parse_transcript_text(text: str) -> StudentRecord:
    lines = text.splitlines()
    student_id = ""
    name = ""
    programme = ""
    declared_majors: list[str] = []
    results: list[CourseResult] = []
    current_academic_year: int | None = None

    for raw_line in lines:
        line = " ".join(raw_line.strip().split())
        if not line:
            continue

        year_match = _YEAR_RE.match(line)
        if year_match:
            current_academic_year = int(year_match.group(1))
            continue

        match = _NAME_RE.match(line)
        if match and not name:
            name = _normalise_name(match.group(1))
            continue
        match = _ID_RE.match(line)
        if match and not student_id:
            student_id = match.group(1).strip().upper()
            continue
        match = _PROG_RE.match(line)
        if match and not programme:
            programme = match.group(1).strip()
            continue
        match = _SPEC_RE.match(line)
        if match:
            major_name = re.sub(
                r"\s+(Major|Specialisation|Specialization|Stream|Programme)\s*$",
                "",
                match.group(1).strip(),
                flags=re.IGNORECASE,
            )
            if major_name and major_name not in declared_majors:
                declared_majors.append(major_name)
            continue

        match = _COURSE_RE.match(line)
        if match:
            dept, number, course_name, level, credits, mark, grade = match.groups()
            mark_value = int(mark)
            if 0 <= mark_value <= 100:
                results.append(
                    CourseResult(
                        code=f"{dept.upper()}{number.upper()}",
                        name=course_name.strip(),
                        nqf_level=int(level),
                        nqf_credits=int(credits),
                        mark=mark_value,
                        grade=_parse_grade(grade),
                        academic_year=current_academic_year,
                    )
                )
                continue

        match = _COURSE_STATUS_RE.match(line)
        if match:
            dept, number, course_name, level, credits, grade = match.groups()
            results.append(
                CourseResult(
                    code=f"{dept.upper()}{number.upper()}",
                    name=course_name.strip(),
                    nqf_level=int(level),
                    nqf_credits=int(credits),
                    mark=None,
                    grade=_parse_grade(grade),
                    academic_year=current_academic_year,
                )
            )
            continue

        match = _COURSE_NO_RESULT_RE.match(line)
        if match:
            dept, number, course_name = match.groups()
            results.append(
                CourseResult(
                    code=f"{dept.upper()}{number.upper()}",
                    name=course_name.strip(),
                    nqf_level=0,
                    nqf_credits=0,
                    mark=None,
                    grade=None,
                    academic_year=current_academic_year,
                )
            )

    return StudentRecord(
        student_id=student_id,
        name=name,
        programme=programme,
        declared_majors=declared_majors,
        results=results,
    )


def parse_transcript_pdf(
    pdf_path_or_file,
    *,
    max_pages: int | None = None,
    max_objects: int | None = None,
    max_text_characters: int | None = None,
    reject_encrypted: bool = False,
) -> StudentRecord:
    """Extract transcript facts from a PDF.

    Optional public-upload limits are applied before and during extraction.
    They default to ``None`` so trusted local tooling and existing callers keep
    their previous behaviour.
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ImportError("pypdf is required: pip install pypdf") from exc

    source = pdf_path_or_file if hasattr(pdf_path_or_file, "read") else str(pdf_path_or_file)
    public_limits_enabled = (
        any(value is not None for value in (max_pages, max_objects, max_text_characters)) or reject_encrypted
    )
    try:
        reader = PdfReader(source, strict=False) if public_limits_enabled else PdfReader(source)
    except Exception as exc:
        raise TranscriptPdfError("The uploaded file is not a readable PDF transcript.") from exc

    if reject_encrypted and reader.is_encrypted:
        raise TranscriptPdfError("Encrypted or password-protected PDFs are not supported.")

    page_count = len(reader.pages)
    if max_pages is not None and page_count > max_pages:
        raise TranscriptPdfError(
            f"The transcript has {page_count} pages; the public limit is {max_pages} pages."
        )

    if max_objects is not None:
        object_count = 0
        try:
            object_count = sum(len(objects) for objects in reader.xref.values())
        except Exception:
            object_count = 0
        if object_count > max_objects:
            raise TranscriptPdfError(
                "The PDF is unusually complex and cannot be processed safely. "
                "Please export a simplified transcript PDF."
            )

    extracted: list[str] = []
    total_characters = 0
    try:
        for page in reader.pages:
            text = page.extract_text() or ""
            total_characters += len(text)
            if max_text_characters is not None and total_characters > max_text_characters:
                raise TranscriptPdfError(
                    "The PDF contains an unusually large amount of text and cannot be processed safely."
                )
            extracted.append(text)
    except TranscriptPdfError:
        raise
    except Exception as exc:
        raise TranscriptPdfError(
            "The PDF could not be read reliably. Please download a fresh transcript PDF and try again."
        ) from exc

    full_text = "\n".join(extracted)
    return parse_transcript_text(full_text)
