"""
UCT Handbook Extractor / Parser Template.
Extracts courses and major requirements from a UCT Faculty Handbook PDF
and formats them into the JSON structure required by CurriculumAdvisor.

Usage:
  python engine/extractor.py <path_to_handbook.pdf> <output_directory>
"""
import re
import json
import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple

try:
    from pypdf import PdfReader
except ImportError:
    print("Error: pypdf is required. Run: pip install pypdf")
    sys.exit(1)

# --- Regex Patterns ---

# Course code pattern: 2-4 uppercase letters + 4 digits + optional letter + optional slash suffixes
# Matches: INF2009F, ACC1015F/S, DOC1103F/S, GSB3002F/S/X/Z
_CODE_PAT = r"[A-Z]{2,4}\d{4}[A-Z]?(?:/[A-Z])*"

# Matches course header in prose format (description pages):
#   "ACC1015F/S  BUSINESS  ACUMEN FOR ACCOUNTANTS"
#   "ECO4013S  INTERNATIONAL  FINANCE"
# Allows multiple spaces between code and name (PDF artifact)
_COURSE_HEADER_RE = re.compile(
    rf"^({_CODE_PAT})\s{{2,}}(.+)$"
)

# Matches course line in tabular format (curriculum table pages):
#   "ACC1106F Financial Accounting ..............................18 5"
#   "DOC1103F/S Harnessing Personal Capital for Growth ..........2 5"
_TABLE_ROW_RE = re.compile(
    rf"^({_CODE_PAT})\s+(.+?)\s*\.{{2,}}\s*(\d+)\s+(\d+)\s*$"
)

# Matches NQF credits and level: e.g., "18 NQF credits at NQF level 6"
_NQF_RE = re.compile(r"(\d+)\s+NQF\s+credits\s+at\s+NQF\s+level\s+(\d+)", re.IGNORECASE)

# Matches prerequisites: e.g., "Course entry requirements: INF1002F/S or equivalent"
_PREREQ_RE = re.compile(r"Course\s+entry\s+requirements:\s*(.+?)(?:\n|Co-requisites|Objective|Course outline|DP requirements|$)", re.IGNORECASE)

# Matches offered semester: e.g., "First semester" or "Second semester"
_OFFERED_RE = re.compile(r"(first|second|both|either|full year)\s+semester", re.IGNORECASE)

# For extracting individual course codes from free text (prereqs, major lists, etc.)
_CODE_EXTRACT_RE = re.compile(rf"\b({_CODE_PAT})\b")


def clean_text(text: str) -> str:
    """Clean up whitespace and common PDF artifacts."""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_prerequisites(prereq_text: str) -> List[str]:
    """
    Extract course codes from prerequisite text.
    E.g., "INF1002F/S or equivalent" -> ["INF1002F", "INF1002S"]
    """
    codes = _CODE_EXTRACT_RE.findall(prereq_text.upper())
    # Expand slash suffixes: ACC1015F/S -> ACC1015F, ACC1015S
    expanded = []
    for code in codes:
        if "/" in code:
            match = re.match(r"([A-Z]{2,4}\d{4})", code)
            if match:
                base = match.group(1)
                suffixes = re.findall(r"[A-Z]", code[len(base):])
                for s in suffixes:
                    expanded.append(base + s)
        else:
            expanded.append(code)
    return sorted(list(set(expanded)))


def expand_slash_code(code: str) -> List[str]:
    """Expand slash suffixes: ACC1015F/S -> [ACC1015F, ACC1015S]"""
    if "/" in code:
        match = re.match(r"([A-Z]{2,4}\d{4})", code)
        if match:
            base = match.group(1)
            suffixes = re.findall(r"[A-Z]", code[len(base):])
            return [base + s for s in suffixes]
    return [code]


def is_page_header(line: str) -> bool:
    """Check if a line is a page header or page number."""
    line_clean = line.strip()
    if line_clean.isupper() and any(phrase in line_clean for phrase in ["BACHELOR OF", "COMMERCE", "BUSINESS SCIENCE", "AUGMENTED", "EXTENDED"]):
        return True
    if re.match(r"^\d+$", line_clean):
        return True
    if re.search(r"\s+\d+$", line_clean) and line_clean.isupper():
        return True
    return False


def reconstruct_specialisation_name(lines: List[str], index: int) -> str:
    """Reconstruct specialisation name from lines preceding the code."""
    # If the line immediately preceding starts with a full degree name, just use it
    prev_line = lines[index - 1].strip()
    if re.match(r"^(Bachelor of|BCom|BBusSc)", prev_line, re.IGNORECASE):
        return prev_line
        
    start_idx = index - 1
    # Scan forward from index-4 to index-1 to find the earliest start of the header
    for k in range(max(0, index - 4), index):
        line_clean = lines[k].strip()
        # Skip page headers
        if k == 0 and is_page_header(line_clean):
            continue
        if re.match(r"^(Bachelor|BCom|BBusSc|Ba|chelor|achelor|Augmented|Extended|Specialisation|Programme)", line_clean, re.IGNORECASE):
            start_idx = k
            break
    
    header_parts = []
    for k in range(start_idx, index):
        line_clean = lines[k].strip()
        if k == 0 and is_page_header(line_clean):
            continue
        header_parts.append(line_clean)
        
    full_name = " ".join(header_parts)
    
    # Clean up common PDF artifacts
    full_name = re.sub(r"\s+", " ", full_name)
    full_name = re.sub(r"\bBa\s+chelor\b", "Bachelor", full_name, flags=re.IGNORECASE)
    full_name = re.sub(r"\bB\s+achelor\b", "Bachelor", full_name, flags=re.IGNORECASE)
    
    # Handle cases where Ba or B was on a line that we missed or was cut off
    if full_name.lower().startswith("achelor"):
        full_name = "B" + full_name
    elif full_name.lower().startswith("chelor"):
        full_name = "Ba" + full_name
    
    return full_name.strip()


def infer_semester(code: str) -> List[str]:
    """Infer semester from course code suffix."""
    if "/" in code:
        return ["Semester 1", "Semester 2"]
    elif code.endswith("F"):
        return ["Semester 1"]
    elif code.endswith("S"):
        return ["Semester 2"]
    else:
        return ["Semester 1", "Semester 2"]


def parse_handbook(pdf_path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Parse the PDF and extract courses and major requirements."""
    print(f"Reading {pdf_path.name}...")
    reader = PdfReader(str(pdf_path))
    
    courses: List[Dict[str, Any]] = []
    seen_codes: set = set()  # Deduplicate across table + prose
    majors: Dict[str, Any] = {}
    
    current_dept = "Unknown"
    current_major_key = None
    
    # Regex for specialisation code
    _PROG_CODE_RE = re.compile(r"^\[([A-Z0-9]{8,12})\]$")
    
    print("Parsing pages...")
    for page_num, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        lines = text.splitlines()
        
        # Try to track department from page headers
        if lines and len(lines[0].strip()) < 50:
            header = lines[0].strip()
            if header.isupper() and not any(x in header for x in ["RULES", "CURRICULA", "HANDBOOK"]):
                current_dept = header.title()
            
            # Clear current major if we leave the curriculum section
            if "bachelor" not in header.lower():
                current_major_key = None

        for i, line in enumerate(lines):
            line = line.strip()
            
            # 1a. Check for Tabular Course Row (curriculum tables)
            tm = _TABLE_ROW_RE.match(line)
            if tm:
                raw_code = tm.group(1)
                name = tm.group(2).strip()
                credits = int(tm.group(3))
                nqf_level = int(tm.group(4))
                
                expanded_codes = expand_slash_code(raw_code)
                for code in expanded_codes:
                    if code not in seen_codes:
                        seen_codes.add(code)
                        courses.append({
                            "code": code,
                            "name": name.title(),
                            "credits": credits,
                            "nqf_level": nqf_level,
                            "prerequisites": [],
                            "offered": infer_semester(code),
                            "department": current_dept,
                            "description": f"Course outline for {code}."
                        })
                    
                    if current_major_key and current_major_key in majors:
                        if code not in majors[current_major_key]["required_courses"]:
                            majors[current_major_key]["required_courses"].append(code)
                continue

            # 1b. Check for Prose Course Header (description pages)
            m = _COURSE_HEADER_RE.match(line)
            if m:
                raw_code, name = m.groups()
                name = name.strip()
                
                # Skip false positives: name should be mostly uppercase
                if not any(c.isupper() for c in name):
                    continue
                
                # Look ahead for NQF credits, level, and prerequisites
                nqf_credits = 18
                nqf_level = 5
                prereqs = []
                
                # Scan next 15 lines for details
                lookahead = " ".join(lines[i+1:i+16])
                
                nqf_match = _NQF_RE.search(lookahead)
                if nqf_match:
                    nqf_credits = int(nqf_match.group(1))
                    nqf_level = int(nqf_match.group(2))
                    
                prereq_match = _PREREQ_RE.search(lookahead)
                if prereq_match:
                    prereqs = extract_prerequisites(prereq_match.group(1))
                    
                offered_match = _OFFERED_RE.search(lookahead)
                
                for code in expand_slash_code(raw_code):
                    offered = infer_semester(code)
                    if code.endswith("F"):
                        offered = ["Semester 1"]
                    elif code.endswith("S"):
                        offered = ["Semester 2"]
                    elif offered_match:
                        sem = offered_match.group(1).lower()
                        if "first" in sem:
                            offered = ["Semester 1"]
                        elif "second" in sem:
                            offered = ["Semester 2"]
                        else:
                            offered = ["Semester 1", "Semester 2"]
                    
                    # Prose data is richer – overwrite table entry if exists
                    if code in seen_codes:
                        # Update existing entry with richer data
                        for c in courses:
                            if c["code"] == code:
                                c["name"] = name.strip().title()
                                c["credits"] = nqf_credits
                                c["nqf_level"] = nqf_level
                                c["prerequisites"] = prereqs
                                c["offered"] = offered
                                break
                    else:
                        seen_codes.add(code)
                        courses.append({
                            "code": code,
                            "name": name.strip().title(),
                            "credits": nqf_credits,
                            "nqf_level": nqf_level,
                            "prerequisites": prereqs,
                            "offered": offered,
                            "department": current_dept,
                            "description": f"Course outline for {code}."
                        })
                continue
                
            # 2a. Check for Humanities Major Requirements
            if "Requirements for a major in" in line:
                major_name_match = re.search(r"Requirements for a major in\s+(.+)", line, re.IGNORECASE)
                if major_name_match:
                    major_name = major_name_match.group(1).strip().title()
                    major_key = major_name.lower().replace(" ", "_").replace("&", "and")
                    
                    # Collect next 20 lines to find course codes
                    major_lookahead = " ".join(lines[i+1:i+21])
                    major_courses = _CODE_EXTRACT_RE.findall(major_lookahead.upper())
                    
                    expanded_major_courses = []
                    for mc in major_courses:
                        expanded_major_courses.extend(expand_slash_code(mc))
                    
                    if expanded_major_courses:
                        majors[major_key] = {
                            "name": major_name,
                            "department": current_dept,
                            "category": "bcom" if "commerce" in str(pdf_path).lower() else "bsc",
                            "humanities_major": True,
                            "required_courses": sorted(list(set(expanded_major_courses))),
                            "choice_groups": []
                        }

            # 2b. Check for Commerce Specialisation Requirements
            prog_match = _PROG_CODE_RE.match(line)
            if prog_match:
                prog_code = prog_match.group(1)
                if prog_code.startswith("CB"):
                    major_name = reconstruct_specialisation_name(lines, i).title()
                    major_key = major_name.lower().replace(" ", "_").replace("&", "and").replace(":", "").replace(",", "")
                    major_key = re.sub(r"_+", "_", major_key)
                    
                    current_major_key = major_key
                    majors[major_key] = {
                        "name": major_name,
                        "code": prog_code,
                        "department": current_dept,
                        "category": "bcom" if "commerce" in str(pdf_path).lower() else "bsc",
                        "humanities_major": False,
                        "required_courses": [],
                        "choice_groups": []
                    }

    print(f"  Found {len(courses)} courses and {len(majors)} majors")
    return courses, majors


def main():
    if len(sys.argv) < 3:
        print("Usage: python engine/extractor.py <path_to_handbook.pdf> <output_directory>")
        sys.exit(1)
        
    pdf_path = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    
    if not pdf_path.exists():
        print(f"Error: File not found: {pdf_path}")
        sys.exit(1)
        
    output_dir.mkdir(parents=True, exist_ok=True)
    
    courses, majors = parse_handbook(pdf_path)
    
    # Save courses.json
    courses_file = output_dir / "courses.json"
    with open(courses_file, "w", encoding="utf-8") as f:
        json.dump(courses, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(courses)} courses to {courses_file}")
    
    # Save degree_requirements.json template
    reqs_file = output_dir / "degree_requirements.json"
    reqs_data = {
        "source": f"UCT Handbook Extracted from {pdf_path.name}",
        "programmes": {
            "regular_programme": {
                "name": "Regular Programme",
                "qualification_codes": ["HB001"],
                "minimum_duration_years": 3,
                "minimum_nqf_credits": 360,
                "minimum_nqf_level_7_credits": 120,
                "minimum_semester_courses": 20,
                "minimum_senior_semester_courses": 10,
                "minimum_majors": 2,
                "minimum_humanities_semester_courses": 12,
                "required_courses": []
            }
        },
        "majors": majors
    }
    with open(reqs_file, "w", encoding="utf-8") as f:
        json.dump(reqs_data, f, indent=2, ensure_ascii=False)
    print(f"Saved degree requirements template to {reqs_file}")


if __name__ == "__main__":
    main()
