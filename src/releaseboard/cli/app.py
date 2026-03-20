"""ReleaseBoard CLI — main entry point."""

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from releaseboard import __version__
from releaseboard.i18n import t

app = typer.Typer(
    name="releaseboard",
    help="ReleaseBoard — Internal release-readiness dashboard generator.",
    no_args_is_help=True,
)
console = Console(stderr=True)


@app.command()
def generate(
    config: Path = typer.Option(
        "releaseboard.json",
        "--config",
        "-c",
        help="Path to configuration file.",
        exists=True,
        readable=True,
    ),
    output: str | None = typer.Option(
        None, "--output", "-o", help="Override output path for the HTML dashboard."
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging."),
    theme: str | None = typer.Option(
        None, "--theme", "-t", help="Override default theme (light/dark/system)."
    ),
) -> None:
    """Generate a static release-readiness HTML dashboard."""
    from dataclasses import replace

    from releaseboard.application.service import AnalysisService
    from releaseboard.config.loader import load_config
    from releaseboard.config.schema import ConfigValidationError
    from releaseboard.git.local_provider import LocalGitProvider
    from releaseboard.presentation.renderer import DashboardRenderer
    from releaseboard.presentation.view_models import build_dashboard_view_model
    from releaseboard.shared.logging import configure_root_logger

    configure_root_logger(verbose)

    # Load config
    try:
        app_config = load_config(config)
    except FileNotFoundError as exc:
        console.print(f"[red]{t('cli.error_prefix')}[/red] {exc}")
        raise typer.Exit(1) from exc
    except ConfigValidationError as exc:
        console.print(f"[red]{t('cli.validation_failed')}:[/red]")
        for err in exc.errors:
            console.print(f"  • {err}")
        raise typer.Exit(1) from exc

    # Apply CLI overrides
    if output:
        app_config = replace(
            app_config, settings=replace(app_config.settings, output_path=output)
        )
    if theme:
        app_config = replace(
            app_config, settings=replace(app_config.settings, theme=theme)
        )

    console.print(f"\n[bold]ReleaseBoard[/bold] v{__version__}")
    console.print(f"Release: [cyan]{app_config.release.name}[/cyan]")
    console.print(f"{t('cli.col.repository')}: [cyan]{len(app_config.repositories)}[/cyan]\n")

    # Run analysis using shared service
    git_provider = LocalGitProvider()
    service = AnalysisService(git_provider)

    with console.status(f"[bold green]{t('cli.analyzing')}") as spinner:

        def _on_progress(event_type: str, progress) -> None:
            if event_type == "repo_start":
                spinner.update(
                    f"[bold green]{t('cli.analyzing')}[/bold green] {progress.current_repo} "
                    f"({progress.completed + 1}/{progress.total})"
                )

        result = asyncio.run(service.analyze_async(app_config, on_progress=_on_progress))

    _print_summary(result.analyses, result.metrics)

    # Render static dashboard — load raw config so milestone data is embedded
    import json as _json
    _config_raw = _json.loads(config.read_text(encoding="utf-8")) if config.exists() else {}
    view_model = build_dashboard_view_model(
        app_config, result.analyses, result.metrics, config_raw=_config_raw,
    )
    renderer = DashboardRenderer()
    output_path = renderer.render_to_file(view_model, app_config.settings.output_path)

    console.print(
        f"\n[bold green]✓[/bold green] {t('cli.dashboard_generated')}: "
        f"[link=file://{output_path}]{output_path}[/link]"
    )


@app.command()
def serve(
    config: Path = typer.Option(
        "releaseboard.json",
        "--config",
        "-c",
        help="Path to configuration file.",
    ),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Bind host."),
    port: int = typer.Option(8080, "--port", "-p", help="Bind port."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging."),
) -> None:
    """Start the interactive web dashboard server."""
    import uvicorn

    from releaseboard.shared.logging import configure_root_logger
    from releaseboard.web.server import create_app

    configure_root_logger(verbose)

    first_run = not config.exists()

    console.print(f"\n[bold]ReleaseBoard[/bold] v{__version__} — Interactive Mode")
    if first_run:
        console.print("[yellow]No configuration file found.[/yellow]")
        console.print("The dashboard will open in setup mode.\n")
    else:
        console.print(f"Config: [cyan]{config}[/cyan]")
    console.print(f"Server: [link=http://{host}:{port}]http://{host}:{port}[/link]\n")

    web_app = create_app(config, first_run=first_run)
    uvicorn.run(web_app, host=host, port=port, log_level="info" if verbose else "warning")


@app.command()
def validate(
    config: Path = typer.Option(
        "releaseboard.json",
        "--config",
        "-c",
        help="Path to configuration file to validate.",
        exists=True,
        readable=True,
    ),
) -> None:
    """Validate a ReleaseBoard configuration file."""
    import json

    from releaseboard.config.schema import validate_config, validate_layer_references

    raw = json.loads(config.read_text(encoding="utf-8"))
    errors = validate_config(raw)
    ref_errors = validate_layer_references(raw)
    all_errors = errors + ref_errors

    if all_errors:
        console.print(f"[red]{t('cli.validation_failed')}:[/red]")
        for err in all_errors:
            console.print(f"  • {err}")
        raise typer.Exit(1)
    else:
        console.print(f"[bold green]✓[/bold green] {t('cli.validation_success')}")


@app.command()
def version() -> None:
    """Show ReleaseBoard version."""
    console.print(f"ReleaseBoard v{__version__}")


def _print_summary(analyses: list, metrics) -> None:
    """Print a CLI summary table."""
    from releaseboard.domain.enums import ReadinessStatus

    table = Table(title=t("cli.summary_title"), show_lines=False)
    table.add_column(t("cli.col.repository"), style="bold")
    table.add_column(t("cli.col.layer"))
    table.add_column(t("cli.col.status"))
    table.add_column(t("cli.col.branch"))

    status_styles = {
        ReadinessStatus.READY: f"[green]{t('status.ready')}[/green]",
        ReadinessStatus.MISSING_BRANCH: f"[red]{t('status.missing_branch')}[/red]",
        ReadinessStatus.INVALID_NAMING: f"[yellow]{t('status.invalid_naming')}[/yellow]",
        ReadinessStatus.STALE: f"[magenta]{t('status.stale')}[/magenta]",
        ReadinessStatus.INACTIVE: f"[dim]{t('status.inactive')}[/dim]",
        ReadinessStatus.WARNING: f"[yellow]{t('status.warning')}[/yellow]",
        ReadinessStatus.ERROR: f"[red]{t('status.error')}[/red]",
        ReadinessStatus.UNKNOWN: f"[dim]{t('status.unknown')}[/dim]",
    }

    for a in sorted(analyses, key=lambda x: (x.status.severity, x.layer, x.name)):
        branch = a.branch.name if a.branch and a.branch.exists else "—"
        table.add_row(
            a.name,
            a.layer,
            status_styles.get(a.status, str(a.status)),
            branch,
        )

    console.print(table)
    console.print(
        f"\n📊 {t('cli.readiness')}: [bold]{metrics.readiness_pct:.0f}%[/bold] "
        f"({metrics.ready}/{metrics.total})"
    )
