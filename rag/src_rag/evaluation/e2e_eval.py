"""End-to-end evaluation of the whole chatbot on a mixed PDF / SQL / both question set.

For each question: router -> retriever(s) -> synthesized answer, then score
  - router accuracy against the labelled source,
  - retrieval: PDF section/page hit and SQL execution accuracy against gold results,
  - RAGAS: faithfulness, answer relevancy, context precision, context recall, answer correctness.

    uv run python -m rag.src_rag.evaluation.e2e_eval
    uv run python -m rag.src_rag.evaluation.e2e_eval --judge-rpm 60
    uv run python -m rag.src_rag.evaluation.e2e_eval --skip-ragas

Every LLM call is cached on disk, so after a quota error rerunning the same command resumes
where it stopped. Questions hit by an LLM failure are reported as incomplete, never scored:
the router's fallback to PDF would otherwise count quota errors as correct PDF routing.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from rag.src_rag.chatbot.app import _format_sql, answer
from rag.src_rag.interfaces import Llm, PdfRag, SqlRag, SqlRagResult
from rag.src_rag.retriever.sql import run_sql
from rag.src_rag.retriever.sql_examples import (
    EXPECTED_MAX_ROWS,
    load_examples,
    result_rows,
    results_contain,
    results_match,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
QUESTIONS_PATH = Path(__file__).resolve().parent / "questions_e2e.jsonl"
RESULTS_DIR = PROJECT_ROOT / "rag" / "data" / "eval_results"
SOURCES = ("pdf", "sql", "both")
# RAGAS makes about three calls for every chatbot call, so a cheaper, faster judge keeps a run practical.
DEFAULT_JUDGE_MODEL = "gemini-3.1-flash-lite"
_SOURCE_TRAILER = re.compile(r"\n\s*\W*Source:.*\Z", re.DOTALL)
RAGAS_METRICS = (
    "faithfulness",
    "answer_relevancy",
    "llm_context_precision_with_reference",
    "context_recall",
    "answer_correctness",
)


@dataclass(frozen=True)
class E2eQuestion:
    id: str
    question: str
    expected_source: str
    reference: str
    expected_pages: tuple[int, ...] = ()
    expected_sections: tuple[str, ...] = ()
    expected_rows: tuple[tuple[Any, ...], ...] | None = None


@dataclass
class Record:
    id: str
    question: str
    expected_source: str
    reference: str
    routed_source: str = ""
    rationale: str = ""
    answer: str = ""
    contexts: list[str] = field(default_factory=list)
    pages: list[int] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)
    sql: str = ""
    sql_error: str | None = None
    section_hit: bool | None = None
    page_hit: bool | None = None
    sql_exact: bool | None = None
    sql_relaxed: bool | None = None
    failure: str | None = None
    ragas: dict[str, float] = field(default_factory=dict)


class TrackingLlm:
    """Remembers LLM failures that the router and answer fallbacks would otherwise hide."""

    def __init__(self, llm: Llm) -> None:
        self._llm = llm
        self.failure: str | None = None

    def complete(self, prompt: str) -> str:
        return self._track(self._llm.complete, prompt)

    def complete_json(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        return self._track(self._llm.complete_json, prompt, schema)

    def _track(self, call, *args):
        try:
            return call(*args)
        except Exception as e:
            self.failure = str(e)
            raise


def load_questions(path: Path = QUESTIONS_PATH) -> list[E2eQuestion]:
    sql_examples = {e.id: e for e in load_examples("eval")}
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        d = json.loads(line)
        expected = None
        if "sql_example" in d:
            expected = sql_examples[d["sql_example"]].expected
        elif "gold_sql" in d:
            gold = run_sql(d["gold_sql"], max_rows=EXPECTED_MAX_ROWS)
            if gold.error:
                raise ValueError(f"{d['id']}: gold SQL failed: {gold.error}")
            expected = result_rows(gold)
        reference = d["reference"]
        if "GOLD_COUNT" in reference:
            reference = reference.replace("GOLD_COUNT", str(expected[0][0]))
        out.append(E2eQuestion(
            id=d["id"],
            question=d["question"],
            expected_source=d["expected_source"],
            reference=reference,
            expected_pages=tuple(d.get("expected_pages", ())),
            expected_sections=tuple(s.upper() for s in d.get("expected_sections", ())),
            expected_rows=expected,
        ))
    return out


def run_question(q: E2eQuestion, llm: TrackingLlm, *, pdf_rag: PdfRag, sql_rag: SqlRag) -> Record:
    rec = Record(q.id, q.question, q.expected_source, q.reference)
    llm.failure = None
    out = answer(q.question, pdf_rag=pdf_rag, sql_rag=sql_rag, llm=llm)
    rec.failure = llm.failure
    rec.routed_source = out.source
    rec.rationale = out.decision.rationale
    rec.answer = out.text

    if q.expected_sections:
        chunks = out.pdf.chunks if out.pdf else []
        rec.pages = [c.page for c in chunks]
        rec.sections = [c.section or "" for c in chunks]
        rec.page_hit = any(p in q.expected_pages for p in rec.pages)
        rec.section_hit = any(s.upper() in q.expected_sections for s in rec.sections)
    if q.expected_rows is not None:
        actual = out.sql or SqlRagResult(sql="", rows=[], columns=[], error="SQL path not called")
        rec.sql = actual.sql
        rec.sql_error = actual.error
        rows = result_rows(actual)
        rec.sql_exact = actual.error is None and results_match(q.expected_rows, rows)
        rec.sql_relaxed = actual.error is None and results_contain(q.expected_rows, rows)

    if out.pdf:
        rec.contexts += [f"[p. {c.page}, {c.section}]\n{c.text}" for c in out.pdf.chunks]
    if out.sql:
        rec.contexts.append(_format_sql(out.sql))
    return rec


def _rate(values: list[bool | None]) -> float | None:
    known = [v for v in values if v is not None]
    return sum(known) / len(known) if known else None


def _mean(values: list[float]) -> float | None:
    known = [v for v in values if not math.isnan(v)]
    return sum(known) / len(known) if known else None


def summarize(records: list[Record]) -> dict[str, Any]:
    done = [r for r in records if not r.failure]
    groups: dict[str, list[Record]] = defaultdict(list)
    for r in done:
        groups[r.expected_source].append(r)

    def block(rows: list[Record]) -> dict[str, Any]:
        return {
            "questions": len(rows),
            "router_accuracy": _rate([r.routed_source == r.expected_source for r in rows]),
            "pdf_section_hit": _rate([r.section_hit for r in rows]),
            "pdf_page_hit": _rate([r.page_hit for r in rows]),
            "sql_exact": _rate([r.sql_exact for r in rows]),
            "sql_relaxed": _rate([r.sql_relaxed for r in rows]),
            "sql_errors": sum(r.sql_error is not None for r in rows),
            "ragas": {
                m: _mean([r.ragas[m] for r in rows if m in r.ragas]) for m in RAGAS_METRICS
            },
            "ragas_missing": {
                m: sum(m not in r.ragas or math.isnan(r.ragas[m]) for r in rows)
                for m in RAGAS_METRICS
            },
        }

    return {
        "total_questions": len(records),
        "incomplete": [r.id for r in records if r.failure],
        "overall": block(done),
        "by_source": {s: block(groups[s]) for s in SOURCES if groups[s]},
        "router_confusion": {
            s: {t: sum(r.routed_source == t for r in groups[s]) for t in SOURCES}
            for s in SOURCES if groups[s]
        },
        "router_mistakes": [
            {"id": r.id, "expected": r.expected_source, "routed": r.routed_source}
            for r in done if r.routed_source != r.expected_source
        ],
    }


def answer_for_scoring(text: str) -> str:
    """Drop the trailing SQL citation: RAGAS would judge each query detail as a false claim."""
    return _SOURCE_TRAILER.sub("", text).strip()


def score_with_ragas(records: list[Record], llm: Llm, *, rpm_workers: int = 1) -> None:
    os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")
    from rag.src_rag.evaluation.ragas_adapters import ragas_metrics, wrap_embeddings, wrap_llm
    from ragas import EvaluationDataset, RunConfig, SingleTurnSample, evaluate

    scored = [r for r in records if not r.failure and r.contexts and r.answer]
    if not scored:
        return
    dataset = EvaluationDataset([
        SingleTurnSample(
            user_input=r.question,
            response=answer_for_scoring(r.answer),
            retrieved_contexts=r.contexts,
            reference=r.reference,
        )
        for r in scored
    ])
    result = evaluate(
        dataset,
        metrics=ragas_metrics(),
        llm=wrap_llm(llm),
        embeddings=wrap_embeddings(),
        run_config=RunConfig(max_workers=rpm_workers, max_retries=1, timeout=3600),
        raise_exceptions=False,
        show_progress=True,
    )
    for rec, row in zip(scored, result.to_pandas().to_dict("records")):
        rec.ragas = {m: float(row[m]) for m in RAGAS_METRICS if m in row}


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _missing_score_warning(summary: dict[str, Any]) -> list[str]:
    missing = {m: n for m, n in summary["overall"]["ragas_missing"].items() if n}
    if not missing:
        return []
    return [f"**Incomplete: RAGAS scores missing, rerun to finish: {missing}**", ""]


def render_report(summary: dict[str, Any], records: list[Record], model: str) -> str:
    blocks = {"overall": summary["overall"], **summary["by_source"]}
    names = list(blocks)
    lines = [
        "# End-to-end evaluation",
        "",
        f"Model: `{model}`. Questions: {summary['total_questions']}, "
        f"incomplete: {len(summary['incomplete'])}.",
        "",
        *_missing_score_warning(summary),
        "| Metric | " + " | ".join(names) + " |",
        "|---|" + "---|" * len(names),
    ]
    for label, key in (
        ("Questions", "questions"),
        ("Router accuracy", "router_accuracy"),
        ("PDF section hit@5", "pdf_section_hit"),
        ("PDF page hit@5", "pdf_page_hit"),
        ("SQL exact match", "sql_exact"),
        ("SQL relaxed match", "sql_relaxed"),
        ("SQL errors", "sql_errors"),
    ):
        cells = [
            str(b[key]) if isinstance(b[key], int) else _fmt(b[key]) for b in blocks.values()
        ]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    for metric in RAGAS_METRICS:
        cells = [_fmt(b["ragas"].get(metric)) for b in blocks.values()]
        lines.append(f"| RAGAS {metric} | " + " | ".join(cells) + " |")

    lines += ["", "## Router confusion (rows: expected, columns: routed)", ""]
    lines += ["| expected | " + " | ".join(SOURCES) + " |", "|---|---|---|---|"]
    for source, row in summary["router_confusion"].items():
        lines.append(f"| {source} | " + " | ".join(str(row[t]) for t in SOURCES) + " |")

    lines += ["", "## Per question", ""]
    lines += [
        "| id | routed | section | SQL | faith | relev | c.prec | c.rec | correct |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in records:
        sql = "" if r.sql_exact is None else ("exact" if r.sql_exact else ("relaxed" if r.sql_relaxed else "wrong"))
        section = "" if r.section_hit is None else ("hit" if r.section_hit else "miss")
        scores = [_fmt(r.ragas.get(m)) for m in RAGAS_METRICS]
        lines.append(f"| {r.id} | {r.routed_source} | {section} | {sql} | " + " | ".join(scores) + " |")
    return "\n".join(lines) + "\n"


def main() -> None:
    from rag.src_rag.llm.gemini import GeminiLlm
    from rag.src_rag.retriever.pdf import pdf_rag
    from rag.src_rag.retriever.sql_rag import SqlRag as GeminiSqlRag

    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", help="Gemini model for the chatbot")
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL, help="Gemini model for the RAGAS judge")
    parser.add_argument("--rpm", type=float, default=14.0, help="chatbot requests per minute to stay under")
    parser.add_argument("--judge-rpm", type=float, default=14.0, help="judge requests per minute to stay under")
    parser.add_argument("--skip-ragas", action="store_true")
    parser.add_argument("--limit", type=int, help="only run the first N of each source, as a smoke test")
    parser.add_argument("--out", type=Path, default=RESULTS_DIR)
    args = parser.parse_args()

    base = GeminiLlm(args.model, min_interval_s=60.0 / args.rpm)
    llm = TrackingLlm(base)
    sql = GeminiSqlRag(llm)

    questions = load_questions()
    if args.limit:
        questions = [
            q for s in SOURCES for q in [x for x in questions if x.expected_source == s][: args.limit]
        ]

    records: list[Record] = []
    for i, q in enumerate(questions, 1):
        rec = run_question(q, llm, pdf_rag=pdf_rag, sql_rag=sql)
        records.append(rec)
        mark = "FAILED" if rec.failure else f"routed={rec.routed_source}"
        print(f"[{i}] {q.id}: {mark}", flush=True)
        if rec.failure:
            print(f"Stopping, rerun later to resume: {rec.failure[:300]}", flush=True)
            break

    judge_base = GeminiLlm(args.judge_model, min_interval_s=60.0 / args.judge_rpm)
    judge = TrackingLlm(judge_base)
    if not args.skip_ragas and not any(r.failure for r in records):
        score_with_ragas(records, judge)

    summary = summarize(records)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "e2e_records.json").write_text(
        json.dumps([asdict(r) for r in records], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.out / "e2e_summary.json").write_text(
        json.dumps({"model": base.model, "judge_model": judge_base.model, **summary}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (args.out / "e2e_report.md").write_text(
        render_report(summary, records, f"{base.model}`, judge `{judge_base.model}"), encoding="utf-8"
    )
    print(json.dumps(summary["overall"], indent=2))
    print("\n".join(_missing_score_warning(summary)))
    if judge.failure:
        print(f"Last judge failure: {judge.failure[:300]}")
    print(f"Chatbot usage {base.usage()}\nJudge usage {judge_base.usage()}\nwrote {args.out}")


if __name__ == "__main__":
    main()
