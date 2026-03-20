# Usage Guide

## Table of Contents

- [First Run](#first-run)
- [Commands](#commands)
  - [`releaseboard generate`](#releaseboard-generate)
  - [`releaseboard serve`](#releaseboard-serve)
  - [`releaseboard validate`](#releaseboard-validate)
  - [`releaseboard version`](#releaseboard-version)
- [Workflow](#workflow)
  - [Static Dashboard (CLI)](#static-dashboard-cli)
  - [Interactive Dashboard (Web)](#interactive-dashboard-web)
  - [CI/CD Integration](#cicd-integration)
- [Authentication & GitHub Token](#authentication-github-token)
- [API Endpoints (Interactive Mode)](#api-endpoints-interactive-mode)

## First Run

When you run `releaseboard serve` without a configuration file, the dashboard starts in **setup wizard mode** instead of crashing. This makes it easy to get started without manually creating a config file.

### How it works

1. Run `releaseboard serve` — if `releaseboard.json` doesn't exist, the setup wizard opens automatically
2. The wizard creates `releaseboard.json` in the current directory (or the path specified with `--config`)
3. Choose one of three options:
   - **Start Fresh** — create a minimal empty configuration with release name, target month/year, and branch pattern
   - **Import from Example** — pick from pre-built example configurations in the `examples/` directory
   - **Import JSON** — paste your own configuration JSON directly
4. After creation, the dashboard loads normally with your new configuration
5. You can then add repositories and customize settings through the interactive dashboard

### Notes

- The `generate` and `validate` commands still require an existing config file
- Example configurations are available in the `examples/` directory for reference
- The setup wizard validates your configuration against the JSON schema before saving

## Commands

### `releaseboard generate`

Generate a static HTML dashboard.

```bash
releaseboard generate [OPTIONS]
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--config` | `-c` | `releaseboard.json` | Config file path |
| `--output` | `-o` | (from config) | Override output path |
| `--theme` | `-t` | (from config) | Override theme |
| `--verbose` | `-v` | `false` | Verbose logging |

**Example:**

```bash
releaseboard generate --config my-release.json --output report.html --theme dark -v
```

### `releaseboard serve`

Start the interactive web dashboard with live config editing and real-time analysis.

```bash
releaseboard serve [OPTIONS]
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--config` | `-c` | `releaseboard.json` | Config file path |
| `--host` | | `127.0.0.1` | Host to bind to |
| `--port` | `-p` | `8080` | Port to listen on |
| `--verbose` | `-v` | `false` | Verbose logging |

**Example:**

```bash
releaseboard serve --config my-release.json --port 9000
```

Then open `http://127.0.0.1:9000` in your browser.

### `releaseboard validate`

Validate a configuration file without generating.

```bash
releaseboard validate --config releaseboard.json
```

### `releaseboard version`

Show version number.

## Workflow

### Static Dashboard (CLI)

#### 1. Create Configuration

Start with `examples/config.json` and adapt:
- Set your `release` target month/year
- Define your `layers`
- List your `repositories` with URLs and layer assignments
- Customize `branding` and `settings`

#### 2. Validate

```bash
releaseboard validate
```

#### 3. Generate

```bash
releaseboard generate
```

The CLI will:
1. Load and validate config
2. Query each repository for branch information
3. Evaluate release readiness
4. Print a CLI summary table
5. Generate the HTML dashboard

#### 4. View

```bash
open output/dashboard.html    # macOS
xdg-open output/dashboard.html  # Linux
```

### Interactive Dashboard (Web)

#### 1. Start the server

```bash
releaseboard serve --config my-release.json
```

#### 2. Use the dashboard

The interactive dashboard provides:

- **Toolbar** — Analyze, Stop, Config, Export HTML, Export Config buttons; uses **sticky positioning** so primary actions remain accessible while scrolling
- **Analysis status bar** — real-time progress with per-repo chips, progress bar, elapsed time; shows "Stopping…" state when stop is requested
- **Config drawer** — slide-out panel with:
  - **Form tab** — structured controls for all config sections (Release, Branding, Settings, Layers, Repositories), with repositories grouped under their layer headers
  - **JSON tab** — JSON editor on top with a validation bar and error list; field reference panel below the editor in a 2-column CSS layout. Schema-aware **autocomplete** suggests field names based on cursor context (root, release, layers, repositories, branding, settings, author, layout) with keyboard navigation (arrows, Tab, Enter, Escape). Parse errors are shown separately from schema errors.
  - **Effective/Active tab** — read-only view showing resolved settings after inheritance and defaults, with source badges (`global`, `layer`, `repo`, `derived`, `config`, `default`) on each value. Displays Global Settings, Layers, Repositories, and Branding as they will be used during analysis. Helps understand three-tier inheritance.
  - **Validation** — live schema-driven validation errors; switching tabs clears stale messages and triggers fresh validation
  - **Actions** — Apply & Analyze, Save, Reset, Import
- **Inline table actions** — Edit and Delete buttons on each repository row (appear on hover); Edit opens the config drawer scrolled to the repo; Delete shows a confirmation modal
- **URL auto-derivation** — when adding a repo, new repos start with an empty name field. Pasting a URL auto-derives the name in real time (via `oninput`) and shows an "auto-filled from URL" indicator. Manually editing the name marks it as overridden so subsequent URL changes respect the custom name. Supports HTTPS, SSH, and local paths.
- **Inherited value placeholders** — branch pattern inputs show the effective inherited value as a placeholder when no explicit override is set, so inputs never appear misleadingly empty
- **Enriched GitHub metadata** — repos hosted on `github.com` show additional details (description, visibility, archived status, web URL, owner) via the GitHub REST API; public repos work without a token
- **Missing branch diagnostics** — when a release branch is missing but the repo is reachable, the detail modal shows a "Diagnostics" section with connectivity status (✓ Repository reachable), detected default branch, missing release branch, expected pattern, and analysis conclusion
- **Default-branch fallback** — when the release branch doesn't exist, metadata is fetched from the repo's default branch, providing last activity date, visibility, and default branch name
- **Version display** — `v{version}` shown from package metadata
- **Drag-and-drop layout** — reorder dashboard sections by dragging their visible grip-icon handles; sections indent to reveal handles and a hint banner appears at the top. Drop placeholders show "Drop here" text with accent-colored borders and glow
- **Layout template bar** — select from 5 predefined templates (Default, Executive, Release Manager, Engineering, Compact) or create your own
- **Immediate refresh** — adding, editing, or deleting a repository instantly refreshes the dashboard
- **Placeholder URL detection** — placeholder/example URLs (e.g. `https://github.com/your-org/your-repo`) are detected and skipped during analysis; no network call is made

#### 3. Stop/Cancel analysis

While an analysis is running, click the **Stop** button to cancel it:
1. The UI immediately transitions to "Stopping…" state
2. The analysis winds down gracefully, finishing the current repository
3. Final state is `cancelled` (no results) or `partially_completed` (some results available)

#### 4. Config workflow

1. Click **Configuration** in the toolbar
2. Edit settings in the form or JSON tab (repositories are grouped under their layer headers)
3. Each layer card shows its root URL, branch pattern, color, and order
4. **Branch pattern inheritance** — layer branch patterns display "inherited from global" or "layer override" tags; repo branch patterns show the effective source ("inherited from global", "inherited from layer", or "repo override"); use the "Reset to inherited" button to clear a repo-level override
5. Click **Apply & Analyze** to run analysis with the new settings
6. Click **Save** to persist changes to disk
7. Click **Reset** to discard unsaved changes
8. Use **Import** to load a JSON config file
9. Use **Export Config** in the toolbar to download current config

#### 5. JSON editor

1. Open the config drawer and switch to the **JSON tab**
2. The editor area shows the raw JSON with a **validation bar** below it
3. **Autocomplete**: as you type inside a JSON object, schema-aware suggestions appear based on cursor context (root, release, layers, repositories, branding, settings, author, layout). Use **↑ / ↓** to navigate, **Tab** or **Enter** to accept, **Escape** to dismiss.
4. Schema validation runs automatically as you type — parse errors (invalid JSON syntax) and schema errors (valid JSON that violates the config schema) are listed separately
5. The **field reference** panel is below the editor in a 2-column CSS layout with all config sections, field names, types, required markers, and descriptions
6. Edits in the JSON tab stay synced with the Form tab

#### 6. Effective/Active tab

1. Open the config drawer and switch to the **Effective/Active** tab
2. This read-only tab shows the fully resolved configuration after inheritance, auto-derivation, and defaults
3. **Global Settings** — effective release target, branch pattern, stale threshold, theme
4. **Layers** — each layer with its effective branch pattern and root URL; source badges show `global` or `layer` origin
5. **Repositories** — each repo with its effective URL, branch pattern, and default branch; source badges show `repo`, `layer`, `global`, `derived`, `config`, or `default` origin
6. **Branding** — effective title, subtitle, company, and accent color
7. Use this tab to verify that three-tier inheritance and auto-derivation produce the expected results before running analysis

#### 7. Layout customization

1. Use the **layout template bar** below the toolbar to switch between predefined templates (Default, Executive, Release Manager, Engineering, Compact)
2. **Drag sections** by their visible grip-icon handle to reorder the dashboard layout
3. Sections indent to reveal drag handles, and a layout-mode hint banner appears at the top
4. Drop placeholders with "Drop here" text and accent-colored glow indicate where the section will land
4. To create a custom template, arrange sections as desired and click **Save Template**
5. Custom templates are stored in localStorage and available across sessions
6. Templates control both section order and visibility — hidden sections are omitted from the view

#### 8. Placeholder URL handling

Placeholder or example URLs (`https://github.com/your-org/your-repo`, `https://example.com/repo.git`, etc.) are automatically detected and skipped during analysis. No network calls are made for these URLs. They appear in the dashboard with a `placeholder_url` status so you can identify repos that still need real URLs.

Use the **Check URLs** action (or `POST /api/config/check-urls`) to validate all repository URLs without running a full analysis.

### CI/CD Integration

Generate the dashboard in CI and upload as an artifact:

```yaml
- name: Generate release dashboard
  run: releaseboard generate --config release-config.json --output dashboard.html

- name: Upload dashboard
  uses: actions/upload-artifact@v4
  with:
    name: release-dashboard
    path: dashboard.html
```

## Authentication & GitHub Token

For private repositories and enriched GitHub metadata, set the `GITHUB_TOKEN` environment variable:

```bash
export GITHUB_TOKEN=ghp_xxxxxxxxxxxx
```

The token serves two purposes:

1. **Git credential** — use `${GITHUB_TOKEN}` in config URLs for private repo access:
   ```json
   { "url": "https://${GITHUB_TOKEN}@github.com/acme/private-repo.git" }
   ```
2. **GitHub REST API** — `SmartGitProvider` uses the token for authenticated API calls, yielding higher rate limits and access to private repos. For public repos, unauthenticated access works but is rate-limited.

## API Endpoints (Interactive Mode)

When running `releaseboard serve`, the following API endpoints are available:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Interactive dashboard HTML |
| `/api/config` | GET | Get config state (draft + persisted) |
| `/api/config` | PUT | Update draft config |
| `/api/config/save` | POST | Persist draft to disk |
| `/api/config/reset` | POST | Reset draft to persisted |
| `/api/config/validate` | POST | Validate config against schema |
| `/api/config/schema` | GET | Get JSON Schema |
| `/api/config/export` | GET | Export current config as JSON |
| `/api/config/import` | POST | Import config from JSON |
| `/api/analyze` | POST | Trigger analysis |
| `/api/analyze/stream` | GET | SSE stream for analysis progress |
| `/api/analyze/results` | GET | Get latest analysis results |
| `/api/export/html` | GET | Export static HTML dashboard |
| `/api/config/check-urls` | POST | Validate repository URLs without running analysis (detects placeholder, empty, relative, and valid URLs) |
| `/api/config/create` | POST | Create initial configuration from first-run wizard (modes: empty, example, import) |
| `/api/examples` | GET | List available example configurations |
| `/api/status` | GET | Application health check |
