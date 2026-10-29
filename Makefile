.PHONY: install sync parse index chat eval test clean

install:
	uv sync

sync:
	uv sync

parse:
	uv run python -m rag.src_rag.parser.parse_pdf

index:
	uv run python -m rag.src_rag.retriever.build_index

chat:
	uv run python -m rag.src_rag.chatbot.app

eval:
	uv run python -m rag.src_rag.evaluation.run

test:
	uv run pytest -q

clean:
	rm -rf rag/data/parsed rag/data/index .pytest_cache .ruff_cache __pycache__
