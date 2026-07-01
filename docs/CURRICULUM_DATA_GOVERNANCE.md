# Curriculum Data Governance

This document describes the additive governance foundation for the CurriculumAdvisor repository.

## Purpose

The governance layer is designed to:

- capture stable baseline manifests for the current curriculum dataset
- validate operational offering templates without altering reasoning or catalogue data
- keep all curriculum data and reasoning logic untouched
- support future administrative workflows for curriculum data approval and release auditability

## Key Principles

1. Additive only
   - no existing execution path is changed
   - no current catalogue JSON file is moved or rewritten
   - governance artifacts live in new directories only

2. Baseline manifests
   - record checksums and file counts for the curriculum `data/` root
   - enable verification that the dataset is unchanged

3. Operational validation
   - supporting files such as course offerings are validated separately
   - these files are not yet part of graduation reasoning or catalogue loading

## Usage

From the repo root:

```bash
python tools/catalogue_guard.py snapshot \
  --data-root data \
  --output governance/releases/uct-2026-public-baseline.json \
  --release-id uct-2026-public-baseline \
  --academic-year 2026 \
  --created-by "CurriculumAdvisor project team"
```

```bash
python tools/catalogue_guard.py verify \
  --data-root data \
  --manifest governance/releases/uct-2026-public-baseline.json
```

```bash
python tools/catalogue_guard.py validate-offerings \
  --template governance/templates/course_offerings.example.json
```
