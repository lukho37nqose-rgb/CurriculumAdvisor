import json
from html import escape
from pathlib import Path

import streamlit as st

st.set_page_config(
    page_title="Academic Advisor",
    page_icon=":mortar_board:",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Sora:wght@600;700&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    #MainMenu, footer, header { visibility: hidden; }
    .block-container { padding-top: 2rem; padding-bottom: 4rem; max-width: 820px; }

    /* ── Adaptive tokens ───────────────────────────────────────────────────────
       These pull from Streamlit's own CSS variables so they flip automatically
       between light and dark mode.
       --background-color and --text-color are set by Streamlit on :root.
       We define our own semantic tokens on top of them.
    */
    :root {
        --ca-accent:       #2F7A62;
        --ca-accent-warm:  #A65332;
        --ca-border:       rgba(128,128,128,0.2);
        --ca-surface:      rgba(128,128,128,0.06);
        --ca-surface-card: rgba(128,128,128,0.08);
        --ca-text:         var(--text-color, #173B3A);
        --ca-text-muted:   rgba(128,128,128,0.75);
        --ca-warn-bg:      rgba(166,83,50,0.1);
        --ca-warn-text:    var(--ca-accent-warm);
        --ca-err-bg:       rgba(200,64,64,0.1);
        --ca-err-text:     #C84040;
        --ca-prog-track:   rgba(128,128,128,0.18);
        --ca-tag-bg:       rgba(47,122,98,0.15);
        --ca-tag-border:   rgba(47,122,98,0.35);
    }

    /* ── Step bar ──────────────────────────────────────────────────────────── */
    .step-bar { display: flex; align-items: center; gap: 0; margin-bottom: 2.5rem; }
    .step {
        display: flex; align-items: center; gap: 8px;
        font-size: 0.8rem; font-weight: 500;
        color: var(--ca-text-muted);
        letter-spacing: 0.03em; text-transform: uppercase;
    }
    .step.active { color: var(--ca-text); }
    .step.done   { color: var(--ca-accent); }
    .step-dot {
        width: 28px; height: 28px; border-radius: 50%;
        background: var(--ca-surface);
        border: 1px solid var(--ca-border);
        display: flex; align-items: center; justify-content: center;
        font-size: 0.75rem; font-weight: 600;
        color: var(--ca-text-muted); flex-shrink: 0;
    }
    .step.active .step-dot { background: var(--ca-accent);      color: #fff; border-color: var(--ca-accent); }
    .step.done   .step-dot { background: var(--ca-accent-warm); color: #fff; border-color: var(--ca-accent-warm); }
    .step-line { flex: 1; height: 1px; background: var(--ca-border); min-width: 24px; }

    /* ── Page heading ──────────────────────────────────────────────────────── */
    .page-title {
        font-family: 'Sora', sans-serif; font-size: 1.75rem; font-weight: 700;
        color: var(--ca-text); margin: 0 0 0.25rem 0;
    }
    .page-subtitle { font-size: 0.95rem; color: var(--ca-text-muted); margin-bottom: 2rem; }

    /* ── Cards ─────────────────────────────────────────────────────────────── */
    .card {
        background: var(--ca-surface-card);
        border-radius: 8px; padding: 1.25rem 1.5rem;
        margin-bottom: 1rem; border: 1px solid var(--ca-border);
    }
    .card-label {
        font-size: 0.7rem; font-weight: 600; text-transform: uppercase;
        letter-spacing: 0.08em; color: var(--ca-text-muted); margin-bottom: 0.3rem;
    }
    .card-value { font-size: 1.05rem; font-weight: 600; color: var(--ca-text); }

    /* ── Progress bars ─────────────────────────────────────────────────────── */
    .prog-row {
        display: flex; justify-content: space-between; align-items: center;
        margin-bottom: 0.3rem; font-size: 0.875rem; color: var(--ca-text);
    }
    .prog-track {
        width: 100%; height: 6px; background: var(--ca-prog-track);
        border-radius: 99px; margin-bottom: 1rem; overflow: hidden;
    }
    .prog-fill          { height: 100%; border-radius: 99px; background: var(--ca-accent-warm); }
    .prog-fill.complete { background: var(--ca-accent); }

    /* ── Section header ────────────────────────────────────────────────────── */
    .major-header {
        font-family: 'Sora', sans-serif; font-size: 1rem; font-weight: 700;
        color: var(--ca-text); margin: 1.5rem 0 0.75rem 0;
        padding-bottom: 0.5rem; border-bottom: 2px solid var(--ca-border);
    }

    /* ── Inline alerts ─────────────────────────────────────────────────────── */
    .inline-warn {
        background: var(--ca-warn-bg); border-left: 3px solid var(--ca-accent-warm);
        border-radius: 0 6px 6px 0; padding: 0.6rem 1rem;
        font-size: 0.85rem; color: var(--ca-warn-text); margin: 0.5rem 0;
    }
    .inline-err {
        background: var(--ca-err-bg); border-left: 3px solid var(--ca-err-text);
        border-radius: 0 6px 6px 0; padding: 0.6rem 1rem;
        font-size: 0.85rem; color: var(--ca-err-text); margin: 0.5rem 0;
    }

    /* ── Buttons ───────────────────────────────────────────────────────────── */
    .stButton > button {
        border-radius: 8px; font-weight: 600; font-size: 0.9rem;
        padding: 0.55rem 1.5rem; border: none; transition: opacity 0.15s;
    }
    .stButton > button:hover { opacity: 0.88; }
    div[data-testid="column"] .stButton > button { width: 100%; }

    /* ── Divider ───────────────────────────────────────────────────────────── */
    .divider { height: 1px; background: var(--ca-border); margin: 1.5rem 0; }

    /* ── Summary grid ──────────────────────────────────────────────────────── */
    .focus-summary {
        display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.75rem;
        margin: 1.25rem 0 1.5rem 0;
    }
    .summary-item {
        background: var(--ca-surface-card);
        border: 1px solid var(--ca-border); border-radius: 8px;
        padding: 0.9rem 1rem;
    }
    .summary-number {
        font-family: 'Sora', sans-serif; font-size: 1.35rem; font-weight: 700;
        color: var(--ca-text); line-height: 1.1;
    }
    .summary-label { font-size: 0.76rem; color: var(--ca-text-muted); margin-top: 0.25rem; }

    /* ── Course rows ───────────────────────────────────────────────────────── */
    .course-row {
        background: var(--ca-surface-card);
        border: 1px solid var(--ca-border); border-radius: 8px;
        padding: 0.9rem 1rem; margin-bottom: 0.65rem;
    }
    .course-title  { color: var(--ca-text);       font-weight: 700; font-size: 0.95rem; margin-bottom: 0.2rem; }
    .course-meta   { color: var(--ca-text-muted);  font-size: 0.82rem; margin-bottom: 0.45rem; }
    .course-desc   { color: var(--ca-text);        font-size: 0.9rem; line-height: 1.45; }
    .missing-prereq{ color: var(--ca-err-text);    font-size: 0.86rem; margin-top: 0.2rem; }

    /* ── Multiselect tags ──────────────────────────────────────────────────── */
    div[data-baseweb="tag"] {
        background-color: var(--ca-tag-bg)     !important;
        border:       1px solid var(--ca-tag-border) !important;
    }
    div[data-baseweb="tag"] span { color: var(--ca-text) !important; }

    /* ── Responsive ────────────────────────────────────────────────────────── */
    @media (max-width: 640px) {
        .focus-summary { grid-template-columns: 1fr; }
        .step { font-size: 0.68rem; gap: 5px; }
        .step-dot { width: 24px; height: 24px; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Data loading ───────────────────────────────────────────────────────────────
BASE = Path(__file__).parent


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Could not load {path.name}: {e}")
        return None


courses_data = load_json(BASE / "courses.json") or []
rules = load_json(BASE / "degree_requirements.json") or {}
courses_by_code = {c["code"]: c for c in courses_data}
majors = rules.get("majors", {})
programmes = rules.get("programmes", {})


# ── Helpers ────────────────────────────────────────────────────────────────────
def get_nqf_level(course):
    if "nqf_level" in course:
        return course["nqf_level"]
    yl = course.get("year_level", 0)
    return {1: 5, 2: 6, 3: 7}.get(yl, 8 if yl >= 4 else None)


def get_course_suffix(code):
    suffix = ""
    for ch in reversed(code):
        if ch.isalpha():
            suffix = ch + suffix
        else:
            break
    return suffix


def get_semester_eq(course):
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


def is_senior(course):
    return course.get("year_level", 0) >= 2


def is_humanities(course):
    return course.get("department", "").lower() in {
        "history", "historical studies", "economics",
        "philosophy", "political studies", "sociology",
    }


def prereqs_met(course, completed):
    return all(p in completed for p in course.get("prerequisites", []))


def missing_prereqs(course, completed):
    return [p for p in course.get("prerequisites", []) if p not in completed]


def infer_degree(selected_keys):
    if not selected_keys:
        return "-"
    cats = {majors[k].get("category") for k in selected_keys}
    if cats == {"ba"}:
        return "Bachelor of Arts (BA)"
    if cats == {"bsocsc"}:
        return "Bachelor of Social Science (BSocSc)"
    if "ba" in cats and "bsocsc" in cats:
        return "BA or BSocSc (student choice - majors span both lists)"
    if "non_humanities" in cats:
        return "Degree follows the Humanities Faculty major"
    return "-"


def has_forbidden_combo(selected_keys):
    chosen = set(selected_keys)
    for combo in rules.get("forbidden_major_combinations", []):
        if set(combo).issubset(chosen):
            return combo
    return None


def get_major_courses(major_key):
    major = majors[major_key]
    codes = set(major.get("required_courses", []))
    for g in major.get("choice_groups", []):
        codes.update(g.get("courses", []))
    return codes


def prog_bar(value, total, label):
    pct = min(100, int(value / total * 100)) if total else 0
    css_class = "complete" if pct >= 100 else ""
    st.markdown(
        f'<div class="prog-row"><span>{label}</span><span>{value:g} / {total}</span></div>'
        f'<div class="prog-track"><div class="prog-fill {css_class}" style="width:{pct}%"></div></div>',
        unsafe_allow_html=True,
    )


def render_course_row(course, note=None, description=True):
    code = escape(course["code"])
    name = escape(course["name"])
    meta = f"Year {course.get('year_level', '?')} / {course.get('credits', '?')} credits"
    offered = course.get("offered")
    if offered:
        meta += f" / Offered: {', '.join(offered)}"

    note_html = f'<div class="missing-prereq">{escape(note)}</div>' if note else ""
    desc_html = ""
    if description and course.get("description"):
        desc_html = f'<div class="course-desc">{escape(course["description"])}</div>'

    st.markdown(
        f'<div class="course-row">'
        f'<div class="course-title">{code} - {name}</div>'
        f'<div class="course-meta">{escape(meta)}</div>'
        f'{note_html}{desc_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_degree_requirements(programme, completed_courses):
    done_sc = sum(get_semester_eq(c) for c in completed_courses)
    done_senior = sum(get_semester_eq(c) for c in completed_courses if is_senior(c))
    done_hum = sum(get_semester_eq(c) for c in completed_courses if is_humanities(c))
    done_cred = sum(c.get("credits", 0) for c in completed_courses)
    done_l7 = sum(c.get("credits", 0) for c in completed_courses if get_nqf_level(c) == 7)

    prog_bar(done_sc, programme["minimum_semester_courses"], "Semester-course equivalents")
    prog_bar(done_senior, programme["minimum_senior_semester_courses"], "Senior semester-course equivalents")
    prog_bar(done_hum, programme["minimum_humanities_semester_courses"], "Humanities equivalents")
    prog_bar(done_cred, programme["minimum_nqf_credits"], "NQF credits")
    prog_bar(done_l7, programme["minimum_nqf_level_7_credits"], "NQF level 7 credits")

    if st.session_state.programme_key == "extended_ba_bsocsc":
        st.caption(
            f"Extended programme also requires "
            f"{programme.get('introductory_humanities_courses_required', '?')} introductory Humanities courses "
            f"and {programme.get('augmenting_courses_required', '?')} augmenting courses."
        )


# ── Session state ──────────────────────────────────────────────────────────────
defaults = {
    "step": 1,
    "programme_key": list(programmes.keys())[0] if programmes else None,
    "major_count": 2,
    "selected_majors": [],
    "elective_codes": [],
    "completed_codes": set(),
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

STEPS = ["Student details", "Major progress", "Course options"]


def render_steps():
    parts = []
    for i, label in enumerate(STEPS, 1):
        s = st.session_state.step
        state = "done" if i < s else ("active" if i == s else "")
        icon = str(i)
        parts.append(
            f'<div class="step {state}">'
            f'<div class="step-dot">{icon}</div>{label}</div>'
        )
        if i < len(STEPS):
            parts.append('<div class="step-line"></div>')
    st.markdown(f'<div class="step-bar">{"".join(parts)}</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — Programme & Majors
# ══════════════════════════════════════════════════════════════════════════════
def step_1():
    render_steps()
    st.markdown('<p class="page-title">Build your student profile</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="page-subtitle">Start with the degree, majors, and electives that belong to this student.</p>',
        unsafe_allow_html=True,
    )

    prog_keys = list(programmes.keys())
    current_idx = prog_keys.index(st.session_state.programme_key) \
        if st.session_state.programme_key in prog_keys else 0

    st.markdown("**Degree**")
    prog_key = st.selectbox(
        "Degree",
        options=prog_keys,
        index=current_idx,
        format_func=lambda k: programmes[k]["name"],
        label_visibility="collapsed",
    )
    st.session_state.programme_key = prog_key

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    st.markdown("**Number of majors**")
    major_count = st.radio(
        "Number of majors",
        options=[2, 3],
        index=0 if st.session_state.major_count == 2 else 1,
        horizontal=True,
        label_visibility="collapsed",
    )
    st.session_state.major_count = major_count

    st.markdown("**Majors**")
    major_options = list(majors.keys())
    safe_defaults = [m for m in st.session_state.selected_majors if m in major_options]

    selected = st.multiselect(
        "Choose your majors",
        options=major_options,
        default=safe_defaults,
        format_func=lambda k: majors[k]["name"],
        max_selections=major_count,
        placeholder="Search for a major...",
        label_visibility="collapsed",
    )
    st.session_state.selected_majors = selected

    forbidden = has_forbidden_combo(selected)
    if forbidden:
        names = [majors.get(k, {"name": k})["name"] for k in forbidden]
        st.markdown(
            f'<div class="inline-err">This combination is not permitted: {", ".join(names)}.</div>',
            unsafe_allow_html=True,
        )

    if selected and not any(majors[k].get("humanities_major") for k in selected):
        st.markdown(
            '<div class="inline-warn">At least one major must be from the Humanities Faculty.</div>',
            unsafe_allow_html=True,
        )

    listed_only = [majors[k]["name"] for k in selected if majors[k].get("status") == "listed_only"]
    if listed_only:
        st.markdown(
            f'<div class="inline-warn">Handbook rules not yet captured for: {", ".join(listed_only)}. '
            "Classification works but detailed requirements won't show.</div>",
            unsafe_allow_html=True,
        )

    if selected:
        st.markdown(
            f'<div class="card"><div class="card-label">Student pathway</div>'
            f'<div class="card-value">{infer_degree(selected)}</div></div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    st.markdown("**Electives** *(optional)*")
    st.caption("Courses outside your majors - taken or planned.")

    all_major_codes = set()
    for mk in selected:
        all_major_codes.update(get_major_courses(mk))

    elective_pool = [c for c in courses_data if c["code"] not in all_major_codes]
    elective_opts_keys = [c["code"] for c in elective_pool]
    elective_opts_labels = {c["code"]: f"{c['code']} - {c['name']}" for c in elective_pool}
    safe_electives = [e for e in st.session_state.elective_codes if e in elective_opts_labels]

    chosen_electives = st.multiselect(
        "Electives",
        options=elective_opts_keys,
        default=safe_electives,
        format_func=lambda k: elective_opts_labels[k],
        placeholder="Search electives...",
        label_visibility="collapsed",
    )
    st.session_state.elective_codes = chosen_electives

    st.markdown("<br>", unsafe_allow_html=True)

    can_proceed = (
        len(selected) == major_count
        and not forbidden
        and bool(selected)
        and any(majors[k].get("humanities_major") for k in selected)
    )

    if st.button("Continue", disabled=not can_proceed, type="primary"):
        st.session_state.step = 2
        st.rerun()

    if selected and not can_proceed:
        st.caption(f"Select exactly {major_count} valid major(s) to continue.")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — Mark completed courses
# ══════════════════════════════════════════════════════════════════════════════
def step_2():
    render_steps()
    st.markdown('<p class="page-title">Major progress</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="page-subtitle">Mark completed courses for each major. Electives stay separate.</p>',
        unsafe_allow_html=True,
    )

    selected_majors = st.session_state.selected_majors
    new_completed: set = set()

    tabs = st.tabs([majors[k]["name"] for k in selected_majors])
    for tab, mk in zip(tabs, selected_majors):
        with tab:
            major = majors[mk]
            st.markdown(f'<p class="major-header">{major["name"]}</p>', unsafe_allow_html=True)

            major_codes = get_major_courses(mk)
            major_courses = sorted(
                [courses_by_code[c] for c in major_codes if c in courses_by_code],
                key=lambda c: (c.get("year_level", 99), c["code"]),
            )
            opts = {c["code"]: f"{c['code']} - {c['name']} (Year {c.get('year_level', '?')})"
                    for c in major_courses}
            prev = [c for c in st.session_state.completed_codes if c in opts]

            chosen = st.multiselect(
                f"Completed in {major['name']}",
                options=list(opts.keys()),
                default=prev,
                format_func=lambda k, o=opts: o[k],
                placeholder="Select completed courses...",
                label_visibility="collapsed",
                key=f"comp_{mk}",
            )
            new_completed.update(chosen)

            st.markdown(
                f'<div class="focus-summary">'
                f'<div class="summary-item"><div class="summary-number">{len(chosen)}</div>'
                f'<div class="summary-label">completed in this major</div></div>'
                f'<div class="summary-item"><div class="summary-number">{max(len(opts) - len(chosen), 0)}</div>'
                f'<div class="summary-label">left to review</div></div>'
                f'<div class="summary-item"><div class="summary-number">{len(opts)}</div>'
                f'<div class="summary-label">courses in this major plan</div></div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    elective_codes = st.session_state.elective_codes
    if elective_codes:
        st.markdown('<p class="major-header">Electives</p>', unsafe_allow_html=True)
        e_courses = [courses_by_code[c] for c in elective_codes if c in courses_by_code]
        e_opts = {c["code"]: f"{c['code']} - {c['name']}" for c in e_courses}
        e_prev = [c for c in st.session_state.completed_codes if c in e_opts]

        e_chosen = st.multiselect(
            "Completed electives",
            options=list(e_opts.keys()),
            default=e_prev,
            format_func=lambda k, o=e_opts: o[k],
            placeholder="Select completed electives...",
            label_visibility="collapsed",
            key="comp_electives",
        )
        new_completed.update(e_chosen)

    st.session_state.completed_codes = new_completed

    st.markdown("<br>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Back", use_container_width=True):
            st.session_state.step = 1
            st.rerun()
    with col2:
        if st.button("Show course options", type="primary", use_container_width=True):
            st.session_state.step = 3
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — Pathway dashboard
# ══════════════════════════════════════════════════════════════════════════════
def step_3():
    render_steps()

    programme = programmes[st.session_state.programme_key]
    selected_majors = st.session_state.selected_majors
    completed = st.session_state.completed_codes
    completed_courses = [courses_by_code[c] for c in completed if c in courses_by_code]

    st.markdown('<p class="page-title">Course options</p>', unsafe_allow_html=True)
    st.markdown(
        f'<p class="page-subtitle">{programme["name"]} / '
        f'{" & ".join(majors[k]["name"] for k in selected_majors)}</p>',
        unsafe_allow_html=True,
    )

    tabs = st.tabs([majors[k]["name"] for k in selected_majors])
    for tab, mk in zip(tabs, selected_majors):
        with tab:
            major = majors[mk]
            major_codes = get_major_courses(mk)
            st.markdown(f'<p class="major-header">{major["name"]}</p>', unsafe_allow_html=True)

            if major.get("status") == "listed_only":
                st.markdown(
                    '<div class="inline-warn">Detailed handbook rules not yet captured for this major.</div>',
                    unsafe_allow_html=True,
                )
                continue

            required = major.get("required_courses", [])
            done_req = [c for c in required if c in completed]
            major_course_objs = [courses_by_code[c] for c in major_codes if c in courses_by_code]

            available = sorted(
                [c for c in major_course_objs
                 if c["code"] not in completed and prereqs_met(c, completed)],
                key=lambda c: (c.get("year_level", 99), c["code"]),
            )
            blocked_items = sorted(
                [{"course": c, "missing": missing_prereqs(c, completed)}
                 for c in major_course_objs
                 if c["code"] not in completed and not prereqs_met(c, completed)],
                key=lambda x: (x["course"].get("year_level", 99), x["course"]["code"]),
            )

            done_major = [c for c in major_codes if c in completed]
            st.markdown(
                f'<div class="focus-summary">'
                f'<div class="summary-item"><div class="summary-number">{len(done_major)}</div>'
                f'<div class="summary-label">major courses completed</div></div>'
                f'<div class="summary-item"><div class="summary-number">{len(available)}</div>'
                f'<div class="summary-label">available now</div></div>'
                f'<div class="summary-item"><div class="summary-number">{len(blocked_items)}</div>'
                f'<div class="summary-label">blocked in this major</div></div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            if required:
                prog_bar(len(done_req), len(required), "Required courses")

            for group in major.get("choice_groups", []):
                done_g = [c for c in group["courses"] if c in completed]
                prog_bar(len(done_g), group["choose"], group["name"])
                if group.get("note"):
                    st.caption(group["note"])

            st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
            st.markdown(f"**Courses available now** ({len(available)})")
            if available:
                for c in available:
                    render_course_row(c)
            else:
                st.caption("No major courses available yet. Check the blocked list for missing prerequisites.")

            with st.expander(f"Blocked in this major ({len(blocked_items)})", expanded=False):
                if not blocked_items:
                    st.caption("No blocked courses in this major.")
                for item in blocked_items:
                    c = item["course"]
                    render_course_row(c, note=f"Still need: {', '.join(item['missing'])}", description=False)

    elective_codes = st.session_state.elective_codes
    if elective_codes:
        with st.expander("Electives", expanded=False):
            done_el = [c for c in elective_codes if c in completed]
            prog_bar(len(done_el), len(elective_codes), "Electives completed")

            remaining = [courses_by_code[c] for c in elective_codes
                         if c not in completed and c in courses_by_code]
            if remaining:
                st.markdown("**Remaining electives**")
                for c in remaining:
                    avail = prereqs_met(c, completed)
                    miss = missing_prereqs(c, completed)
                    note = None if avail else f"Still need: {', '.join(miss)}"
                    render_course_row(c, note=note, description=avail)

    with st.expander("Degree-wide requirements", expanded=False):
        render_degree_requirements(programme, completed_courses)

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Edit progress", use_container_width=True):
            st.session_state.step = 2
            st.rerun()
    with col2:
        if st.button("Edit profile", use_container_width=True):
            st.session_state.step = 1
            st.rerun()


# ── Router ─────────────────────────────────────────────────────────────────────
if st.session_state.step == 1:
    step_1()
elif st.session_state.step == 2:
    step_2()
elif st.session_state.step == 3:
    step_3()
