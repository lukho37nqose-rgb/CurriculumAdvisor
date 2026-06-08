import json
from pathlib import Path

import streamlit as st


st.set_page_config(page_title="Curriculum Advisor")
st.title("Curriculum Advisor")
st.write(
    "Select a Humanities programme, choose majors, then mark completed courses to see progress and next options."
)

BASE = Path(__file__).parent


def load_json(path: Path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Failed to load {path.name}: {e}")
        return None


courses = load_json(BASE / "courses.json") or []
rules = load_json(BASE / "degree_requirements.json") or {}
courses_by_code = {course["code"]: course for course in courses}
majors = rules.get("majors", {})
programmes = rules.get("programmes", {})


def course_label(course):
    nqf_level = get_nqf_level(course)
    semester_equivalent = get_semester_course_equivalent(course)
    return (
        f"{course['code']} - {course['name']} "
        f"({course.get('credits', '?')} NQF credits, level {nqf_level}, {semester_equivalent:g} semester-course eq.)"
    )


def prerequisites_met(course, completed_set):
    return all(prereq in completed_set for prereq in course.get("prerequisites", []))


def get_missing_prerequisites(course, completed_set):
    return [prereq for prereq in course.get("prerequisites", []) if prereq not in completed_set]


def is_senior_course(course):
    return course.get("year_level", 0) >= 2


def get_nqf_level(course):
    if "nqf_level" in course:
        return course["nqf_level"]
    year_level = course.get("year_level", 0)
    if year_level == 1:
        return 5
    if year_level == 2:
        return 6
    if year_level == 3:
        return 7
    if year_level >= 4:
        return 8
    return None


def get_course_suffix(code):
    suffix = ""
    for character in reversed(code):
        if character.isalpha():
            suffix = character + suffix
        else:
            break
    return suffix


def get_semester_course_equivalent(course):
    if "semester_course_equivalent" in course:
        return course["semester_course_equivalent"]

    suffix = get_course_suffix(course["code"])
    valuation = rules.get("credit_valuation_rules", {}).get("semester_course_equivalents", {})

    if suffix in valuation:
        return valuation[suffix]

    if suffix.endswith("W"):
        return valuation.get("W", 2)
    if suffix.endswith("H"):
        return valuation.get("H", 0.5)

    return 1


def is_humanities_course(course):
    department = course.get("department", "").lower()
    return department in {
        "history",
        "historical studies",
        "economics",
        "philosophy",
        "political studies",
        "sociology",
    }


def selected_major_names(selected_major_keys):
    return [majors[key]["name"] for key in selected_major_keys]


def has_forbidden_combination(selected_major_keys):
    chosen = set(selected_major_keys)
    for combo in rules.get("forbidden_major_combinations", []):
        if set(combo).issubset(chosen):
            return combo
    return None


def infer_degree(selected_major_keys):
    categories = {majors[key].get("category") for key in selected_major_keys}
    if categories == {"ba"}:
        return "Bachelor of Arts (BA)"
    if categories == {"bsocsc"}:
        return "Bachelor of Social Science (BSocSc)"
    if "ba" in categories and "bsocsc" in categories:
        return "BA or BSocSc: student may choose because majors cross both lists"
    if "non_humanities" in categories:
        return "Degree follows the Humanities Faculty major"
    return "Select majors to infer degree"


st.sidebar.header("Student pathway")

programme_key = st.sidebar.selectbox(
    "Programme",
    options=list(programmes.keys()),
    format_func=lambda key: programmes[key]["name"],
)
programme = programmes[programme_key]

major_count = st.sidebar.number_input(
    "How many majors?",
    min_value=2,
    max_value=3,
    value=2,
    step=1,
)

major_options = list(majors.keys())
selected_majors = st.sidebar.multiselect(
    "Selected majors",
    options=major_options,
    format_func=lambda key: majors[key]["name"],
    max_selections=major_count,
)

st.subheader("Degree classification")
st.write(f"Programme: **{programme['name']}**")
st.write(f"Selected majors: **{', '.join(selected_major_names(selected_majors)) or 'None yet'}**")
st.write(f"Likely registration: **{infer_degree(selected_majors)}**")

if len(selected_majors) < programme.get("minimum_majors", 2):
    st.warning(f"Select at least {programme.get('minimum_majors', 2)} majors.")

if len(selected_majors) != major_count:
    st.info(f"You said the student has {major_count} majors. Select exactly {major_count} major(s).")

if selected_majors and not any(majors[key].get("humanities_major") for key in selected_majors):
    st.error("At least one major must be offered by Humanities, including the School of Economics.")

forbidden_combo = has_forbidden_combination(selected_majors)
if forbidden_combo:
    forbidden_names = [majors.get(key, {"name": key})["name"] for key in forbidden_combo]
    st.error(f"This major combination is not permitted: {', '.join(forbidden_names)}.")

listed_only = [majors[key]["name"] for key in selected_majors if majors[key].get("status") == "listed_only"]
if listed_only:
    st.warning(
        "Major rules still need to be captured from the handbook for: "
        + ", ".join(listed_only)
        + ". The app can classify these majors, but cannot yet verify their detailed requirements."
    )

course_options = [course_label(course) for course in courses]
selected_courses = st.multiselect("Completed courses", options=course_options)
completed_codes = {label.split(" - ")[0] for label in selected_courses}
completed_courses = [courses_by_code[code] for code in completed_codes if code in courses_by_code]

completed_semester_courses = sum(get_semester_course_equivalent(course) for course in completed_courses)
completed_senior_courses = sum(
    get_semester_course_equivalent(course) for course in completed_courses if is_senior_course(course)
)
completed_humanities_courses = sum(
    get_semester_course_equivalent(course) for course in completed_courses if is_humanities_course(course)
)
completed_credits = sum(course.get("credits", 0) for course in completed_courses)
completed_level_7_credits = sum(
    course.get("credits", 0) for course in completed_courses if get_nqf_level(course) == 7
)

st.subheader("Faculty-wide progress")
st.write(
    f"Semester-course equivalents: {completed_semester_courses:g}/{programme['minimum_semester_courses']}"
)
st.write(
    f"Senior semester-course equivalents: {completed_senior_courses:g}/{programme['minimum_senior_semester_courses']}"
)
st.write(
    f"Humanities semester-course equivalents: {completed_humanities_courses:g}/{programme['minimum_humanities_semester_courses']}"
)
st.write(f"NQF credits: {completed_credits}/{programme['minimum_nqf_credits']}")
st.write(f"NQF level 7 credits: {completed_level_7_credits}/{programme['minimum_nqf_level_7_credits']}")

if programme_key == "extended_ba_bsocsc":
    st.write(
        f"Extended programme also requires {programme['introductory_humanities_courses_required']} introductory Humanities courses "
        f"and {programme['augmenting_courses_required']} augmenting courses."
    )

st.subheader("Major progress")

for major_key in selected_majors:
    major = majors[major_key]
    st.markdown(f"**{major['name']}**")

    if major.get("status") == "listed_only":
        st.write("Detailed handbook rules have not been added yet.")
        continue

    required_courses = major.get("required_courses", [])
    completed_required = [code for code in required_courses if code in completed_codes]
    missing_required = [code for code in required_courses if code not in completed_codes]

    st.write(f"Required courses completed: {len(completed_required)}/{len(required_courses)}")
    if missing_required:
        st.write("Missing required courses: " + ", ".join(missing_required))
    else:
        st.write("All captured required courses for this major are complete.")

    for group in major.get("choice_groups", []):
        completed_choices = [code for code in group["courses"] if code in completed_codes]
        missing_choices = [code for code in group["courses"] if code not in completed_codes]
        st.write(f"{group['name']}: {len(completed_choices)}/{group['choose']} completed")
        if len(completed_choices) < group["choose"]:
            st.write("Options still available: " + ", ".join(missing_choices))
        if group.get("note"):
            st.caption(group["note"])

available = [
    course
    for course in courses
    if course["code"] not in completed_codes and prerequisites_met(course, completed_codes)
]

blocked = []
for course in courses:
    if course["code"] in completed_codes:
        continue
    missing = get_missing_prerequisites(course, completed_codes)
    if missing:
        blocked.append({"course": course, "missing": missing})

st.subheader("Courses available next")
if available:
    for course in sorted(available, key=lambda item: (item.get("year_level", 99), item["code"])):
        st.markdown(f"**{course_label(course)}**")
        st.write(f"Department: {course.get('department', 'N/A')}")
        st.write(f"Offered: {', '.join(course.get('offered', []))}")
        st.write(course.get("description", ""))
else:
    st.write("No available courses yet.")

st.subheader("Blocked courses")
if blocked:
    for item in blocked:
        course = item["course"]
        st.markdown(f"**{course_label(course)}**")
        st.write(f"Missing prerequisites: {', '.join(item['missing'])}")
else:
    st.write("No blocked courses.")

st.subheader("Semester planner")
max_credits = st.number_input("Maximum credits for next semester", min_value=1, max_value=180, value=60)


def course_score(course):
    score = 0
    for major_key in selected_majors:
        major = majors[major_key]
        if course["code"] in major.get("required_courses", []):
            score += 30
        for group in major.get("choice_groups", []):
            if course["code"] in group.get("courses", []):
                score += 20
    score -= course.get("year_level", 0)
    return score


plan = []
planned_credits = 0
for course in sorted(available, key=lambda item: (-course_score(item), item["code"])):
    credits = course.get("credits", 0)
    if planned_credits + credits <= max_credits:
        plan.append(course)
        planned_credits += credits

if plan:
    st.write(f"Suggested next semester: {planned_credits} credits")
    for course in plan:
        st.write(f"- {course['code']} - {course['name']} ({course.get('credits', '?')} credits)")
else:
    st.write("No suggested plan fits within the selected credit load.")

st.subheader("Course explanations")
for course in courses:
    if course["code"] in completed_codes:
        explanation = "You have already completed this course."
    else:
        missing = get_missing_prerequisites(course, completed_codes)
        if missing:
            explanation = f"You cannot take this course yet. Missing: {', '.join(missing)}."
        else:
            explanation = "You can take this course next because the captured prerequisites are satisfied."

    with st.expander(f"{course['code']} - {course['name']}"):
        st.write(explanation)
        st.write(f"Department: {course.get('department', 'N/A')}")
        st.write(f"Offered: {', '.join(course.get('offered', []))}")
        st.write(course.get("description", ""))
