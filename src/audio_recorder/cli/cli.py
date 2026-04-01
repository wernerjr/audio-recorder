from __future__ import annotations

import logging
import queue
import threading
import time
from pathlib import Path
from typing import Annotated, Optional

import typer

app = typer.Typer(
    name="audio-recorder",
    help="Gravador de áudio com transcrição em tempo real.",
    no_args_is_help=True,
)

_DEFAULT_CONFIG = Path("config.toml")


@app.command()
def gui() -> None:
    """Abre a interface gráfica (PySide6)."""
    from ..gui.app import run
    run()


def _setup_logging(verbose: bool, quiet: bool) -> None:
    if quiet:
        level = logging.ERROR
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _collect_and_display(
    result_queue: queue.Queue,
    results: list,
    stop_event: threading.Event,
    quiet: bool,
) -> None:
    """Background thread: drains result_queue, displays and accumulates results."""
    from ..utils.timestamp import format_ts
    while not stop_event.is_set() or not result_queue.empty():
        try:
            result = result_queue.get(timeout=0.1)
            results.append(result)
            if not quiet:
                ts = format_ts(result.start)
                label = result.source.upper()
                if result.speaker:
                    label += f"/{result.speaker}"
                typer.echo(f"  [{ts}] [{label}] {result.text}")
        except queue.Empty:
            continue


@app.command()
def record(
    config: Annotated[
        Optional[Path],
        typer.Option("--config", "-c", help="Caminho para config.toml"),
    ] = None,
    model: Annotated[
        Optional[str],
        typer.Option("--model", "-m", help="Modelo Whisper (tiny/base/small/medium/large)"),
    ] = None,
    lang: Annotated[
        Optional[str],
        typer.Option("--lang", "-l", help="Idioma (auto, pt, en, ...)"),
    ] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Log detalhado")] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Silencia saída exceto erros")] = False,
) -> None:
    """Inicia a gravação de áudio (mic + sistema) com transcrição em tempo real."""
    _setup_logging(verbose, quiet)

    from ..config.settings import load_settings
    from ..diarization.engine import DiarizationEngine
    from ..session.session import RecordingSession, session_output_dir

    config_path = config or (_DEFAULT_CONFIG if _DEFAULT_CONFIG.exists() else None)
    try:
        settings = load_settings(config_path)
    except ValueError as exc:
        typer.secho(f"Erro na configuração: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    # CLI overrides
    if model:
        settings.transcription.model = model
    if lang:
        settings.transcription.language = lang

    output_dir = session_output_dir(settings.output.directory)
    session = RecordingSession(settings, output_dir)
    results = []
    stop_display = threading.Event()

    display_thread = threading.Thread(
        target=_collect_and_display,
        args=(session.result_queue, results, stop_display, quiet),
        daemon=True,
    )

    try:
        session.start()
    except Exception as exc:
        typer.secho(f"Falha ao iniciar gravação: {exc}", fg=typer.colors.RED, err=True)
        typer.secho(
            "Dica: rode 'audio-recorder devices' para verificar os dispositivos disponíveis.",
            fg=typer.colors.YELLOW, err=True,
        )
        raise typer.Exit(1)

    display_thread.start()

    if not quiet:
        typer.secho(f"\nGravando...  Ctrl+C para parar.", fg=typer.colors.GREEN)
        typer.echo(f"Sessão: {output_dir}\n")

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass

    if not quiet:
        typer.echo("\nParando gravação...")

    session.stop()
    stop_display.set()
    display_thread.join(timeout=10)

    # Optional diarization
    diarization_segments = None
    if settings.diarization.enabled and settings.diarization.token:
        if not quiet:
            typer.echo("Executando diarização...")
        try:
            engine = DiarizationEngine(settings.diarization.token)
            mic_wav = output_dir / "microfone.wav"
            if mic_wav.exists():
                diarization_segments = engine.diarize(mic_wav)
        except Exception as exc:
            typer.secho(f"Diarização falhou: {exc}", fg=typer.colors.YELLOW, err=True)

    if not quiet:
        typer.echo("Gerando arquivos de transcrição...")

    try:
        session.merge_and_save(results, diarization_segments)
    except Exception as exc:
        typer.secho(f"Erro ao salvar transcrição: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    if not quiet:
        typer.secho("\nSessão salva no histórico.", fg=typer.colors.GREEN)
        typer.echo()


@app.command()
def history(
    config: Annotated[
        Optional[Path],
        typer.Option("--config", "-c", help="Caminho para config.toml"),
    ] = None,
) -> None:
    """Lista sessões gravadas no histórico."""
    from ..config.settings import load_settings
    from ..persistence.database import get_db, list_sessions

    config_path = config or (_DEFAULT_CONFIG if _DEFAULT_CONFIG.exists() else None)
    settings = load_settings(config_path)
    db_path = (
        Path(settings.output.db_path)
        if settings.output.db_path
        else Path(settings.output.directory) / "history.db"
    )

    if not db_path.exists():
        typer.echo("Nenhum histórico encontrado.")
        return

    db = get_db(db_path)
    try:
        sessions = list_sessions(db)
    finally:
        db.close()

    if not sessions:
        typer.echo("Nenhuma sessão gravada.")
        return

    typer.echo(f"\n{'ID':>4}  {'Data/Hora':<20}  {'Duração':>8}  {'Seg.':>5}  Diretório")
    typer.echo("-" * 72)
    for s in sessions:
        duration = s.get("duration_s") or 0.0
        mins, secs = divmod(int(duration), 60)
        started = s["started_at"].replace("T", " ")[:16]
        typer.echo(
            f"{s['id']:>4}  {started:<20}  {mins:02d}:{secs:02d}     "
            f"{s['segment_count']:>5}  {s['output_dir']}"
        )
    typer.echo()


@app.command()
def show(
    session_id: Annotated[int, typer.Argument(help="ID da sessão (ver 'history')")],
    search: Annotated[
        Optional[str],
        typer.Option("--search", "-s", help="Filtrar segmentos por texto"),
    ] = None,
    config: Annotated[
        Optional[Path],
        typer.Option("--config", "-c", help="Caminho para config.toml"),
    ] = None,
) -> None:
    """Exibe a transcrição de uma sessão gravada."""
    from ..config.settings import load_settings
    from ..persistence.database import get_db, get_segments, search_segments
    from ..utils.timestamp import format_ts

    config_path = config or (_DEFAULT_CONFIG if _DEFAULT_CONFIG.exists() else None)
    settings = load_settings(config_path)
    db_path = (
        Path(settings.output.db_path)
        if settings.output.db_path
        else Path(settings.output.directory) / "history.db"
    )

    if not db_path.exists():
        typer.secho("Histórico não encontrado.", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    db = get_db(db_path)
    try:
        if search:
            rows = [
                r for r in search_segments(db, search)
                if r["session_id"] == session_id
            ]
        else:
            rows = get_segments(db, session_id)
    finally:
        db.close()

    if not rows:
        typer.echo("Nenhum segmento encontrado.")
        return

    typer.echo()
    for r in rows:
        ts = format_ts(r["start"])
        label = r["source"].upper()
        if r.get("speaker"):
            label += f"/{r['speaker']}"
        typer.echo(f"  [{ts}] [{label}] {r['text']}")
    typer.echo()


@app.command()
def devices() -> None:
    """Lista microfones e dispositivos de loopback disponíveis."""
    from ..capture.factory import list_devices
    from ..utils.platform import check_loopback_dependency

    all_devices = list_devices()

    typer.echo("\nMicrofones (entrada):")
    if all_devices["mics"]:
        for d in all_devices["mics"]:
            marker = " (padrão)" if d["is_default"] else ""
            typer.echo(
                f"  [{d['index']}] {d['name']}"
                f"  —  {d['channels']}ch  {d['sample_rate']}Hz{marker}"
            )
    else:
        typer.echo("  Nenhum microfone encontrado.")

    typer.echo("\nLoopback (áudio do sistema):")
    ok, msg = check_loopback_dependency()
    if all_devices["loopback"]:
        for d in all_devices["loopback"]:
            typer.echo(
                f"  [{d['index']}] {d['name']}"
                f"  —  {d['channels']}ch  {d['sample_rate']}Hz"
            )
    elif ok:
        typer.echo("  Dispositivo de loopback detectado automaticamente na gravação.")
    else:
        typer.secho(f"  Aviso: {msg}", fg=typer.colors.YELLOW)

    typer.echo()


if __name__ == "__main__":
    app()
