# Architecture

## Table of Contents

- [Overview](#overview)
- [Layers](#layers)
  - [Domain (`domain/`)](#domain-domain)
  - [Config (`config/`)](#config-config)
  - [Git (`git/`)](#git-git)
  - [Analysis (`analysis/`)](#analysis-analysis)
  - [Application (`application/`)](#application-application)
  - [Web (`web/`)](#web-web)
  - [Presentation (`presentation/`)](#presentation-presentation)
  - [CLI (`cli/`)](#cli-cli)
- [Key Design Decisions](#key-design-decisions)
  - [Dual Runtime Model (Static + Web)](#dual-runtime-model-static-web)
  - [Server-Sent Events (SSE) over WebSocket](#server-sent-events-sse-over-websocket)
  - [Three-Tier Config State](#three-tier-config-state)
  - [Three-Tier Branch Pattern Override](#three-tier-branch-pattern-override)
  - [Git Provider Abstraction & Smart Selection](#git-provider-abstraction-smart-selection)
  - [Default-Branch Fallback](#default-branch-fallback)
  - [Provider Metadata on Missing Branch](#provider-metadata-on-missing-branch)
  - [URL → Name Auto-Derivation](#url-name-auto-derivation)
  - [Branch-Exists Status Model](#branch-exists-status-model)
  - [Shared Analysis Service](#shared-analysis-service)
  - [View Models](#view-models)
  - [Error Classification](#error-classification)
  - [Deferred Analysis Model](#deferred-analysis-model)
  - [Layout System](#layout-system)
  - [URL Health-Check Endpoint](#url-health-check-endpoint)
- [Extensibility Points](#extensibility-points)

## Overview

ReleaseBoard uses a clean layered architecture with two runtime modes:
1. **CLI mode** — `releaseboard generate` produces a self-contained static HTML dashboard
2. **Interactive mode** — `releaseboard serve` starts a FastAPI web application with live config editing, real-time analysis via SSE, and an interactive dashboard

Both modes share the same `AnalysisService`, config, and domain logic.

```text
┌─────────────────────────────────────────────────────────┐
│                   Entry Points                           │
│          CLI (Typer)  ·  Web (FastAPI)                   │
├────────────────────┬────────────────────────────────────┤
│   Application      │         Web Layer                   │
│   AnalysisService  │  server.py (14 API routes)          │
│   (shared pipeline)│  state.py (config tiers, SSE)       │
├────────────────────┴────────────────────────────────────┤
│               Application Flow                           │
│   Config → SmartGitProvider → Analysis → Presentation     │
├──────────┬───────────┬───────────┬──────────────────────┤
│  Config  │    Git    │ Analysis  │   Presentation        │
│  loader  │ providers │ readiness │   view models         │
│  schema  │  smart    │ patterns  │   renderer            │
│  models  │  github   │ staleness │   templates           │
│  author  │  local    │ metrics   │   theme               │
├──────────┴───────────┴───────────┴──────────────────────┤
│                   Domain Layer                           │
│         Models, Enums (zero dependencies)                │
├─────────────────────────────────────────────────────────┤
│                   Shared Layer                           │
│             Logging, Type Aliases                         │
└─────────────────────────────────────────────────────────┘
```

## Layers

### Domain (`domain/`)
Pure data models and enumerations. No external dependencies.
- `ReadinessStatus` — enum of all possible repository states
- `BranchInfo` — metadata about a branch; enriched fields include `last_commit_sha`, `repo_description`, `repo_default_branch`, `repo_visibility`, `repo_owner`, `repo_archived`, `repo_web_url`, `provider_updated_at`
- `RepositoryAnalysis` — complete analysis result for one repo
- `LayerDefinition` — layer configuration data

### Config (`config/`)
Configuration loading and validation.
- `schema.json` — JSON Schema (Draft 7) for config validation
- `schema.py` — schema validation using `jsonschema`
- `loader.py` — reads JSON, resolves `${ENV}` placeholders, builds typed `AppConfig`
- `models.py` — typed dataclass config models (includes per-layer `repository_root_url` and `AuthorConfig` for author metadata)

### Git (`git/`)
Abstracted repository access with smart provider selection.
- `GitProvider` — abstract base class defining the interface
- `LocalGitProvider` — uses `git` CLI via subprocess
- `GitHubProvider` — uses GitHub REST API for richer metadata (commit SHAs, repo description, visibility, archived status, web URL, default branch, owner)
- `SmartGitProvider` — auto-selects between `GitHubProvider` (for `github.com` URLs) and `LocalGitProvider` (everything else); used by the web server by default
- `derive_name_from_url()` — utility that extracts a repository name from HTTPS, SSH (`git@…`), `ssh://`, local paths, or bare slugs; strips `.git` suffixes and trailing slashes

### Analysis (`analysis/`)
Business logic for release readiness evaluation.
- `BranchPatternMatcher` — resolves templates to concrete names, validates with regex
- `ReadinessAnalyzer` — evaluates each repository's readiness status
- `staleness.py` — determines if branches are stale
- `metrics.py` — aggregates per-layer and global metrics

### Application (`application/`)
Shared orchestration used by both CLI and web.
- `AnalysisService` — runs the full analysis pipeline with async progress callbacks and cancellation support
- `AnalysisProgress` — real-time progress state model with `to_dict()` for SSE serialization
- `AnalysisResult` — complete result of an analysis run

#### Analysis State Model

```text
idle → queued → analyzing → stopping → cancelled
                    │                    completed
                    │                    failed
                    │                    partially_completed
                    └──────────────────→ completed / failed
```

When a stop is requested during `analyzing`, the state immediately transitions to `stopping` (reflected in the UI as "Stopping…"). The final state is one of `cancelled`, `partially_completed`, `completed`, or `failed` depending on how far the analysis progressed.

### Web (`web/`)
FastAPI-based interactive web layer.
- `server.py` — FastAPI application factory with 14 endpoints (dashboard, config CRUD, analysis trigger/stream, export, status)
- `state.py` — `AppState` managing three-tier config (persisted/active/draft), SSE subscriber queues, analysis locking

### Presentation (`presentation/`)
View model construction and HTML rendering.
- `view_models.py` — converts domain objects to presentation models (supports `interactive` flag)
- `theme.py` — enterprise visual design with technical color palette, reduced border-radius, refined status colors
- `renderer.py` — Jinja2-based HTML generation
- `templates/dashboard.html.j2` — self-contained HTML template with conditional interactive features, layer-grouped config drawer and version display

### CLI (`cli/`)
User-facing entry point.
- `app.py` — Typer commands: `generate`, `serve`, `validate`, `version`

## Key Design Decisions

### Dual Runtime Model (Static + Web)
The system supports **both** a generated static HTML file and an interactive web application:
- **Static mode**: Zero deployment, CI/CD artifact, shareable offline
- **Interactive mode**: Live config editing, real-time analysis, SSE progress updates

### Server-Sent Events (SSE) over WebSocket
Analysis progress flows one direction (server → client), so SSE is simpler and sufficient. Implemented via FastAPI `StreamingResponse` with `asyncio.Queue` per subscriber.

### Three-Tier Config State
The web layer manages three config tiers:
- **Persisted**: saved on disk (source of truth)
- **Active**: used for the last analysis run
- **Draft**: current unsaved UI edits

This prevents accidental data loss and supports safe rapid iteration.

### Three-Tier Branch Pattern Override
Branch patterns resolve: repo → layer → global. This supports teams where different layers use different branch conventions.

### Git Provider Abstraction & Smart Selection
Git access goes through an abstract `GitProvider` interface. `SmartGitProvider` automatically selects the best concrete provider: `GitHubProvider` for `github.com` URLs (returning enriched metadata via the REST API) and `LocalGitProvider` for everything else. A `GitLabProvider` implementation also exists for GitLab-hosted repositories. If the GitHub API call fails, analysis continues gracefully with limited metadata. Adding Bitbucket or other providers requires only a new provider implementation — no changes to analysis logic.

### Default-Branch Fallback
When the expected release branch is missing but the repository is reachable, the `GitHubProvider` attempts to fetch metadata from the repository's default branch. This provides intelligence even when the release branch hasn't been created yet:
- **Last activity date** from the default branch
- **Visibility status** (public/private)
- **Default branch name** (e.g. `main`, `master`)
- **Repository description, owner, and web URL**

The metadata flows through the system as: `GitHubProvider` → `BranchInfo` (enriched fields) → `RepositoryAnalysis` → `RepoViewModel` (presentation) → dashboard template (Diagnostics section). This ensures the detail modal can show useful repository information and diagnostics even for repos where the release branch doesn't exist.

### Provider Metadata on Missing Branch
Repository metadata (default branch, visibility, description, web URL, owner) is preserved in `BranchInfo` even when the release branch is absent. The `RepositoryAnalysis` carries this metadata forward, and the `RepoViewModel` makes it available to the template. The detail modal renders a "Diagnostics" section showing connectivity status, detected default branch, missing release branch, expected pattern, and an analysis conclusion.

### URL → Name Auto-Derivation
The `derive_name_from_url()` utility extracts a human-readable repository name from any URL format (HTTPS, SSH, `ssh://`, local path, bare slug). It strips `.git` suffixes and trailing slashes. In the UI, when a user adds a repository by URL, the name field auto-fills with the derived name (editable).

### Branch-Exists Status Model
Status determination clearly separates four concerns: **existence** (does the branch exist?), **validity** (does it match the naming pattern?), **freshness** (how recent is the last commit?), and **readiness** (is everything in order?). A branch that exists with valid naming but has no commit metadata returns `READY` — `STALE` only applies when commit age exceeds the threshold, and `INACTIVE` is reserved for cases with explicit inactivity evidence.

### Shared Analysis Service
Both CLI and web call the same `AnalysisService`. No business logic duplication. The service accepts an optional `on_progress` callback for SSE integration.

### View Models
The presentation layer never receives domain objects directly. View models pre-compute all display values (colors, labels, formatted dates) so the Jinja2 template is pure rendering.

### Error Classification
Git errors are classified into structured kinds via the `GitErrorKind` enum:

| Kind | Description |
|------|-------------|
| `dns_resolution` | DNS lookup failed |
| `auth_required` | Authentication needed |
| `rate_limited` | API rate limit exceeded (e.g. GitHub 403) |
| `repo_not_found` | Repository does not exist |
| `access_denied` | Permissions insufficient |
| `timeout` | Operation timed out |
| `network_error` | General network failure |
| `invalid_url` | Malformed URL |
| `local_path_missing` | Local path does not exist |
| `git_cli_missing` | `git` binary not found |
| `provider_unavailable` | Provider (e.g. GitHub API) is down |
| `placeholder_url` | URL is a placeholder or example |
| `unknown` | Unclassifiable error |

The `classify_git_error()` function maps raw error output to the appropriate kind. GitHub-specific HTTP status codes are mapped precisely: 404 → `repo_not_found`, 403 → `rate_limited`, 401 → `auth_required`, and connection failures → `network_error`. GitHub-specific messages like "Cannot access GitHub repo" and "API rate limit exceeded" are also recognized. User-facing messages are kept concise; the full technical detail is available in an expandable section (detail modal). The `is_placeholder_url()` utility detects common placeholder and example URLs (e.g. `https://github.com/your-org/your-repo`) and returns `placeholder_url` immediately — no network call is attempted.

### Deferred Analysis Model
Config editing is fully decoupled from git network access. Three independent validity concerns are tracked:

1. **Config validity** — does the JSON conform to the schema and pass semantic checks?
2. **Connectivity validity** — can the configured URLs be reached? (checked on-demand via `/api/config/check-urls`)
3. **Analysis validity** — does the latest analysis reflect the current config?

Editing config never triggers network calls. Users explicitly request connectivity checks or full analysis when ready. This makes config editing fast and safe even with many repositories or unreliable networks.

### Layout System
Dashboard sections have stable IDs: `score`, `metrics`, `charts`, `filters`, `attention`, `layer-{id}`, `summary`. Users can reorder sections via drag handles; drop placeholders are shown during drag. The layout is responsive-safe and persists in localStorage.

Five predefined layout templates are available: **Default**, **Executive**, **Release Manager**, **Engineering**, and **Compact**. Users can also create custom templates. Templates control section order and visibility. The active template is stored in localStorage alongside the section order.

### URL Health-Check Endpoint
The `/api/config/check-urls` endpoint validates repository URLs without running a full analysis. It detects:
- Placeholder/example URLs
- Empty or blank URLs
- Relative URLs (not supported)
- Valid, reachable URLs

This enables quick feedback in the config drawer before committing to a full analysis run.

## ReleasePilot Integration

ReleaseBoard integrates with [ReleasePilot](https://github.com/polprog-tech/ReleasePilot/blob/main/README.md) — release note generation library. The integration lives in `src/releaseboard/integrations/releasepilot/` and follows a clean adapter pattern:

```
integrations/releasepilot/
├── __init__.py          # Public exports
├── models.py            # AudienceMode, OutputFormat, ReleasePrepRequest/Result, RepoContext
├── adapter.py           # ReleasePilotAdapter — capability detection + request forwarding
└── validation.py        # Input validation for all request fields
```

The adapter auto-detects ReleasePilot at runtime. When available, a release-note wizard appears in the dashboard UI, supporting multiple audiences (technical, executive, customer, changelog) and output formats (Markdown, JSON, PDF, DOCX).

ReleasePilot is an optional dependency sourced from [its GitHub repository](https://github.com/polprog-tech/ReleasePilot). It is declared in `pyproject.toml` under `[project.optional-dependencies]` and can be installed with `pip install -e ".[releasepilot]"`. No local clone is required.

See [docs/releasepilot.md](releasepilot.md) for the full integration guide.

## Extensibility Points

| Extension | Where to add |
|-----------|-------------|
| New git provider | Implement `GitProvider` in `git/` (see `GitHubProvider` as reference) |
| Custom status rules | Extend `ReadinessAnalyzer._compute_status()` |
| New report format | Add renderer alongside `DashboardRenderer` |
| CI/CD integration | Add module in `infrastructure/` |
| Slack/email reports | Add notification module |
| PDF export | Render HTML → PDF via headless browser |
| Role-specific views | Add view model variants |
| WebSocket support | Replace SSE in `web/server.py` |
| Layout template | Add to predefined templates in presentation layer |
| Error kind | Add variant to `GitErrorKind` and update `classify_git_error()` (see `rate_limited` as recent example) |
