"use strict";

const MAX_UPLOAD_MB = 20;
const MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024;
const MAX_RECOMMENDATIONS_PER_BATCH = 20;
const state = {
    faculty: null,
    context: null,
    programme: null,
    pathway: null,
    routeDetails: null,
    routeLoaded: false,
    routeVersion: 0,
    facultyVersion: 0,
    majors: {},
    courses: {},
    coursePage: 1,
    pageSize: 30,
    recommendationLimit: MAX_RECOMMENDATIONS_PER_BATCH,
    file: null,
    report: null,
};

const $ = id => document.getElementById(id);
const esc = value => String(value ?? "").replace(/[&<>'"]/g, character => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "'": "&#39;",
    '"': "&quot;",
}[character]));
const titleCase = value => String(value || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, character => character.toUpperCase());

function announce(message) {
    const region = $("statusRegion");
    region.textContent = "";
    window.setTimeout(() => {
        region.textContent = message;
    }, 20);
}

async function api(url, options = {}) {
    const headers = new Headers(options.headers || {});
    headers.set("Accept", "application/json");
    const response = await fetch(url, {
        ...options,
        headers,
        credentials: "same-origin",
    });
    let data = {};
    if (response.status !== 204) {
        try {
            data = await response.json();
        } catch {
            data = { detail: "Unexpected server response." };
        }
    }
    if (!response.ok) {
        const error = new Error(detailToMessage(data.detail));
        error.status = response.status;
        error.retryAfter = response.headers.get("Retry-After");
        throw error;
    }
    return data;
}

function detailToMessage(detail) {
    if (typeof detail === "string" && detail.trim()) {
        return detail;
    }
    if (Array.isArray(detail)) {
        const parts = detail
            .map(item => item?.msg || item?.detail || "")
            .filter(Boolean);
        if (parts.length) return parts.join(" ");
    }
    return "The request could not be completed. Please check the transcript file and try again.";
}

function setView(name, { scroll = true } = {}) {
    $("landingView").classList.toggle("hidden", name !== "landing");
    $("facultyView").classList.toggle("hidden", name !== "faculty");
    $("changeFacultyBtn").classList.toggle("hidden", name !== "faculty");
    if (scroll) {
        window.scrollTo({ top: 0, behavior: "smooth" });
    }
}

function clearElement(id) {
    $(id).textContent = "";
}

function resetRouteState({ clearYears = true } = {}) {
    state.routeVersion += 1;
    state.routeDetails = null;
    state.routeLoaded = false;
    state.majors = {};
    state.courses = {};
    state.coursePage = 1;
    state.recommendationLimit = MAX_RECOMMENDATIONS_PER_BATCH;
    state.file = null;
    state.report = null;

    for (const id of ["majorOne", "majorTwo", "majorThree"]) {
        if ($(id)) $(id).value = "";
    }
    for (const id of ["majorSearch", "courseSearch"]) {
        if ($(id)) $(id).value = "";
    }
    for (const id of ["majorCategory", "majorStatus", "courseLevel", "courseOffering"]) {
        if ($(id)) $(id).value = "";
    }
    if (clearYears && $("yearsRegistered")) {
        $("yearsRegistered").value = "";
    }

    $("transcriptFile").value = "";
    clearElement("selectedFile");
    clearElement("majorCount");
    clearElement("majorList");
    clearElement("courseCount");
    clearElement("courseList");
    clearElement("coursePager");
    clearElement("routeStatus");
    clearElement("results");
    $("analysisError").classList.add("hidden");
    clearElement("analysisError");
    $("processing").classList.add("hidden");
    $("uploadArea").classList.add("hidden");
    $("results").classList.add("hidden");
    $("uploadBox").classList.remove("drag");
    $("uploadBox").setAttribute("aria-busy", "false");
    switchTab("analyse", { focus: false });
    updateRouteControls();
}

async function loadFaculties() {
    try {
        const faculties = await api("/faculties");
        $("facultyGrid").innerHTML = faculties.map((faculty, index) => `
            <button class="faculty-card ${faculty.available ? "available" : "unavailable"}"
                    type="button"
                    data-key="${esc(faculty.key)}"
                    ${faculty.available ? "" : "disabled"}>
                <span class="status-pill">${faculty.available ? "Available" : "Coming soon"}</span>
                <span class="faculty-icon" aria-hidden="true">${index + 1}</span>
                <h3>${esc(faculty.name)}</h3>
                <p>${esc(faculty.description)}</p>
            </button>
        `).join("");
        document.querySelectorAll(".faculty-card.available").forEach(card => {
            card.addEventListener("click", () => openFaculty(card.dataset.key, "push"));
        });
    } catch (error) {
        $("facultyGrid").innerHTML = `<div class="error-box" role="alert">${esc(error.message)}</div>`;
    }
}

function updateHistory(mode, path, historyState = {}) {
    if (mode === "push") {
        history.pushState(historyState, "", path);
    } else if (mode === "replace") {
        history.replaceState(historyState, "", path);
    }
}

async function openFaculty(key, historyMode = "push") {
    const requestVersion = ++state.facultyVersion;
    announce("Loading faculty routes.");
    try {
        const context = await api(`/faculties/${encodeURIComponent(key)}`);
        if (requestVersion !== state.facultyVersion) return;

        state.faculty = key;
        state.context = context;
        state.programme = null;
        state.pathway = null;
        resetRouteState();

        $("facultyBreadcrumbName").textContent = context.name;
        $("facultyHeading").textContent = context.short_name || context.name;
        $("facultyIntro").textContent = context.key === "uct_humanities"
            ? "Select the route and intended majors before the transcript is analysed."
            : context.key === "uct_health"
                ? "Select the professional programme, Fundamentals route and cohort pathway where applicable before analysis."
                : "Select the qualification, curriculum length and cohort pathway before the transcript is analysed.";
        document.title = `CurriculumAdvisor · ${context.name} 2026`;
        populateProgrammes();
        setView("faculty");
        updateHistory(historyMode, `/faculty/${encodeURIComponent(key)}`, { faculty: key });
        $("facultyHeading").focus({ preventScroll: true });
        announce(`${context.name} routes loaded.`);
    } catch (error) {
        if (requestVersion !== state.facultyVersion) return;
        setView("landing");
        $("facultyGrid").insertAdjacentHTML(
            "afterbegin",
            `<div class="error-box" role="alert">${esc(error.message)}</div>`,
        );
        announce("The faculty route could not be loaded.");
    }
}

function programmeGroup(programme) {
    if (state.faculty === "uct_ebe") {
        if (programme.availability === "restricted") return "Transfer and access routes";
        if (programme.name.includes("Geomatics")) return "Geomatics";
        if (programme.name.includes("Chemical")) return "Chemical Engineering";
        if (programme.name.includes("Civil")) return "Civil Engineering";
        if (programme.name.includes("Electrical") || programme.name.includes("Mechatronics (Electrical")) return "Electrical Engineering programmes";
        if (programme.name.includes("Mechanical")) return "Mechanical Engineering programmes";
        if (programme.name.includes("Construction") || programme.name.includes("Property")) return "Construction and Property";
        return "Architecture";
    }
    if (state.faculty === "uct_law") {
        return programme.availability === "continuing_only"
            ? "Continuing-student LLB routes"
            : "Current LLB routes";
    }
    if (state.faculty === "uct_health") {
        if (programme.key.includes("mbchb") || programme.key.includes("nmfc")) return "Medicine and clinical training";
        if (["audiology", "speech", "occupational", "physiotherapy"].some(token => programme.key.includes(token))) return "Health and Rehabilitation Sciences";
        if (programme.key.includes("certificate") || programme.key.includes("diploma")) return "Certificates and diplomas";
        return "Other Health Sciences routes";
    }
    const category = programme.degree_category || "other";
    if (category.includes("bachelor")) return "Bachelor degrees";
    if (category === "diploma") return "Diplomas";
    if (category === "advanced_diploma") return "Advanced diplomas";
    if (programme.key.includes("certificate")) return "Certificates";
    return "General BA and BSocSc";
}

function populateProgrammes() {
    const groups = {};
    for (const programme of state.context.programmes) {
        const group = programmeGroup(programme);
        (groups[group] ??= []).push(programme);
    }
    let html = '<option value="">Choose a programme</option>';
    for (const [label, programmes] of Object.entries(groups)) {
        html += `<optgroup label="${esc(label)}">${programmes.map(programme => `
            <option value="${esc(programme.key)}">
                ${esc(programme.name)} · ${esc((programme.qualification_codes || []).join(", "))}
            </option>
        `).join("")}</optgroup>`;
    }
    $("programmeSelect").innerHTML = html;
    state.programme = null;
    state.pathway = null;
    populateMajors([]);
    populatePathways(null);
    renderRouteWelcome();
}

function populatePathways(programme) {
    const field = $("pathwayField");
    const select = $("pathwaySelect");
    if (!programme || !(programme.pathways || []).length) {
        field.classList.add("hidden");
        select.innerHTML = '<option value="">No pathway required</option>';
        state.pathway = null;
        return;
    }
    field.classList.remove("hidden");
    select.innerHTML = '<option value="">Choose a pathway</option>' + (programme.pathways || []).map(pathway => `
        <option value="${esc(pathway.key)}">
            ${esc(pathway.name)}${pathway.availability !== "open" ? ` · ${esc(titleCase(pathway.availability))}` : ""}
        </option>
    `).join("");
    if (programme.default_pathway_key) select.value = programme.default_pathway_key;
    state.pathway = (programme.pathways || []).find(pathway => pathway.key === select.value) || null;
}

function populateMajors(majors) {
    const options = ['<option value="">Choose a major</option>'];
    const groups = { BA: [], BSocSc: [], NON_HUMANITIES: [] };
    majors.forEach(major => (groups[major.category] ?? groups.NON_HUMANITIES).push(major));
    for (const [category, label] of [
        ["BA", "BA majors"],
        ["BSocSc", "BSocSc majors"],
        ["NON_HUMANITIES", "Recognised outside-Humanities majors"],
    ]) {
        if (!groups[category].length) continue;
        options.push(`<optgroup label="${label}">${groups[category].map(major => `
            <option value="${esc(major.key)}">
                ${esc(major.name)}${major.verification_status !== "verified" ? " · verify" : ""}
            </option>
        `).join("")}</optgroup>`);
    }
    for (const id of ["majorOne", "majorTwo", "majorThree"]) {
        $(id).innerHTML = options.join("");
    }
}

function selectedProgramme() {
    return state.context?.programmes.find(programme => programme.key === $("programmeSelect").value) || null;
}

function selectedPathway() {
    return state.programme?.pathways?.find(pathway => pathway.key === $("pathwaySelect").value) || null;
}

function selectedMajors() {
    return [...new Set([
        $("majorOne").value,
        $("majorTwo").value,
        $("majorThree").value,
    ].filter(Boolean))];
}

function programmeStats(programme) {
    const stats = [
        [`<b>${esc(programme.minimum_nqf_credits)}</b>`, "minimum NQF credits"],
        [`<b>${esc(programme.minimum_duration_years)}</b>`, "minimum years"],
    ];
    if (programme.minimum_semester_courses) {
        stats.splice(1, 0, [`<b>${esc(programme.minimum_semester_courses)}</b>`, "semester-course equivalents"]);
    }
    if (programme.minimum_senior_courses) {
        stats.splice(2, 0, [`<b>${esc(programme.minimum_senior_courses)}</b>`, "senior courses"]);
    } else if (Object.keys(programme.level_credit_requirements || {}).length) {
        const levels = Object.entries(programme.level_credit_requirements)
            .map(([level, credits]) => `${credits} at L${level}`)
            .join(" · ");
        stats.splice(1, 0, [`<b>${esc(levels)}</b>`, "level-credit minima"]);
    }
    return `<div class="rule-grid">${stats.slice(0, 4).map(([value, label]) => `
        <div class="rule-stat">${value}<span>${label}</span></div>
    `).join("")}</div>`;
}

function updateRouteControls() {
    const programme = state.programme;
    const structured = programme && programme.programme_type !== "general_degree";
    $("majorsField").classList.toggle("hidden", Boolean(structured));
    $("majorsTabButton").classList.toggle("hidden", Boolean(structured));
    if (structured && $("majorsTabButton").getAttribute("aria-selected") === "true") {
        switchTab("analyse", { focus: false });
    }
    const pathwayReady = !programme?.pathway_required || Boolean(selectedPathway());
    $("openRouteBtn").disabled = !programme || !pathwayReady;
    chooseFile(state.file, { announceError: false });
}

function renderRouteWelcome() {
    resetRouteState();
    const programme = selectedProgramme();
    if (!programme) {
        state.programme = null;
        state.pathway = null;
        populatePathways(null);
        $("routeWelcome").innerHTML = `
            <h2>Choose a programme to begin</h2>
            <p>The selection determines the qualification rules, streams, elective pool, registration period and progression thresholds.</p>
        `;
        $("routeCard").classList.add("hidden");
        updateRouteControls();
        return;
    }

    state.programme = programme;
    populatePathways(programme);
    populateMajors(programme.majors || []);
    const pathway = selectedPathway();
    state.pathway = pathway;
    const status = programme.availability !== "open"
        ? titleCase(programme.availability)
        : titleCase(programme.scope_status);
    const maximum = programme.maximum_registration_years
        ? ` · ordinary maximum ${esc(programme.maximum_registration_years)} years`
        : "";
    $("routeCard").classList.remove("hidden");
    $("routeCard").innerHTML = `
        <strong>${esc(programme.name)}</strong>
        ${esc(titleCase(programme.route_type))} route${maximum} · ${esc(programme.course_count)} scoped courses ·
        <span class="badge ${esc(programme.scope_status)}">${esc(status)}</span>
        ${programme.availability_note ? `<small>${esc(programme.availability_note)}</small>` : ""}
    `;
    const routeKind = programme.programme_type === "general_degree"
        ? "This flexible route applies major, elective, credit and faculty-recognition rules."
        : "This structured route applies its prescribed curriculum and, where relevant, a selected stream or concentration.";
    $("routeWelcome").innerHTML = `
        <div class="eyebrow eyebrow-blue">${esc((programme.qualification_codes || []).join(" · "))}</div>
        <h2>${esc(programme.name)}</h2>
        <p>${esc(routeKind)}</p>
        ${programmeStats(programme)}
        ${programme.pathway_required && !pathway ? `
            <div class="notice"><span aria-hidden="true">!</span><span>Select a stream, concentration or intake pattern before opening this route.</span></div>
        ` : ""}
    `;
    updateRouteControls();
    announce(`${programme.name} selected. Open the route to load its catalogue.`);
}

function pathwayChanged() {
    resetRouteState({ clearYears: true });
    state.pathway = selectedPathway();
    renderRouteWelcomeWithoutReset();
}

function renderRouteWelcomeWithoutReset() {
    const programme = state.programme;
    const pathway = selectedPathway();
    state.pathway = pathway;
    if (!programme) return;
    const pathwayLine = pathway ? `
        <div class="notice info">
            <span aria-hidden="true">↳</span>
            <span><strong>${esc(pathway.name)}</strong>${pathway.availability_note ? `<br>${esc(pathway.availability_note)}` : ""}</span>
            <span class="badge ${esc(pathway.verification_status)}">${esc(pathway.verification_status)}</span>
        </div>
    ` : "";
    const routeKind = programme.programme_type === "general_degree"
        ? "This flexible route applies major, elective, credit and faculty-recognition rules."
        : "This structured route applies its prescribed curriculum and selected pathway.";
    $("routeWelcome").innerHTML = `
        <div class="eyebrow eyebrow-blue">${esc((programme.qualification_codes || []).join(" · "))}</div>
        <h2>${esc(programme.name)}</h2>
        <p>${esc(routeKind)}</p>
        ${programmeStats(programme)}
        ${pathwayLine}
    `;
    updateRouteControls();
    announce(pathway ? `${pathway.name} selected. Open the route to load its catalogue.` : "Select a pathway before opening this route.");
}

function routeQuery() {
    const query = new URLSearchParams({
        faculty_key: state.faculty,
        programme_key: state.programme.key,
    });
    const pathway = selectedPathway();
    if (pathway) query.set("pathway_key", pathway.key);
    return query.toString();
}

async function loadCatalogue(routeVersion) {
    const query = routeQuery();
    const [majors, courses, routeDetails] = await Promise.all([
        api(`/majors?${query}`),
        api(`/catalogue?${query}`),
        api(`/programme?${query}`),
    ]);
    if (routeVersion !== state.routeVersion) return false;
    state.majors = majors;
    state.courses = courses;
    state.routeDetails = routeDetails;
    state.coursePage = 1;
    renderMajors();
    renderCourses();
    return true;
}

async function openRoute() {
    if (!state.programme || (state.programme.pathway_required && !selectedPathway())) return;
    const routeVersion = state.routeVersion;
    $("openRouteBtn").disabled = true;
    $("routeStatus").innerHTML = `
        <div class="route-loading" role="status">
            <span class="spinner" aria-hidden="true"></span>
            <span>Loading the selected route and its verified course roles…</span>
        </div>
    `;
    announce("Loading the selected academic route.");
    try {
        const loaded = await loadCatalogue(routeVersion);
        if (!loaded || routeVersion !== state.routeVersion) return;
        state.routeLoaded = true;
        clearElement("routeStatus");
        $("uploadArea").classList.remove("hidden");
        $("results").classList.add("hidden");
        switchTab("analyse", { focus: false });
        $("uploadHeading").focus({ preventScroll: true });
        $("uploadArea").scrollIntoView({ behavior: "smooth", block: "start" });
        announce(`Route loaded with ${Object.keys(state.courses).length} scoped courses.`);
    } catch (error) {
        if (routeVersion !== state.routeVersion) return;
        state.routeLoaded = false;
        $("routeStatus").innerHTML = `
            <div class="error-box" role="alert">
                <strong>The route could not be loaded.</strong><br>${esc(error.message)}
            </div>
        `;
        announce("The selected route could not be loaded.");
    } finally {
        updateRouteControls();
    }
}

function switchTab(name, { focus = true } = {}) {
    const tabs = [...document.querySelectorAll(".tab")];
    tabs.forEach(tab => {
        const selected = tab.dataset.tab === name;
        tab.classList.toggle("active", selected);
        tab.setAttribute("aria-selected", String(selected));
        tab.tabIndex = selected ? 0 : -1;
    });
    for (const panelName of ["analyse", "majors", "courses"]) {
        const panel = $(`${panelName}Tab`);
        const selected = panelName === name;
        panel.classList.toggle("hidden", !selected);
        panel.hidden = !selected;
    }
    if (focus) {
        const selectedTab = tabs.find(tab => tab.dataset.tab === name);
        selectedTab?.focus();
    }
}

function renderMajors() {
    const query = $("majorSearch").value.trim().toLowerCase();
    const category = $("majorCategory").value;
    const status = $("majorStatus").value;
    const rows = Object.values(state.majors)
        .filter(major => (
            (!query || `${major.name} ${major.handbook_code}`.toLowerCase().includes(query))
            && (!category || major.qualification === category)
            && (!status || major.verification_status === status)
        ))
        .sort((left, right) => left.name.localeCompare(right.name));
    $("majorCount").textContent = `${rows.length} major${rows.length === 1 ? "" : "s"} in this view`;
    $("majorList").innerHTML = rows.length ? rows.map(major => {
        const groups = (major.choice_groups || []).map(group => `
            <div><strong>${esc(group.label)}</strong> · choose ${esc(group.required)}
                <div class="code-list">${group.courses.map(code => `<span class="code-tag">${esc(code)}</span>`).join("")}</div>
            </div>
        `).join("");
        return `
            <article class="major-card">
                <div class="major-top">
                    <div>
                        <div class="course-code">${esc(major.handbook_code || major.key)}</div>
                        <div class="course-title">${esc(major.name)}</div>
                        <div class="major-meta">
                            <span>${esc(major.qualification)}</span>
                            <span>${major.faculty_owned ? `${esc(state.context?.short_name || "Faculty")}-owned` : "recognised external major"}</span>
                            <span>Handbook p. ${esc(major.source?.page || "—")}</span>
                        </div>
                    </div>
                    <span class="badge ${esc(major.verification_status)}">${esc(major.verification_status)}</span>
                </div>
                <details><summary>View structure</summary><div class="major-detail">
                    ${major.required_courses?.length ? `
                        <strong>Required courses</strong>
                        <div class="code-list">${major.required_courses.map(code => `<span class="code-tag">${esc(code)}</span>`).join("")}</div>
                    ` : "<p>No flat required-course list is asserted for this provisional pathway.</p>"}
                    ${groups}
                    ${(major.verification_notes || []).map(note => `<div class="notice">${esc(note)}</div>`).join("")}
                </div></details>
            </article>
        `;
    }).join("") : '<div class="empty">This structured programme does not use general-degree majors.</div>';
}

function filteredCourses() {
    const query = $("courseSearch").value.trim().toLowerCase();
    const level = $("courseLevel").value;
    const offering = $("courseOffering").value;
    return Object.values(state.courses)
        .filter(course => (
            (!query || `${course.code} ${course.name} ${course.department}`.toLowerCase().includes(query))
            && (!level || String(course.nqf_level) === level)
            && (!offering || (offering === "offered" ? (course.offered || []).length > 0 : (course.offered || []).length === 0))
        ))
        .sort((left, right) => left.code.localeCompare(right.code));
}

const COURSE_ROLE_LABELS = {
    required: { label: "required by route", cls: "required" },
    support: { label: "support course", cls: "support" },
    major_requirement: { label: "major requirement", cls: "major_requirement" },
    elective: { label: "permitted elective", cls: "elective" },
    outside_route: { label: "outside selected route", cls: "not_assessed" },
};

function courseRoleBadges(course) {
    const roles = course.route_roles?.length
        ? course.route_roles
        : [course.route_role || "outside_route"];
    return roles.map(role => {
        const display = COURSE_ROLE_LABELS[role] || COURSE_ROLE_LABELS.outside_route;
        return `<span class="badge ${esc(display.cls)}">${esc(display.label)}</span>`;
    }).join("");
}

function renderCourses() {
    const rows = filteredCourses();
    const pages = Math.max(1, Math.ceil(rows.length / state.pageSize));
    state.coursePage = Math.max(1, Math.min(state.coursePage, pages));
    const start = (state.coursePage - 1) * state.pageSize;
    const shown = rows.slice(start, start + state.pageSize);
    $("courseCount").textContent = `${rows.length} course${rows.length === 1 ? "" : "s"} · page ${state.coursePage} of ${pages}`;
    $("courseList").innerHTML = shown.length ? shown.map(course => `
        <article class="course-card">
            <div class="course-top">
                <div>
                    <div class="course-code">${esc(course.code)}</div>
                    <div class="course-title">${esc(course.name || "Untitled course")}</div>
                    <div class="course-meta">
                        <span>${esc(course.nqf_credits)} credits</span>
                        <span>NQF ${esc(course.nqf_level)}</span>
                        <span>${esc(course.department || "Department not recorded")}</span>
                    </div>
                </div>
                <div class="badge-stack">
                    ${courseRoleBadges(course)}
                    <span class="badge ${esc(course.verification_status)}">${esc(course.verification_status)}</span>
                </div>
            </div>
            <div class="course-detail">
                <div>${(course.offered || []).length ? `2026 offering: ${esc(course.offered.join(", "))}` : "Not offered in 2026 or no offering recorded."}</div>
                ${course.co_requisites?.length ? `<div>Co-requisite: ${esc(course.co_requisites.join(", "))}</div>` : ""}
                ${course.prerequisites?.length
                    ? `<div>Prerequisites: ${esc(course.prerequisites.join(", "))}</div>`
                    : course.prerequisites_verified
                        ? "<div>No course-code prerequisite recorded.</div>"
                        : "<div>Prerequisite requires manual verification.</div>"}
                ${course.recognition_note ? `<div><strong>Recognition:</strong> ${esc(course.recognition_note)}</div>` : ""}
            </div>
        </article>
    `).join("") : '<div class="empty">No courses match these filters.</div>';
    $("coursePager").innerHTML = `
        <button id="prevPage" type="button" ${state.coursePage <= 1 ? "disabled" : ""}>Previous</button>
        <span>${state.coursePage} / ${pages}</span>
        <button id="nextPage" type="button" ${state.coursePage >= pages ? "disabled" : ""}>Next</button>
    `;
    $("prevPage").onclick = () => {
        state.coursePage -= 1;
        renderCourses();
    };
    $("nextPage").onclick = () => {
        state.coursePage += 1;
        renderCourses();
    };
}

function showAnalysisError(message) {
    $("analysisError").textContent = message;
    $("analysisError").classList.remove("hidden");
    announce(message);
}

function chooseFile(file, { announceError = true } = {}) {
    $("analysisError").classList.add("hidden");
    clearElement("analysisError");
    if (!file) {
        state.file = null;
        clearElement("selectedFile");
        $("analyseBtn").disabled = true;
        return false;
    }
    const filename = String(file.name || "");
    const isPdf = filename.toLowerCase().endsWith(".pdf")
        && (!file.type || ["application/pdf", "application/octet-stream"].includes(file.type));
    if (!isPdf) {
        state.file = null;
        $("transcriptFile").value = "";
        clearElement("selectedFile");
        if (announceError) showAnalysisError("Please select a PDF transcript.");
        return false;
    }
    if (file.size > MAX_UPLOAD_BYTES) {
        state.file = null;
        $("transcriptFile").value = "";
        clearElement("selectedFile");
        if (announceError) {
            const sizeMb = (file.size / 1024 / 1024).toFixed(2);
            showAnalysisError(
                `What happened: this PDF is ${sizeMb} MB, which is larger than the ${MAX_UPLOAD_MB} MB upload limit. `
                + "What you can try: export or download a smaller official transcript PDF, or remove extra pages before uploading."
            );
        }
        return false;
    }
    state.file = file;
    $("selectedFile").textContent = `${filename} · ${(file.size / 1024 / 1024).toFixed(2)} MB`;
    const routeReady = state.routeLoaded
        && Boolean(state.programme)
        && (!state.programme.pathway_required || Boolean(selectedPathway()));
    $("analyseBtn").disabled = !routeReady;
    if (announceError) announce(`${filename} selected.`);
    return true;
}

async function analyse() {
    if (!state.file || !state.programme || !state.routeLoaded) return;
    $("analysisError").classList.add("hidden");
    clearElement("analysisError");
    $("processingText").textContent = `Reading transcript and applying ${state.context?.short_name || "faculty"} rules…`;
    $("processing").classList.remove("hidden");
    $("uploadBox").setAttribute("aria-busy", "true");
    $("analyseBtn").disabled = true;

    const params = new URLSearchParams({
        faculty: state.faculty,
        programme: state.programme.key,
        majors: selectedMajors().join(","),
    });
    const pathway = selectedPathway();
    if (pathway) params.set("pathway", pathway.key);
    const years = $("yearsRegistered").value;
    if (years) params.set("years_registered", years);
    const form = new FormData();
    form.append("file", state.file);

    try {
        state.report = await api(`/analyse?${params}`, { method: "POST", body: form });
        state.recommendationLimit = MAX_RECOMMENDATIONS_PER_BATCH;
        renderReport(state.report);
        $("uploadArea").classList.add("hidden");
        $("results").classList.remove("hidden");
        $("reportHeading")?.focus({ preventScroll: true });
        $("results").scrollIntoView({ behavior: "smooth", block: "start" });
        announce("Academic progress report ready.");
    } catch (error) {
        const suffix = error.status === 429 && error.retryAfter
            ? ` Try again in about ${error.retryAfter} seconds.`
            : "";
        showAnalysisError(`${error.message}${suffix}`);
    } finally {
        $("processing").classList.add("hidden");
        $("uploadBox").setAttribute("aria-busy", "false");
        chooseFile(state.file, { announceError: false });
    }
}

function requirementCard(requirement) {
    const percent = requirement.required > 0
        ? Math.max(0, Math.min(100, (requirement.current / requirement.required) * 100))
        : 0;
    return `
        <div class="requirement ${requirement.complete ? "done" : ""}">
            <div class="req-icon" aria-hidden="true">${requirement.complete ? "✓" : "!"}</div>
            <div>
                <h4>${esc(requirement.label)}</h4>
                <p>${esc(requirement.detail || requirement.explanation || "")}</p>
                <div class="progress" role="progressbar" aria-label="${esc(requirement.label)}" aria-valuemin="0" aria-valuemax="${esc(requirement.required)}" aria-valuenow="${esc(requirement.current)}"><i style="width:${percent}%"></i></div>
            </div>
            <span class="badge ${esc(requirement.status)}">${esc(requirement.status)}</span>
        </div>
    `;
}

function distinctionSection(distinction) {
    if (!distinction) return "";
    const subjects = (distinction.subjects || []).map(subject => `
        <article class="major-progress-card">
            <div class="course-top"><h4>${esc(subject.major)}</h4><span class="badge ${subject.eligible ? "complete" : esc(subject.status)}">${subject.eligible ? "award threshold met" : "not yet met"}</span></div>
            <p>${esc(subject.average)}% across ${esc(subject.senior_courses_assessed)} assessed senior courses</p>
            <small>${esc(subject.reason || "")}</small>
        </article>
    `).join("");
    return `
        <section class="result-section">
            <h3>Award and distinction assessment</h3>
            <div class="notice info">
                <span aria-hidden="true">ⓘ</span>
                <span><strong>${distinction.qualification_eligible ? "Qualification distinction thresholds appear met" : "Distinction not confirmed"}</strong><br>${esc(distinction.reason || "")}</span>
                <span class="badge ${esc(distinction.status)}">${esc(distinction.status)}</span>
            </div>
            ${subjects ? `<div class="major-progress major-grid-gap">${subjects}</div>` : ""}
        </section>
    `;
}

function majorProgressCard(major) {
    const completionClass = major.complete ? "complete" : "incomplete";
    const completionLabel = major.complete ? "represented requirements complete" : "incomplete";
    const verificationExplanation = major.complete && major.status !== "verified"
        ? '<span class="verification-note">Requirements represented in the system are complete, but the rule authority still requires verification.</span>'
        : "";
    return `
        <article class="major-progress-card">
            <div class="course-top">
                <h4>${esc(major.name)}</h4>
                <div class="badge-stack">
                    <span class="badge ${completionClass}">${completionLabel}</span>
                    <span class="badge ${esc(major.status)}">${esc(major.status)} rules</span>
                </div>
            </div>
            ${verificationExplanation}
            ${major.completed_requirements.length ? `<ul>${major.completed_requirements.map(item => `<li>✓ ${esc(item)}</li>`).join("")}</ul>` : ""}
            ${major.outstanding_requirements.length ? `<ul>${major.outstanding_requirements.map(item => `<li>${esc(item)}</li>`).join("")}</ul>` : ""}
        </article>
    `;
}

function readmissionSection(risk = {}) {
    let heading;
    let icon;
    let noticeClass;
    if (risk.at_risk === true) {
        heading = risk.status === "verified"
            ? "Possible risk identified"
            : "Possible risk identified in a provisional assessment";
        icon = "⚠";
        noticeClass = "";
    } else if (risk.assessed !== true) {
        heading = "Readmission position could not be verified from the available data";
        icon = "?";
        noticeClass = "";
    } else if (risk.status !== "verified") {
        heading = "No threshold failure identified in the provisional assessment";
        icon = "ⓘ";
        noticeClass = "info";
    } else {
        heading = "No threshold failure identified in the assessed rules";
        icon = "ⓘ";
        noticeClass = "info";
    }
    const details = [risk.basis, ...(risk.reasons || [])].filter(Boolean).join(" ");
    return `
        <section class="result-section">
            <h3>Readmission indicator</h3>
            <div class="notice ${noticeClass}">
                <span aria-hidden="true">${icon}</span>
                <span><strong>${esc(heading)}</strong><br>${esc(details || "No programme-specific conclusion could be produced.")}</span>
                <span class="badge ${esc(risk.status || "unverified")}">${esc(risk.status || "unverified")}</span>
            </div>
        </section>
    `;
}

function recommendationGroup(label, courses) {
    if (!courses.length) return "";
    return `
        <div class="recommend-group">
            <h4>${esc(label)}</h4>
            ${courses.map(course => `
                <div class="recommend">
                    <div><strong>${esc(course.code)} · ${esc(course.name)}</strong><small>${esc(course.reason)} · ${esc(course.credits)} credits</small></div>
                    <span class="badge ${esc(course.status)}">${esc(course.status)}</span>
                </div>
            `).join("")}
        </div>
    `;
}

function renderRecommendations() {
    const container = $("recommendations");
    if (!container || !state.report) return;
    const allCourses = state.report.eligible_courses || [];
    if (!allCourses.length) {
        container.innerHTML = '<div class="empty">No course recommendation can be made from the verified prerequisite data currently available.</div>';
        return;
    }
    const visible = allCourses.slice(0, state.recommendationLimit);
    const majorCourses = visible.filter(course => course.is_major_requirement);
    const otherCourses = visible.filter(course => !course.is_major_requirement);
    container.innerHTML = `
        <div class="recommend-summary">
            <span>Showing ${visible.length} of ${allCourses.length} route-visible courses</span>
            <span>Grouped by academic role</span>
        </div>
        ${recommendationGroup("Major or prescribed requirements", majorCourses)}
        ${recommendationGroup("Other courses visible to the selected route", otherCourses)}
        ${visible.length < allCourses.length ? `
            <div class="recommend-more"><button class="secondary-btn" id="showMoreRecommendations" type="button">Show ${Math.min(MAX_RECOMMENDATIONS_PER_BATCH, allCourses.length - visible.length)} more</button></div>
        ` : ""}
    `;
    $("showMoreRecommendations")?.addEventListener("click", () => {
        state.recommendationLimit += MAX_RECOMMENDATIONS_PER_BATCH;
        renderRecommendations();
        announce(`Showing ${Math.min(state.recommendationLimit, allCourses.length)} of ${allCourses.length} courses.`);
    });
}

function renderReport(report) {
    const completedBlocking = report.requirements.filter(requirement => requirement.complete && requirement.blocking).length;
    const totalBlocking = report.requirements.filter(requirement => requirement.blocking).length;
    const pathway = report.pathway_name ? ` · ${esc(report.pathway_name)}` : "";
    const majorSection = report.majors?.length ? `
        <section class="result-section">
            <h3>Major progress</h3>
            <div class="major-progress">${report.majors.map(majorProgressCard).join("")}</div>
        </section>
    ` : "";
    const warnings = report.warnings?.length
        ? report.warnings.map(warning => `<div class="warning">${esc(warning)}</div>`).join("")
        : '<div class="empty">No additional warning was produced.</div>';

    $("results").innerHTML = `
        <div class="result-hero">
            <div>
                <span class="badge ${esc(report.graduation_status)}">${esc(titleCase(report.graduation_status))}</span>
                <h2 id="reportHeading" tabindex="-1">${esc(report.student_name || "Academic progress report")}</h2>
                <p>${esc(report.programme_name)}${pathway} · ${esc(titleCase(report.scope_status))} scope</p>
            </div>
            <div class="score-ring" aria-label="${completedBlocking} of ${totalBlocking} blocking rules satisfied">
                <strong>${completedBlocking}/${totalBlocking}</strong>
                <small>blocking rules satisfied</small>
            </div>
        </div>
        <section class="result-section">
            <div class="metrics">
                <div class="metric"><b>${esc(report.credits_completed)}</b><span>NQF credits counted</span></div>
                <div class="metric"><b>${esc(report.level_7_credits)}</b><span>NQF level 7 credits</span></div>
                <div class="metric"><b>${esc(report.semester_course_equivalents)}</b><span>course equivalents</span></div>
            </div>
        </section>
        <section class="result-section"><h3>Qualification requirements</h3><div class="requirement-list">${report.requirements.map(requirementCard).join("")}</div></section>
        ${majorSection}
        ${distinctionSection(report.distinction)}
        ${readmissionSection(report.exclusion_risk)}
        <section class="result-section"><h3>Courses visible to this route</h3><div id="recommendations" class="recommend-list"></div></section>
        <section class="result-section"><h3>Warnings and limits</h3><div class="warning-list">${warnings}</div></section>
        <button class="secondary-btn section-gap" id="newAnalysis" type="button">Analyse another transcript</button>
    `;
    renderRecommendations();
    $("newAnalysis").addEventListener("click", () => {
        $("results").classList.add("hidden");
        clearElement("results");
        $("uploadArea").classList.remove("hidden");
        state.file = null;
        state.report = null;
        state.recommendationLimit = MAX_RECOMMENDATIONS_PER_BATCH;
        $("transcriptFile").value = "";
        chooseFile(null, { announceError: false });
        $("uploadHeading").focus({ preventScroll: true });
        announce("Ready for another transcript.");
    });
}

function resetLanding(historyMode = "push") {
    state.facultyVersion += 1;
    state.faculty = null;
    state.context = null;
    state.programme = null;
    state.pathway = null;
    resetRouteState();
    $("programmeSelect").innerHTML = '<option value="">Choose a programme</option>';
    $("pathwaySelect").innerHTML = '<option value="">Choose a pathway</option>';
    $("routeCard").classList.add("hidden");
    document.title = "CurriculumAdvisor · UCT Curriculum Reasoning 2026";
    setView("landing");
    updateHistory(historyMode, "/", {});
    announce("Faculty selection page.");
}

function handleTabKeydown(event) {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    const visibleTabs = [...document.querySelectorAll('.tab:not(.hidden)')];
    const currentIndex = visibleTabs.indexOf(event.currentTarget);
    let nextIndex = currentIndex;
    if (event.key === "ArrowRight") nextIndex = (currentIndex + 1) % visibleTabs.length;
    if (event.key === "ArrowLeft") nextIndex = (currentIndex - 1 + visibleTabs.length) % visibleTabs.length;
    if (event.key === "Home") nextIndex = 0;
    if (event.key === "End") nextIndex = visibleTabs.length - 1;
    event.preventDefault();
    switchTab(visibleTabs[nextIndex].dataset.tab, { focus: true });
}

$("programmeSelect").addEventListener("change", renderRouteWelcome);
$("pathwaySelect").addEventListener("change", pathwayChanged);
$("openRouteBtn").addEventListener("click", openRoute);
$("backBtn").addEventListener("click", () => resetLanding("push"));
$("changeFacultyBtn").addEventListener("click", () => resetLanding("push"));
$("brandLink").addEventListener("click", event => {
    event.preventDefault();
    resetLanding("push");
});
document.querySelectorAll(".tab").forEach(tab => {
    tab.addEventListener("click", () => switchTab(tab.dataset.tab, { focus: false }));
    tab.addEventListener("keydown", handleTabKeydown);
});
for (const id of ["majorSearch", "majorCategory", "majorStatus"]) {
    $(id).addEventListener("input", renderMajors);
}
for (const id of ["courseSearch", "courseLevel", "courseOffering"]) {
    $(id).addEventListener("input", () => {
        state.coursePage = 1;
        renderCourses();
    });
}
$("transcriptFile").addEventListener("change", event => chooseFile(event.target.files[0]));
$("analyseBtn").addEventListener("click", analyse);

const uploadBox = $("uploadBox");
["dragenter", "dragover"].forEach(eventName => uploadBox.addEventListener(eventName, event => {
    event.preventDefault();
    uploadBox.classList.add("drag");
}));
["dragleave", "drop"].forEach(eventName => uploadBox.addEventListener(eventName, event => {
    event.preventDefault();
    uploadBox.classList.remove("drag");
}));
uploadBox.addEventListener("drop", event => {
    const file = event.dataTransfer.files[0];
    if (file) chooseFile(file);
});

window.addEventListener("popstate", async () => {
    if (location.pathname.startsWith("/faculty/")) {
        const key = location.pathname.split("/").filter(Boolean).pop();
        if (key) await openFaculty(key, "none");
    } else {
        resetLanding("none");
    }
});

(async () => {
    await loadFaculties();
    if (location.pathname.startsWith("/faculty/")) {
        const key = location.pathname.split("/").filter(Boolean).pop();
        if (key) await openFaculty(key, "replace");
    } else {
        history.replaceState({}, "", "/");
    }
})();
