from pathlib import Path
import typer
from shuka import pipeline, render

app = typer.Typer(add_completion=False)


@app.command()
def demo():
    _execute(Path("samples/complaint_hinglish.wav"), None)


@app.command()
def run(audio: Path = typer.Option(...), image: Path = typer.Option(None)):
    _execute(audio, image)


def _execute(audio: Path, image: Path | None):
    note, wav = pipeline.run_intake(audio, image)
    typer.echo(render.render_terminal(note))
    out = Path("out")
    out.mkdir(exist_ok=True)
    (out / "readback.wav").write_bytes(wav)
    typer.echo("readback written to out/readback.wav")
