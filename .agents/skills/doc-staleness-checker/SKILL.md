---
name: doc-staleness-checker
description: >-
  Audits repository documentation for staleness, drift, and missing updates relative to current git HEAD and recent implementation changes. Detects when code commits, new endpoints, modified schemas, renamed modules, or evolved workflows have rendered existing docs outdated.
---

# Documentation Staleness Checker

Use this skill to audit repository documentation for staleness, drift, and divergence from code reality. Its goal is to answer:
1. Which documentation files are stale or incomplete?
2. What concrete evidence from git history, schemas, routes, or workflows proves they are stale?
3. What specific updates are required to bring documentation back into sync with current HEAD?

---

## 1. Core Principles

- **Code Leads, Docs Follow:** Documentation is a lagging representation of working software. When code and documentation disagree, code is reality and documentation is stale.
- **Tracked vs. Untracked Protection:** Only audit tracked documentation files (`git ls-files "*.md"`). **Never** inspect, grep, stage, or modify private data directories (e.g. `bank_statements/`) or untracked scratch notes (e.g. `docs/BUDGET_APP_TODO.md`).
- **Evidence-Based Staleness:** Never classify a document as stale based on intuition. Always cite the exact commit, model change, route addition, or filesystem restructure that caused the drift.

---

## 2. Staleness Audit Workflow

### Step 1: Establish Tracked Documentation Inventory
Discover all tracked documentation files in version control:
```bash
git ls-files "*.md" "docs/**/*.md" "frontend/**/*.md" "backend/**/*.md"
```
Group the inventory by area:
- Root guides (`README.md`, `AGENTS.md`)
- Checkpoints & Backlog (`docs/TODO.md`, `docs/checkpoints/`)
- Architecture Deep-Dives (`docs/architecture/`)
- API & Schema References (`docs/old_architecture/` or `docs/api/`)
- Frontend Guides (`frontend/README.md`)

### Step 2: Analyze Recent Implementation Deltas
Inspect recent git commits to identify what has changed since documentation was last refreshed:
```bash
git log -n 25 --oneline
```
Identify commits touching:
- ORM models or database schema (`models.py`, migrations)
- Pydantic request/response schemas (`schemas.py`)
- API route handlers (`backend/routers/`)
- Architecture modules (`backend/managers/`, `backend/access/`, `backend/domain/`)
- Ingestion parsers or adapters (`bank_statement_loader.py`)
- Frontend views and routing (`frontend/app/pages/`)
- Test harnesses and fixtures (`tests/`)

### Step 3: Run Staleness Detection Checks

Evaluate each tracked document against these 7 drift dimensions:

#### 1. Architectural & Filesystem Drift
- Does the documented directory structure match the actual tree?
- Are referenced module paths current (e.g. `backend/managers/budget_summary_manager.py` vs legacy `budget_summary.py`)?
- Are retired modules (e.g. legacy `crud/`) still referenced as active?
- Do newly added accessors, managers, or domain engines appear in architecture maps?

#### 2. API Endpoint & Routing Drift
- Compare documented endpoints in API references against `@router.*` definitions in `backend/routers/`:
  - Are newly introduced routes documented (e.g. `/upload/inspect`, `/upload/formats`)?
  - Are removed or renamed routes still documented?
  - Do documented HTTP methods, path parameters, and query parameters match route signatures?
  - Are request bodies and response models aligned with `schemas.py`?

#### 3. Data Model & Database Schema Drift
- Compare documented tables, ERDs, and schemas against `backend/models.py`:
  - Do all active SQLAlchemy models appear in ERDs and schema tables (e.g. `csv_formats`)?
  - Are column types, nullability, unique indexes (`lower(name)`), and check constraints accurate?
  - Are any Python-derived properties incorrectly described as database columns?

#### 4. Workflow & UI State Drift
- Compare user flow descriptions against frontend templates (e.g. `frontend/app/pages/`):
  - Do documented wizard steps match current step sequences (`stepLabels`)?
  - Are inline forms incorrectly described as modal dialogs?
  - Does the documentation reflect current client communication patterns (e.g. Nuxt Nitro `/api/**` proxy)?

#### 5. Milestones & Progress Tracking Drift
- Check backlog and checkpoint documents (e.g. `docs/TODO.md`):
  - Does the current stopping point reference the actual HEAD commit?
  - Are recently merged or completed feature slices checked off?
  - Does the documented verification baseline match recent test and build results?

#### 6. Cross-Link & Path Drift
- Scan for broken relative links:
  - Do markdown links (`[text](../path/to/file.md)`) resolve to existing files?
  - Did recent folder reorganizations (e.g. moving files into `old_architecture/` or `architecture/`) break references?

#### 7. Test Command & Baseline Drift
- Check testing instructions in developer setup guides (`DEVELOPMENT.md`, `README.md`):
  - Is the current primary test command documented (e.g. `python3 -m pytest`)?
  - Do setup guides avoid embedding volatile, hardcoded test counts that immediately stale?

---

## 3. Required Staleness Audit Report

When executing this skill, produce a structured audit report:

```markdown
# Documentation Staleness Audit Report

## 1. Repository Baseline
- **Current HEAD:** <commit hash and message>
- **Recent Relevant Commits:** <list of commits evaluated>

## 2. Staleness Audit Matrix

| File Path | Purpose | Stale? | Concrete Evidence of Staleness | Recommended Action |
|---|---|:---:|---|---|
| `docs/path/file.md` | Short description | Yes / No / Partial | Specific commit, missing endpoint, or model change | Update / Leave unchanged / Retire |

## 3. Detailed Drift Breakdown
For each stale document:
- **Missing Features / Endpoints:** What code exists that docs omit?
- **Obsolete Claims:** What documented behavior is no longer true?
- **Renamed / Moved Files:** What paths must be updated?
- **Broken Links:** Specific relative links that 404.

## 4. Prioritized Refresh Plan
List the exact documents to update in recommended execution order.
```
