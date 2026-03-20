# JSON Schema Reference

## Table of Contents

- [Overview](#overview)
- [Validation](#validation)
  - [1. Schema Validation](#1-schema-validation)
  - [2. Semantic Validation](#2-semantic-validation)
- [Schema Fields](#schema-fields)
  - [`layers[]` fields](#layers-fields)
  - [`author` fields](#author-fields)
  - [`layout` fields](#layout-fields)
- [Error Reporting](#error-reporting)
- [Using the Schema](#using-the-schema)
  - [In your editor](#in-your-editor)
  - [Programmatic validation](#programmatic-validation)

## Overview

ReleaseBoard configuration is validated against a JSON Schema (Draft 7) located at:

```text
src/releaseboard/config/schema.json
```

The schema enforces:
- Required fields (`release`, `repositories`)
- Type constraints (strings, integers, arrays)
- Value ranges (month 1–12, year 2000–2100)
- Enum values (theme: light/dark/system)
- Pattern validation (hex colors, layer IDs)
- No additional properties at any level
- Optional `author` section with all-optional fields (name, role, url, tagline, copyright)

## Validation

Config is validated in two phases:

### 1. Schema Validation
Structural validation against the JSON Schema using `jsonschema.Draft7Validator`.

### 2. Semantic Validation
Business rule checks that go beyond schema:
- Layer reference validation: all repository `layer` fields must reference defined layers

## Schema Fields

### `layers[]` fields

The `layers` array supports the following fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | ✅ | Unique layer identifier |
| `label` | string | ✅ | Display label |
| `branch_pattern` | string | — | Layer-level branch pattern override |
| `repository_root_url` | string | — | Root URL prefix for repositories in this layer (used when a repository does not specify an explicit `url`) |
| `color` | string | — | Hex color for badges and charts |
| `order` | integer | — | Display order (lower = first) |

### `layout` fields

The optional `layout` section controls dashboard section ordering and layout templates.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `default_template` | string | — | Active layout template (`default`, `executive`, `release-manager`, `engineering`, `compact`, or user-created name) |
| `section_order` | array of strings | — | Ordered list of visible section IDs: `score`, `metrics`, `charts`, `filters`, `attention`, `layer-{id}`, `summary` |
| `enable_drag_drop` | boolean | — | Enable drag-and-drop section reordering (default `true`) |

All fields are optional. `additionalProperties` is `false` — no extra keys allowed.

## Error Reporting

Validation errors include the JSON path to the problem:

```
release.target_month: 13 is greater than the maximum of 12
settings.theme: 'rainbow' is not one of ['light', 'dark', 'system']
repositories[2].layer: 'backend' is not defined in layers
```

## Using the Schema

### In your editor

Point your JSON editor to the schema for autocompletion:

```json
{
  "$schema": "./src/releaseboard/config/schema.json",
  "release": { ... }
}
```

### Programmatic validation

```python
from releaseboard.config.schema import validate_config, validate_config_strict

errors = validate_config(data)          # Returns list of error strings
validate_config_strict(data)            # Raises ConfigValidationError
```
