# Teacher Dashboard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a separate authenticated teacher dashboard with seven organized modules, a visual home page, responsive behavior, and the requested password.

**Architecture:** Keep the existing Python HTTP service and static frontend. Add signed teacher-session cookies, split login and dashboard routes, and reorganize existing API-backed actions without changing classroom data models.

**Tech Stack:** Static HTML/CSS/JavaScript, Python standard-library HTTP server, SQLite, unittest.

---

### Task 1: Add teacher session authentication

**Files:** `scripts/upload-service.py`, `scripts/test-upload-service.py`

1. Add login, session and logout endpoints.
2. Accept either the signed HttpOnly cookie or the legacy admin header.
3. Add success, wrong-password and logout tests.

### Task 2: Split the login page

**Files:** `codexai-site/dist/teacher/index.html`, `codexai-site/dist/teacher/teacher.js`, `codexai-site/dist/teacher/portal.css`

1. Replace the combined page with a focused login page.
2. Submit credentials to the session endpoint and redirect to the dashboard.
3. Preserve accessible errors and keyboard behavior.

### Task 3: Build the modular dashboard

**Files:** `codexai-site/dist/teacher/dashboard/index.html`, `codexai-site/dist/teacher/dashboard/dashboard.js`

1. Add the sidebar, top bar and seven content views.
2. Add the visual overview, charts, to-do list and activity timeline.
3. Port all existing class, course, review, delivery, lead and site-content actions.

### Task 4: Apply responsive visual design

**Files:** `codexai-site/dist/teacher/portal.css`

1. Implement dashboard tokens, navigation, panels, tables, dialogs and charts.
2. Add mobile drawer behavior and no-overflow layouts.
3. Respect reduced motion and keyboard focus.

### Task 5: Set and verify the requested password

**Files:** ignored local credential files and deployment environment only

1. Set the local teacher token to the requested value.
2. Regenerate the local credential note without committing the secret.
3. Deploy the service with the updated environment only after tests pass.

### Task 6: Validate and publish

1. Run the full service test suite and syntax checks.
2. Run a local server and verify login, navigation, modules and logout.
3. Capture desktop and mobile visual checks.
4. Deploy static files and service, then verify production health and login behavior.
