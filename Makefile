install:
	uv sync

demo:
	INTAKE_MODE=mock uv run shuka demo

run:
	uv run shuka run --audio $(AUDIO) $(if $(IMAGE),--image $(IMAGE),)

serve:
	uv run uvicorn shuka.server:app --reload

test:
	uv run pytest tests -q
	uv run python eval/run_eval.py --gates

audit:
	uv run python eval/run_eval.py --grounding

contrast:
	uv run python eval/run_eval.py --contrast

lint:
	uv run ruff check src eval tests
