# Multi-Source RAG Chatbot_Warhammer 40K

A chatbot that answers Warhammer 40,000 questions from two sources: the Core Rules PDF, searched
with embeddings, and a SQLite database of unit datasheets, queried through text-to-SQL. An LLM
router picks the source on each turn, or uses both. Answers cite their source, and the chat
supports follow-up questions.

Built for the RAG course mini-project by Yawen Zhang and Ruxin Xie.

## How it works

```text
                     question (+ earlier turns)
                                |
                                v
                     rewrite follow-up questions
                                |
                                v
                     LLM router: pdf, sql or both
                      /                       \
                     v                         v
              PDF retriever             Text-to-SQL agent
          embeddings + ChromaDB      LLM writes SQL, runs read-only,
             top-5 passages             retries if it finds nothing
                     \                         /
                      v                       v
               LLM answer, citing pages or the SQL query
```

- **Rulebook:** parsed with docling and split by section into 261 chunks, then embedded locally with
  `bge-small-en-v1.5` and stored in ChromaDB.
- **Database:** the LLM writes SQL using the schema, the names mentioned in the question, and the most
  similar worked examples. Queries run on a read-only connection.
- **Router:** an LLM chooses the source. A question needing both is split into two sub-questions.
- **Chat:** remembers recent turns, shows the sources behind an answer, and can translate it.
- **Evaluation:** covers retrieval, SQL accuracy, and the whole system with RAGAS.

The [technical documentation](TECHNICAL.md) explains each choice and the experiments behind them.

## Quick start

Requires [uv](https://docs.astral.sh/uv/) and a [Google AI Studio](https://aistudio.google.com/) API
key. The rulebook, database and parsed output are already in the repository.

```bash
uv sync                          # install dependencies
cp .env.example .env             # then set GOOGLE_API_KEY in .env
make index                       # build the vector index; the first run downloads the model
make chat                        # start chatting
```

Example questions:

```text
What is the rule for grenades?
What is the toughness of a space marine?
What does Stealth do, and which Tyranids units have it?
```

Type `/help` in the chat for commands: `/sources` shows what an answer was based on, and `/zh`,
`/fr` and `/en` translate the last answer.

On a free API key, the default model allows only about 5 requests per minute and 20 per day, and
one question takes 2 to 3 calls. Add `GEMINI_MIN_INTERVAL_S=12` to `.env` to stay within the
per-minute limit, or use a model with a larger quota, such as `GEMINI_MODEL=gemini-3.1-flash-lite`.

If `make` is not available, each target below is one `uv run` command, listed in the
[`Makefile`](Makefile).

## Commands

| Command | What it does | Needs API key |
|---|---|---|
| `make chat` | Multi-turn chat | Yes |
| `make sanity` | Asks the four questions listed in the course | Yes |
| `make demo` | Scripted run across every path ([example output](DEMO.md)) | Yes |
| `make test` | Unit tests | No |
| `make index` | Chunk the parsed rulebook and build the vector index | No |
| `make parse` | Re-parse the PDF; slow, and the output is already committed | No |
| `make eval` | PDF retrieval evaluation | No |
| `make eval-sql` | SQL accuracy evaluation | Yes |
| `make eval-e2e` | Full evaluation with RAGAS; up to about 530 API calls | Yes |

## Results

Latest end-to-end run on 40 questions, with `gemini-3.5-flash` answering and
`gemini-3.1-flash-lite` judging:

| Metric | Score |
|---|---|
| Router accuracy | 40/40 |
| PDF section hit@5 | 25/25 |
| SQL relaxed match / exact match | 22/22 / 14/22 |
| RAGAS faithfulness | 0.963 |
| RAGAS answer relevancy | 0.917 |
| RAGAS answer correctness | 0.797 |
| RAGAS context recall | 0.985 |

The set is small and these scores are probably optimistic. See
[how to read them](TECHNICAL.md#11-results) and the
[known limitations](TECHNICAL.md#12-known-limitations).

## Repository layout

```text
TECHNICAL.md        Design, choices and their reasons, results, limitations
rag/data/raw/            Rulebook, SQLite database, data dictionary
rag/data/parsed/         Parsed rulebook
rag/data/eval_results/   Evaluation reports and analysis
rag/src_rag/             Source: parser, chunker, retriever, llm, chatbot, evaluation
tests/                   Unit tests, mirroring the source layout
```

## Team

| Member | Work |
|---|---|
| Yawen Zhang ([@nanfanggaosu](https://github.com/nanfanggaosu)) | PDF path: parser, chunker, PDF retriever and its evaluation. Router, answer generation and the chat: conversation, commands, translation, demo and sanity runs. |
| Ruxin Xie ([@xieruxin922](https://github.com/xieruxin922)) | SQL path: text-to-SQL agent, schema and value indexes, few-shot examples, safe execution and its evaluation. Shared Gemini wrapper. End-to-end RAGAS evaluation and the SQL experiments. |
| Both | Shared interfaces between modules, and documentation. |
