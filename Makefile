.PHONY: install sync parse chunk index chat demo sanity eval eval-sql eval-e2e test clean

install:
	uv sync

sync:
	uv sync

parse:
	uv run python -m rag.src_rag.parser.parse_pdf

chunk:
	uv run python -m rag.src_rag.chunker.chunk

index:
	uv run python -m rag.src_rag.retriever.pdf

chat:
	uv run python -m rag.src_rag.chatbot.app

demo:
	uv run python -m rag.src_rag.chatbot.demo

sanity:
	uv run python -m rag.src_rag.chatbot.sanity

eval:
	uv run python -m rag.src_rag.evaluation.pdf_eval --verbose

eval-sql:
	uv run python -m rag.src_rag.evaluation.sql_eval

eval-e2e:
	uv run python -m rag.src_rag.evaluation.e2e_eval --model gemini-3.1-flash-lite

test:
	uv run pytest -q

clean:
	rm -rf rag/data/parsed rag/data/index .pytest_cache .ruff_cache __pycache__
