# End-to-end evaluation: analysis

Written by hand from `e2e_report.md`, `e2e_records.json` and the cached RAGAS verdicts.

**Status: complete.** All 36 questions have every score, with no LLM failures in the final run.

## Setup

- 36 questions: 14 PDF, 14 SQL, 8 both. None appears in a router or SQL few-shot prompt, which
  a test enforces. The 6 PDF questions that are router examples were removed.
- Chatbot and RAGAS judge both ran on `gemini-3.1-flash-lite`, because the free tier of
  `gemini-3.5-flash` allows about 20 requests per day. One full run needs about 410 calls.
- Earlier SQL results (10/14 exact) came from `gemini-3.5-flash`, so the two are not directly
  comparable.

## Results

| Metric | Overall | PDF (14) | SQL (14) | Both (8) |
|---|---|---|---|---|
| Router accuracy | 35/36 | 14/14 | 13/14 | 8/8 |
| PDF section hit@5 | 22/22 | 14/14 | | 8/8 |
| SQL exact match | 17/22 | | 10/14 | 7/8 |
| SQL relaxed match | 19/22 | | 12/14 | 7/8 |
| Context recall | 0.951 | 0.982 | 0.929 | 0.938 |
| Context precision | 0.623 | 0.661 | 0.929 | 0.021 (see artefacts) |

Metrics that depend on the answer, scored without and with the SQL citation:

| Metric | Scoring | Overall | PDF | SQL | Both |
|---|---|---|---|---|---|
| Faithfulness | citation removed (final) | 0.900 | 0.935 | 0.858 | 0.914 |
| Faithfulness | first run, with citation | 0.955 | 0.935 | 0.973 | 0.960 |
| Answer relevancy | citation removed (final) | 0.913 | 0.859 | 0.939 | 0.964 |
| Answer relevancy | first run, with citation | 0.913 | 0.859 | 0.943 | 0.954 |
| Answer correctness | citation removed (final) | 0.783 | 0.731 | 0.864 | 0.729 |
| Answer correctness | first run, with citation | 0.721 | 0.731 | 0.694 | 0.753 |

The first run is kept in `first_run/`. PDF answers have no SQL citation, so their scores are
identical in both. Removing the citation raised SQL correctness but lowered faithfulness, because
statements about the query are easy for the judge to confirm and had been raising that score.

## Real failures

1. **`s-e07` (router and answer).** "Which stratagems can Termagants use in the Fight phase?" was
   routed to `both`. The SQL query lost the Fight phase filter and returned all 36 of the unit's
   stratagems. The answer names only Counter-Offensive and wrongly calls the list partial,
   although no rows were cut off.
2. **`b-stealth-tyranids` (SQL).** The query looked for Stealth in `datasheets_keywords`, but it
   is an ability, so it returned nothing and the retry accepted the empty result. The answer
   honestly says no units were found, while 7 exist. No few-shot example shows the pattern
   "units with ability X".
3. **`p-wound-roll` (parsing).** The rulebook prints the required rolls as dice images, so the
   parsed table contains only "+", and it is filed under BIG GUNS NEVER TIRE on p. 20 instead of
   p. 21. The answer gives the right values (2+ to 6+) from the model's own knowledge and cites
   the wrong page. Faithfulness (0.583) caught this correctly.

## Measurement artefacts

- **Context precision for `both` (0.021) does not mean bad retrieval.** RAGAS judges each context
  alone, and one chunk cannot support a two-part answer, so the sampled verdicts are "only partly
  useful" = 0. Section hit is 8/8. Two-part PDF questions such as `p-embark-disembark` suffer the
  same way.
- **Answer correctness with the SQL citation was too low.** Query details counted as false
  claims: `s-e01` scored 0.587 although its sentence matched the reference word for word. It
  scores 1.000 once the citation is removed. All answers are now scored without it.
- **Extra detail is penalised.** `s-e09` is correct but also explains the ability, so it scores
  0.353.
- **The judge is noisy.** `s-e01` has faithfulness 0.000 after rescoring because the judge
  separates "57 non-virtual datasheets" from "57 datasheets". It accepted the same sentence in the
  first run. `s-e12` (0.500) split "134 units can have a Lascannon" into a separate claim that the
  game has 134 units. `p-battle-shock` lost points for how a page citation was phrased. Treat
  single-question scores as prompts to read the answer, not as verdicts.
- **Exact SQL match undercounts.** `s-e13` is marked wrong only because its gold query also
  returns the unit name; the answer (4+) is right. `s-e08` and `s-e09` return extra columns and are
  right. By reading these cases, 20 of 22 queries returned the right data; the other 2 are
  failures 1 and 2 above.

## Limitations

- All references, SQL gold answers and the 8 `both` questions were written with AI assistance
  and have **not had a human review**. `s-e13` shows that a gold answer can be too strict.
- The evaluation is small, and the SQL questions resemble the few-shot patterns, so results are
  likely optimistic.
- The judge is the same model as the chatbot, and a cheap one.
- The scoring change and these conclusions came after seeing the first results. Report both runs.
  No gold answer or prompt was changed after seeing them.

## Suggested improvements

Each one changes the system, so it needs a new run and fresh questions to measure fairly.

1. Require `sql_question` to keep every filter from the original question.
2. Add a few-shot example for "units with ability X".
3. Add the wound table digits to the chunk and file it under p. 21.
4. Hand-review the gold answers, starting with `s-e13`.
