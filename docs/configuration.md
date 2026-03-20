# Configuration Reference

## Table of Contents

- [File Format](#file-format)
- [Sections](#sections)
  - [`release` (required)](#release-required)
  - [`layers` (optional)](#layers-optional)
  - [`repositories` (required)](#repositories-required)
  - [`branding` (optional)](#branding-optional)
  - [`settings` (optional)](#settings-optional)
  - [`layout` (optional)](#layout-optional)
- [Branch Pattern Variables](#branch-pattern-variables)
- [Three-Tier Override](#three-tier-override)
  - [Branch Pattern Inheritance Indicators](#branch-pattern-inheritance-indicators)
- [Repository Root URL Resolution](#repository-root-url-resolution)
- [Analysis State Model](#analysis-state-model)
- [URL → Name Auto-Derivation](#url-name-auto-derivation)
- [GitHub API Provider](#github-api-provider)
  - [`GITHUB_TOKEN`](#github_token)
- [Environment Variables](#environment-variables)
- [Placeholder URL Detection](#placeholder-url-detection)
- [Deferred Analysis Model](#deferred-analysis-model)
- [Effective Value Validation](#effective-value-validation)
- [JSON Editor](#json-editor)
  - [Schema-Aware Autocomplete](#schema-aware-autocomplete)
  - [Field Reference](#field-reference)
- [Effective/Active Tab](#effectiveactive-tab)
  - [Global Settings](#global-settings)
  - [Layers](#layers)
  - [Repositories](#repositories)
  - [Branding](#branding)
  - [Inherited Value Display](#inherited-value-display)
- [Validation Scoping](#validation-scoping)

## File Format

ReleaseBoard configuration is a JSON file validated against a strict JSON Schema.

Default location: `releaseboard.json` (override with `--config`)

## Sections

### `release` (required)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | ✅ | — | Human-readable release name |
| `target_month` | integer | ✅ | — | Target month (1–12) |
| `target_year` | integer | ✅ | — | Target year (2000–2100) |
| `branch_pattern` | string | — | `release/{MM}.{YYYY}` | Global branch naming pattern |

### `layers` (optional)

Array of layer definitions.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `id` | string | ✅ | — | Unique ID (lowercase, alphanumeric, hyphens) |
| `label` | string | ✅ | — | Display label |
| `branch_pattern` | string | — | — | Layer-level branch pattern override |
| `repository_root_url` | string | — | — | Root URL prefix for all repositories in this layer |
| `color` | string | — | — | Hex color for badges/charts (e.g. `#3B82F6`) |
| `order` | integer | — | `0` | Display order (lower = first) |

### `repositories` (required)

Array of repository definitions. At least one is required.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | ✅ | — | Short repository name |
| `url` | string | ✅ | — | Repository URL (HTTPS, SSH, or local path) |
| `layer` | string | ✅ | — | Layer ID this repo belongs to |
| `branch_pattern` | string | — | — | Repo-level branch pattern override |
| `default_branch` | string | — | `main` | Default/base branch name |
| `notes` | string | — | — | Optional notes |

### `branding` (optional)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `title` | string | `ReleaseBoard` | Dashboard title |
| `subtitle` | string | `Release Readiness Dashboard` | Dashboard subtitle |
| `company` | string | `""` | Company name |
| `accent_color` | string | `#4F46E5` | Primary accent color (hex) |
| `logo_path` | string | `null` | Path to logo image |

### `settings` (optional)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `stale_threshold_days` | integer | `14` | Days before branch is considered stale |
| `output_path` | string | `output/dashboard.html` | Output file path |
| `theme` | string | `system` | Default theme: `light`, `dark`, `system` |
| `verbose` | boolean | `false` | Enable verbose logging |
| `timeout_seconds` | integer | `30` | Timeout for git operations |
| `max_concurrent` | integer | `5` | Max concurrent git operations |

### `layout` (optional)

Controls dashboard section ordering and layout templates.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `default_template` | string | `default` | Active layout template: `default`, `executive`, `release-manager`, `engineering`, `compact`, or a user-created template name |
| `section_order` | array | (template default) | Ordered list of section IDs to display. Valid IDs: `score`, `metrics`, `charts`, `filters`, `attention`, `layer-{id}`, `summary` |
| `enable_drag_drop` | boolean | `true` | Enable drag-and-drop section reordering in the interactive dashboard |

**Example:**

```json
{
  "layout": {
    "default_template": "executive",
    "section_order": ["score", "metrics", "attention", "summary"],
    "enable_drag_drop": true
  }
}
```

When `section_order` is provided it controls both the order and visibility of sections — sections not listed are hidden. If omitted, the selected template's default order is used.

## Branch Pattern Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{YYYY}` | 4-digit year | `2025` |
| `{YY}` | 2-digit year | `25` |
| `{MM}` | Zero-padded month | `03` |
| `{M}` | Month without padding | `3` |

## Three-Tier Override

Pattern resolution priority: **repository → layer → global**

1. If the repository has `branch_pattern`, use it
2. Else if the repository's layer has `branch_pattern`, use it
3. Else use `release.branch_pattern`

### Branch Pattern Inheritance Indicators

In the interactive config drawer, branch patterns show their inheritance source:

- **Layer branch pattern** — displays "inherited from global" when no layer-level override is set, or "layer override" when a custom pattern is defined
- **Repo branch pattern** — displays the effective source: "inherited from global", "inherited from layer", or "repo override"
- **Changing a layer pattern** re-renders all repositories in that layer to reflect the updated effective value
- **Reset to inherited** — repo-level branch pattern fields include a "Reset to inherited" button that clears the repo override and reverts to the layer or global pattern

## Repository Root URL Resolution

Repository URLs can be constructed from a root URL plus the repository name. The root URL resolves with this priority: **repository explicit URL → layer `repository_root_url` → global `repository_root_url`**

If a repository has an explicit `url`, it is always used as-is. Otherwise, the URL is constructed by appending the repository name to the layer's `repository_root_url` (or the global one if the layer doesn't define its own).

```json
{
  "layers": [
    {
      "id": "ui",
      "label": "Frontend",
      "repository_root_url": "https://github.com/acme-frontend",
      "color": "#3B82F6"
    },
    {
      "id": "api",
      "label": "Backend",
      "repository_root_url": "https://github.com/acme-backend",
      "color": "#10B981"
    }
  ],
  "repositories": [
    { "name": "web-app", "layer": "ui" },
    { "name": "core-api", "layer": "api" },
    { "name": "special-svc", "url": "https://github.com/acme-special/svc.git", "layer": "api" }
  ]
}
```

In this example:
- `web-app` resolves to `https://github.com/acme-frontend/web-app`
- `core-api` resolves to `https://github.com/acme-backend/core-api`
- `special-svc` uses its explicit URL `https://github.com/acme-special/svc.git`

## Analysis State Model

When running in interactive mode, the analysis lifecycle follows this state model:

```text
idle → queued → analyzing → stopping → cancelled / partially_completed
                    └──────────────────→ completed / failed
```

- **idle** — no analysis running
- **queued** — analysis requested, waiting to start
- **analyzing** — actively checking repositories
- **stopping** — stop requested; UI shows "Stopping…" and the analysis winds down gracefully
- **cancelled** — analysis was stopped before any results
- **partially_completed** — analysis was stopped after some results were collected
- **completed** — all repositories analyzed successfully
- **failed** — analysis encountered a fatal error

## URL → Name Auto-Derivation

When adding a repository, ReleaseBoard can automatically derive the `name` from the `url`. The `derive_name_from_url()` utility handles HTTPS, SSH (`git@…`), `ssh://`, local paths, and bare slugs, stripping `.git` suffixes and trailing slashes.

In the interactive UI, new repositories start with an empty name field. When a URL is pasted, the name is auto-derived in real time via `oninput` (not just `onchange`) and an "auto-filled from URL" indicator appears. If the user manually edits the name, it is marked as overridden — subsequent URL changes will not replace a manually-set name.

## GitHub API Provider

ReleaseBoard includes a `GitHubProvider` that uses the GitHub REST API to fetch enriched repository metadata (description, visibility, archived status, default branch, owner, web URL, last commit SHA).

Public GitHub repositories work without any token — the provider uses unauthenticated API access, though this is subject to GitHub's rate limits (60 requests/hour). For higher rate limits and access to private repositories, configure a `GITHUB_TOKEN`.

When the expected release branch is missing but the repository is reachable, the provider falls back to fetching metadata from the repository's default branch. This provides useful intelligence (last activity, visibility, default branch name) even before the release branch is created.

`SmartGitProvider` automatically selects the provider:
- **`github.com` URLs** → `GitHubProvider` (REST API)
- **Everything else** → `LocalGitProvider` (git CLI)

The web server uses `SmartGitProvider` by default. If the GitHub API call fails, analysis continues gracefully with limited metadata.

### `GITHUB_TOKEN`

Set the `GITHUB_TOKEN` environment variable for authenticated GitHub API access:

```bash
export GITHUB_TOKEN=ghp_xxxxxxxxxxxx
```

- **Authenticated**: higher rate limits (5,000 requests/hour), access to private repos
- **Unauthenticated**: works for public repos but is rate-limited (60 requests/hour); 403 errors are classified as `rate_limited` with a clear message

## Environment Variables

Repository URLs can contain `${ENV_VAR}` placeholders:

```json
{
  "url": "https://${GITHUB_TOKEN}@github.com/acme/repo.git"
}
```

Set `GITHUB_TOKEN` in your environment before running. It is also used by `SmartGitProvider` for GitHub REST API access (see above).

## Placeholder URL Detection

ReleaseBoard automatically detects placeholder and example URLs (e.g. `https://github.com/your-org/your-repo`, `https://example.com/repo.git`). These URLs are skipped during analysis — no network call is attempted — and reported with the `placeholder_url` error kind in the dashboard.

This makes it safe to keep template entries in your config while setting up new repositories.

## Deferred Analysis Model

Config editing is decoupled from git network access. Three independent validity concerns exist:

1. **Config validity** — JSON schema conformance and semantic checks (layer references, field types)
2. **Connectivity validity** — can the configured URLs be reached? Check on demand via `/api/config/check-urls`
3. **Analysis validity** — does the latest analysis reflect the current config?

Editing config (in the drawer or via API) never triggers network calls. You explicitly request connectivity checks or a full analysis when ready. This keeps config editing fast and safe even with many repositories or unreliable networks.

## Effective Value Validation

`validateDraft` now checks not only explicitly-set fields but also auto-derived and inherited values. This means:

- **Empty names** — if a repo's name is empty and cannot be auto-derived (e.g. no URL provided), a validation error is raised
- **Bare slugs without root URL** — if a repo has no explicit URL and its layer has no `repository_root_url`, validation catches the missing effective URL
- **Inherited branch patterns** — the effective branch pattern (after inheritance resolution) is validated, not just the explicitly-set value

This ensures that the config is valid as a whole, even when individual fields rely on auto-derivation or inheritance from parent layers.

## JSON Editor

The interactive config drawer includes a JSON tab with a raw JSON editor and supporting tools:

### Schema-Aware Autocomplete

The JSON editor provides context-aware autocomplete suggestions based on the ReleaseBoard JSON Schema. As you type, the editor detects the cursor context (root level, inside `release`, `layers`, `repositories`, `branding`, `settings`, or `layout`) and suggests valid field names for that section.

- **Trigger**: autocomplete activates when typing inside a JSON object
- **Navigation**: use **↑ / ↓** arrow keys to move through suggestions
- **Accept**: press **Tab** or **Enter** to insert the selected field
- **Dismiss**: press **Escape** to close the suggestion list
- Suggestions are filtered to exclude fields that already exist in the current object

### Field Reference

The field reference panel is positioned **below the editor** (not side-by-side) and uses a responsive **2-column CSS grid layout** listing all config sections, field names, types, required markers, and descriptions. This layout provides more vertical space for the editor while keeping the reference accessible by scrolling down.

## Effective/Active Tab

The Configuration drawer includes a third tab — **Effective/Active** — that shows the fully resolved configuration after inheritance, auto-derivation, and defaults are applied. This is a read-only view designed to help users understand what values are actually in effect.

### Global Settings
Displays the resolved release target, branch pattern, stale threshold, theme, and other top-level settings as they will be used during analysis.

### Layers
Each layer shows its effective branch pattern and repository root URL. **Source badges** indicate where each value originates:
- `global` — inherited from the global `release.branch_pattern`
- `layer` — explicitly set on the layer

### Repositories
Each repository shows its effective URL, branch pattern, and default branch. **Source badges** indicate the origin of each resolved value:
- `repo` — explicitly set on the repository
- `layer` — inherited from the parent layer
- `global` — inherited from the global config
- `derived` — auto-derived (e.g. name from URL, or URL from layer root + name)
- `config` — set in the config file (not overridden)
- `default` — using the built-in default value

### Branding
Shows the effective title, subtitle, company, and accent color after defaults are applied.

### Inherited Value Display

In the Form tab, branch pattern inputs show the effective inherited value as a **placeholder** when the repository does not have an explicit override. This eliminates empty-appearing inputs for inherited values — users always see what value is in effect, even when the field itself is blank.

## Validation Scoping

Switching between tabs (Form, JSON, Effective/Active) in the config drawer **clears stale validation messages** from the previous tab. Each tab triggers its own validation on entry, ensuring that displayed errors always correspond to the currently visible content.
