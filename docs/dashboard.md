# Dashboard Guide

## Table of Contents

- [Modes](#modes)
  - [Static Mode (`releaseboard generate`)](#static-mode-releaseboard-generate)
  - [Interactive Mode (`releaseboard serve`)](#interactive-mode-releaseboard-serve)
- [Sections](#sections)
  - [Toolbar (Interactive Only)](#toolbar-interactive-only)
  - [Analysis Status Bar (Interactive Only)](#analysis-status-bar-interactive-only)
  - [Config Drawer (Interactive Only)](#config-drawer-interactive-only)
  - [Delete Confirmation Modal (Interactive Only)](#delete-confirmation-modal-interactive-only)
  - [Immediate Refresh](#immediate-refresh)
  - [Readiness Ring](#readiness-ring)
  - [Metric Cards](#metric-cards)
  - [Charts](#charts)
  - [Filters](#filters)
  - [Attention Panel](#attention-panel)
  - [Layer Sections](#layer-sections)
  - [Detail Modal](#detail-modal)
  - [Summary Report](#summary-report)
- [Visual Design](#visual-design)
- [Theme Support](#theme-support)
- [Layout Templates](#layout-templates)
  - [Predefined Templates](#predefined-templates)
- [Print Support](#print-support)

## Modes

ReleaseBoard has two dashboard modes:

### Static Mode (`releaseboard generate`)
Produces a self-contained HTML file. All features below work except the interactive toolbar, config panel, and live analysis.

### Interactive Mode (`releaseboard serve`)
Adds a toolbar, live analysis status bar, and a config drawer with full editing support. All static features are also available.

## Sections

### Toolbar (Interactive Only)
Appears below the header with action buttons. The toolbar uses **sticky positioning** so primary action buttons (Analyze, Configuration, Export) remain visible while scrolling long dashboards:
- **Analyze** — trigger a new analysis, status bar shows real-time progress via SSE
- **Stop** — cancel a running analysis; UI immediately transitions to "Stopping…" state
- **Configuration** — open the config drawer
- **Export HTML** — download a static self-contained HTML snapshot
- **Export Config** — download current config as JSON
- **Status indicator** — shows current state (Ready / Analyzing / Stopping / Completed / Cancelled / Failed)
- **Unsaved badge** — appears when draft config differs from saved version
- **Layout template bar** — row of template buttons below the toolbar to switch dashboard layout (Default, Executive, Release Manager, Engineering, Compact, plus user-created templates); active template is highlighted

### Analysis Status Bar (Interactive Only)
Appears during analysis with:
- Phase label (Starting → Analyzing → Stopping → Completed/Cancelled/Failed)
- Progress bar (transitions to indeterminate style during "Stopping…" state)
- Repository count (completed / total)
- Current repository being analyzed
- Per-repo status chips (done = green, error = red, active = pulsing, stopping = skeleton)

### Config Drawer (Interactive Only)
Slide-out panel from the right with three tabs:

**Form tab** — structured controls for all config sections:
- Release: name, target month/year, branch pattern
- Branding: title, subtitle, company, accent color
- Settings: stale threshold, timeout, theme, max concurrent, output path
- Layers: dynamic list with add/remove (id, label, pattern, root URL, color, order)
- Repositories: grouped under their layer headers — each layer shows as a card with root URL, branch pattern, color, and order
- **Add Layer / Add Repository buttons** use orange accent (`#fb6400`) for better visibility

**JSON tab** — JSON editor with schema-aware features:
- **Editor**: raw JSON editor synced with the form, with a validation bar and error list below. Schema validation runs automatically as you type. Parse errors (invalid JSON syntax) are shown separately from schema errors (valid JSON that violates the config schema).
- **Field Reference**: located below the editor (not side-by-side) in a responsive 2-column CSS layout showing all config sections, field names, types, required markers, and descriptions.
- **Autocomplete**: schema-aware autocomplete suggests field names based on cursor context (root-level keys, release fields, layers fields, repository fields, branding, settings, layout). Navigate suggestions with arrow keys, accept with Tab or Enter, dismiss with Escape.

**Effective/Active tab** — read-only view showing resolved settings after inheritance and defaults are applied:
- **Global Settings**: effective release target, branch pattern, stale threshold, theme, and other settings as resolved from config and defaults
- **Layers**: each layer displays its effective branch pattern and root URL with **source badges** indicating where each value comes from (`global` or `layer` override)
- **Repositories**: each repository displays its effective URL, branch pattern, and default branch with **source badges** (`repo`, `layer`, `global`, `derived`, `config`, or `default`) showing the origin of each resolved value
- **Branding**: effective title, subtitle, company, and accent color

This tab helps users understand how three-tier inheritance, URL auto-derivation, and default values combine to produce the final effective configuration.

**Validation** — live schema-driven validation errors shown above the form. Switching tabs clears stale validation messages; each tab triggers its own validation on entry.

### Immediate Refresh
Add, edit, and delete actions on repositories trigger an immediate dashboard refresh. The UI updates in place without requiring a full page reload or manual re-analysis. This applies to all config mutations made through the config drawer or inline table actions.

### Readiness Ring
A large circular progress indicator showing the overall release readiness percentage. Color-coded:
- **Green** (≥80%) — on track
- **Yellow** (50–79%) — attention needed
- **Red** (<50%) — significant gaps

### Metric Cards
Quick-glance cards showing:
- **Total Repositories** — number of tracked repos
- **Ready** — repos with valid, fresh release branches
- **Missing Branch** — repos where the release branch doesn't exist. When the repo is reachable (e.g. a public GitHub repo), the system shows "Missing Branch" status with diagnostics rather than a vague error. The default-branch fallback provides intelligence (last activity date, visibility, default branch name) even when the release branch hasn't been created yet.
- **Invalid Naming** — repos where branch exists but doesn't match the expected pattern
- **Stale** — repos where the release branch has no recent activity
- **Errors** — repos that couldn't be accessed (shown only if > 0)
- **Warnings** — repos with non-critical issues (shown only if > 0)

### Charts
- **Status Distribution** — doughnut chart showing the breakdown of statuses
- **Readiness by Layer** — horizontal bar chart showing readiness percentage per layer

### Filters
Interactive filter bar:
- **Search** — text search by repository name
- **Layer** — dropdown to filter by layer
- **Status** — dropdown to filter by readiness status
- **Naming** — filter by naming validity
- **Reset** — clear all filters
- **Count** — shows number of visible repositories

### Attention Panel
Surfaces repositories that need immediate action, sorted by severity (errors first).

### Layer Sections
Each layer gets a dedicated section with:
- Layer header with color dot and stats
- Readiness progress bar
- Repository table (name, status, branch, naming, activity, freshness)
- **Drag handle** — grab the handle at the top-left of the section to drag it to a new position. In layout mode, handles show as distinct UI elements with a grip icon (`::before` pseudo-element), visible background, border, and box-shadow. Sections indent slightly to reveal the handles. A **layout-mode hint banner** appears at the top of the dashboard to guide users.
- **Drop placeholder** — during a drag, a drop placeholder appears where the section will land. Placeholders display "Drop here" text, use accent-colored borders and glow, and are indented to match section alignment.
- **Actions column (interactive only)** — Edit and Delete buttons appear on row hover:
  - **Edit** — opens the config drawer and scrolls to the matching repository accordion
  - **Delete** — opens a confirmation modal showing repository name, layer, and effective URL; requires explicit confirmation before removing from the draft config

All dashboard sections (including layer sections) have stable IDs (`score`, `metrics`, `charts`, `filters`, `attention`, `layer-{id}`, `summary`) used for layout persistence.

Click any row to open the detail modal.

### Detail Modal
Full drill-down for a single repository:
- Layer, status, URL
- Expected and actual branch names
- Naming validity
- Activity dates (last and first)
- Author, commit message, count
- Freshness and staleness
- Warnings and notes
- **Error details** — when a repository has errors, the error kind (e.g. `auth_required`, `timeout`, `rate_limited`, `placeholder_url`) is shown with a concise message; click to expand and see the full technical detail
- **Diagnostics section** — when a repository is reachable but its release branch is missing, a "Diagnostics" section appears showing:
  - Connectivity status (✓ Repository reachable)
  - Default branch detected (from the default-branch fallback)
  - Release branch not found
  - Expected branch pattern
  - Analysis conclusion with suggested next steps
- **Enriched GitHub fields** (when available): last commit SHA, repo description, default branch, visibility (public/private), owner, archived status, web URL, provider update timestamp. These fields are preserved even when the release branch doesn't exist — the default-branch fallback fetches metadata from the repo's default branch

### Summary Report
Management-ready section with:
- Overall status numbers
- Layer breakdown
- Suggested actions (create branches, fix naming, review stale)
- Report metadata (generation time, release name, tool version)

## Visual Design

The dashboard uses an enterprise visual design language:
- **Technical color palette** — muted, professional tones for status indicators and layer colors
- **Reduced border-radius** — sharper UI elements for a more technical feel
- **No emoji in controls** — toolbar buttons and actions use text labels only
- **Refined status colors** — carefully tuned for clarity and accessibility across light/dark themes
- **Version display** — `v{version}` shown in header and footer from package metadata

## Theme Support

Three modes available via the header switcher:
- **Light** — white background, dark text
- **System** — follows OS preference
- **Dark** — dark background, light text

Theme preference persists in localStorage.

## Layout Templates

The dashboard supports layout templates that control section order and visibility.

### Predefined Templates

| Template | Sections Shown | Description |
|----------|---------------|-------------|
| **Default** | All sections in standard order | Full dashboard with every section visible |
| **Executive** | Score, metrics, attention, summary | High-level overview for leadership |
| **Release Manager** | Score, metrics, filters, attention, layers, summary | Operational view focused on release status |
| **Engineering** | Metrics, charts, filters, layers | Technical view with charts and per-layer detail |
| **Compact** | Score, metrics, attention | Minimal view for quick status checks |

## Print Support

The dashboard is print-friendly. Toolbar, filters, theme switcher, config drawer, and modals are hidden in print. Use your browser's Print function or export to PDF.
