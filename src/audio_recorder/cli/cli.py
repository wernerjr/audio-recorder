from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

app = typer.Typer(
    name="audio-recorder",
    help="Gravador de áudio com transcrição em tempo real.",
    no_args_is_help=True,
)


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
            typer.echo(f"  [{d['index']}] {d['name']}  —  {d['channels']}ch  {d['sample_rate']}Hz{marker}")
    else:
        typer.echo("  Nenhum microfone encontrado.")

    typer.echo("\nLoopback (áudio do sistema):")
    ok, msg = check_loopback_dependency()
    if all_devices["loopback"]:
        for d in all_devices["loopback"]:
            typer.echo(f"  [{d['index']}] {d['name']}  —  {d['channels']}ch  {d['sample_rate']}Hz")
    elif ok:
        typer.echo("  Dispositivo de loopback será detectado automaticamente na gravação.")
    else:
        typer.secho(f"  Aviso: {msg}", fg=typer.colors.YELLOW)

    typer.echo()


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
) -> None:
    """Inicia a gravação de áudio (mic + sistema) com transcrição em tempo real."""
    typer.secho(
        "Comando 'record' ainda não implementado. Disponível na Fase 2.",
        fg=typer.colors.YELLOW,
    )


@app.command()
def transcribe(
    audio: Annotated[Path, typer.Argument(help="Arquivo .wav ou pasta de sessão para transcrever")],
    model: Annotated[
        Optional[str],
        typer.Option("--model", "-m", help="Modelo Whisper"),
    ] = None,
    lang: Annotated[
        Optional[str],
        typer.Option("--lang", "-l", help="Idioma"),
    ] = None,
    fmt: Annotated[
        Optional[str],
        typer.Option("--format", "-f", help="Formato de saída: txt, srt, json"),
    ] = None,
) -> None:
    """Transcreve um arquivo de áudio existente."""
    typer.secho(
        "Comando 'transcribe' ainda não implementado. Disponível na Fase 2.",
        fg=typer.colors.YELLOW,
    )


if __name__ == "__main__":
    app()
