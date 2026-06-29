"""
UCT Handbook Extraper / Parser Template.
Extracts courses and major requirements from a UCT Faculty Handbook PDF
and formats them into the JSON structure required by CurriculumAdvisor.

Usage:
  python engine/extractor.py path/to/handbook.pdf output_dir/
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
# Matches course header: e.g., "INF2009F    SYSTEMS ANALYSIS"
_COURSE_HEADER_RE = re.compile(r"^([A-Z]{3,4}\d{4}[A-Z]?)\s+(.+)$")

# Matches NQF credits and level: e.g., "18 NQF credits at NQF level 6"
_NQF_RE = re.compile(r"(\d+)\s+NQF\s+credits\s+at\s+NQF\s+level\s+(\d+)", re.IGNORECASE)

# Matches prerequisites: e.g., "Course entry requirements: INF1002F/S or equivalent"
_PREREQ_RE = re.compile(r"Course\s+entry\s+requirements:\s*(.+?)(?:\n|Co-requisites|Objective|Course outline|DP requirements|$)", re.IGNORECASE)

# Matches offered semester: e.g., "First semester" or "Second semester"
_OFFERED_RE = re.compile(r"(first|second|both|either|full year)\s+semester", re.IGNORECASE)


def clean_text(text: str) -> str:
    """Clean up whitespace and common PDF artifacts."""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_prerequisites(prereq_text: str) -> List[str]:
    """
    Extract course codes from prerequisite text.
    E.g., "INF1002F/S or equivalent" -> ["INF1002F", "INF1002S"]
    """
    # Find all course codes (3-4 letters followed by 4 digits and optional letter)
    codes = re.findall(r"\b([A-Z]{3,4}\d{4}[A-Z]?)\b", prereq_text.upper())
    return sorted(list(set(codes)))


def parse_handbook(pdf_path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Parse the PDF and extract courses and major requirements."""
    print(f"Reading {pdf_path.name}...")
    reader = PdfReader(str(pdf_path))
    
    courses: List[Dict[str, Any]] = []
    majors: Dict[str, Any] = {}
    
    current_dept = "Unknown"
    
    print("Parsing pages...")
    for page_num, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        lines = text.splitlines()
        
        # Try to track department from page headers
        if lines and len(lines[0].strip()) < 50:
            header = lines[0].strip()
            if header.isupper() and not any(x in header for x in ["RULES", "CURRICULA", "HANDBOOK"]):
                current_dept = header.title()

        for i, line in enumerate(lines):
            line = line.strip()
            
            # 1. Check for Course Header
            m = _COURSE_HEADER_RE.match(line)
            if m:
                code, name = m.groups()
                # Look ahead for NQF credits, level, and prerequisites
                nqf_credits = 18
                nqf_level = 5
                prereqs = []
                offered = ["Semester 1"]
                description = ""
                
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
                if offered_match:
                    sem = offered_match.group(1).lower()
                    if "first" in sem:
                        offered = ["Semester 1"]
                    elif "second" in sem:
                        offered = ["Semester 2"]
                    else:
                        offered = ["Semester 1", "Semester 2"]
                
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
                
            # 2. Check for Major Requirements
            if "Requirements for a major in" in line:
                major_name_match = re.search(r"Requirements for a major in\s+(.+)", line, re.IGNORECASE)
                if major_name_match:
                    major_name = major_name_match.group(1).strip().title()
                    major_key = major_name.lower().replace(" ", "_").replace("&", "and")
                    
                    # Collect next 20 lines to find course codes
                    major_lookahead = " ".join(lines[i+1:i+21])
                    major_courses = re.findall(r"\b([A-Z]{3,4}\d{4}[A-Z]?)\b", major_lookahead.upper())
                    
                    if major_courses:
                        majors[major_key] = {
                            "name": major_name,
                            "department": current_dept,
                            "category": "bcom" if "commerce" in str(pdf_path).lower() else "bsc",
                            "humanities_major": False,
                            "required_courses": sorted(list(set(major_courses))),
                            "choice_groups": []
                        }

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
