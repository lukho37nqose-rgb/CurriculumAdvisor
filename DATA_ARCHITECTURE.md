# CurriculumAdvisor Data Architecture

## UCT Humanities Faculty - 2025 Handbook Extraction

## Files in this directory

| File | Phase | Description |
|------|-------|-------------|
| `qualifications.json` | 1 | All degrees awarded in the Faculty: codes, NQF levels, min durations, max registration years |
| `faculty_rules.json` | 1 | Global rules applying across all qualifications (F1-F19) |
| `degree_rules_BA_BSocSc.json` | 2 | BA/BSocSc-specific rules (FB1-FB10): distinction, promotion, curricula structure |
| `majors.json` | 3 | Major definitions: required courses, choose-N structures, prerequisites, credit calculations |
| `courses_POL_PHI_ASL.json` | 4 | Course database seed: Politics, Philosophy, African Studies (all courses with credits, levels, prereqs) |
| `graduation_rules.json` | 5 | Graduation checklist engine: requirements, major completion logic, readmission flags |
| `exception_rules.json` | 6 | Edge cases: fail-twice, max registration, forbidden combos, distinction exclusions, double-counting |

## Questions the system can now answer

For BSocSc students with POL, PHI, or ASL majors:

| Question | How |
|----------|-----|
| Can I graduate? | Run all 8 checks in `graduation_rules.json > graduation_requirements` |
| How many credits do I have? | Sum `courses_passed.nqf_credits` from transcript |
| Which requirements are complete? | Evaluate each requirement in graduation checklist individually |
| Which requirements are outstanding? | Same - flag the ones that return false |
| What can I register for next semester? | Check each course in `courses_POL_PHI_ASL.json` against prerequisites and fail-count rules |
| Is my major complete? | Run major completion rules in `graduation_rules.json > major_completion_rules` |
| Have I hit the max registration period? | Check `years_registered` against `exception_rules.json > EXC_MAX_REG_PERIOD` |
| Am I eligible for distinction? | Run `graduation_rules.json > distinction_eligibility` |
| Am I at risk of exclusion? | Check against `graduation_rules.json > readmission_risk_flags` by year |

## Key structural decisions

**Credit counting:**

- 1000-level semester course = 18 NQF credits (level 5)
- 2000-level semester course = 24 NQF credits (level 6)
- 3000-level semester course = 30 NQF credits (level 7)
- Augmenting courses, such as `POL1010S`, = 10 credits, excluded from graduation course counts and class medal calculations

**What counts as senior:**

Level 6 and level 7 courses, meaning 2000-level and 3000-level courses.

**What counts as Humanities:**

Any course offered by a department in the Faculty of Humanities, including the School of Economics. Exceptions and edge cases are in `faculty_rules.json > FB5.x`.

**Majors sharing:**

1000-level courses can be shared across two majors. 2000 and 3000-level courses cannot. This is tracked in `exception_rules.json > EXC_1000_LEVEL_SHARED`.

## Courses not yet in the database

Phase 4 remaining work:

- History, English Literary Studies, Anthropology, Sociology, Psychology, Economics
- Gender Studies, Social Development, The Study of Religions, Industrial Sociology
- All non-Humanities majors, such as Law, Computer Science, Mathematics
- Fine Art, Music, Theatre courses

Extraction pattern: follow the same structure as `courses_POL_PHI_ASL.json`. Each course needs:

`course_code`, `name`, `department`, `nqf_credits`, `nqf_level`, `semester`, `is_senior`, `prerequisites`, and any `augmenting_course`.

## How to extend

1. New major: add a block to `majors.json` with `required_courses` and `prerequisites`.
2. New courses: add entries to `courses_[DEPT].json` following the existing schema.
3. New degree rules: add to `degree_rules_[DEGREE].json`.
4. New exception: add to `exception_rules.json` with an `id`, `rule_ref`, `condition`, `outcome`, and `flag`.
