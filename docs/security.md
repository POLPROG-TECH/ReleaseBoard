# Security Considerations

## Table of Contents

- [Credential Handling](#credential-handling)
- [Git Access](#git-access)
- [Output Files](#output-files)
- [Config File](#config-file)

## Credential Handling

ReleaseBoard never stores credentials in configuration files. Instead:

1. **Environment variable placeholders** — use `${VAR_NAME}` in URLs:
   ```json
   { "url": "https://${GITHUB_TOKEN}@github.com/acme/repo.git" }
   ```

2. **Git credential helpers** — if your system has `git credential-helper` configured, ReleaseBoard benefits automatically since it uses the `git` CLI.

3. **SSH keys** — use SSH URLs for repos where SSH auth is configured:
   ```json
   { "url": "git@github.com:acme/repo.git" }
   ```

## Git Access

ReleaseBoard uses the local `git` CLI via subprocess. It runs:
- `git ls-remote --heads <url>` — to list branches
- `git log` — for metadata on local clones only

Repository URLs are resolved from the most specific source available: explicit repository URL → layer `repository_root_url` → global `repository_root_url`. Credentials embedded via `${ENV}` placeholders in any of these root URLs are resolved at runtime and never persisted.

It does not:
- Clone repositories
- Write to repositories
- Store git data
- Cache credentials

## Output Files

The generated HTML dashboard may contain:
- Repository names and URLs
- Branch names
- Commit metadata (author, date, message)
- Layer/group information

Treat the output file with the same access controls as your repository metadata.

## Config File

The config file may contain repository URLs with embedded tokens (via `${ENV}` resolution). Never commit resolved config files with credentials to version control.

Recommended `.gitignore` entries:

```text
.env
*.local.json
```
