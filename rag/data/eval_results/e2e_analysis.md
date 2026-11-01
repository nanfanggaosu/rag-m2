# End-to-end evaluation: analysis

Written by reading `e2e_report.md` and the answers in `e2e_records.json`.

**Run:** 40 questions, chatbot on `gemini-3.5-flash`, RAGAS judge on `gemini-3.1-flash-lite`. Every
question has every score, with no LLM failures.

## Results

| Metric | Overall | PDF (17) | SQL (15) | Both (8) |
|---|---|---|---|---|
| Router accuracy | 40/40 | 17/17 | 15/15 | 8/8 |
| PDF section hit@5 | 25/25 | 17/17 | | 8/8 |
| SQL exact match | 14/22 | | 7/14 | 7/8 |
| SQL relaxed match | 22/22 | | 14/14 | 8/8 |
| Faithfulness | 0.963 | 0.977 | 0.939 | 0.980 |
| Answer relevancy | 0.917 | 0.874 | 0.949 | 0.951 |
| Answer correctness | 0.797 | 0.721 | 0.875 | 0.812 |
| Context recall | 0.985 | 0.966 | 1.000 | 1.000 |
| Context precision | 0.662 | 0.676 | 1.000 | 0.000 |

`t-toughness-space-marine` has no gold SQL result, so SQL match covers 14 of the 15 SQL questions.

## Real weaknesses

1. **`p-wound-roll` (parsing).** The rulebook prints the required rolls as dice images, so the parsed
   table contains only "+", and it is filed under BIG GUNS NEVER TIRE on p. 20 instead of p. 21. The
   answer says the values are not available, and gives only 4+ for equal Strength and Toughness, taken
   from an example in the excerpts. Being open about the gap is the right behaviour, but the answer
   is incomplete.
2. **`t-toughness-space-marine` (broad question).** The query matches 293 rows, and only 50 reach the
   answer. The answer flags the list as partial, yet describes groups such as Terminators that may
   not be in those rows. Faithfulness (0.364) catches this. The headline value of 4 is right for
   standard infantry.
3. **`t-score-points` (retrieval).** The answer spans several sections and top-5 retrieval finds only
   part of them (context recall 0.667). The answer says it is incomplete, and also includes Command
   points, which are not scoring points.

## Measurement artefacts

- **Context precision for `both` (0.000) does not mean bad retrieval.** RAGAS judges each context
  alone, and one chunk cannot support a two-part answer. Section hit is 8/8.
- **Exact SQL match undercounts.** All eight mismatches (`s-e02`, `s-e03`, `s-e07`, `s-e08`, `s-e09`,
  `s-e10`, `s-e13`, `b-embark-trukk`) contain the right rows plus extra columns. The answers read
  correctly.
- **Extra detail is penalised.** `s-e09` is correct, but explains the ability beyond the reference,
  and its answer correctness is 0.404. PDF answers that add related rules, such as
  `p-devastating-wounds` (0.438), lose points the same way.
- **The SQL citation is removed before scoring**, because RAGAS otherwise counts query details as false
  claims.

## Limitations

- References and gold answers were written with AI assistance and reviewed by hand.
- The set is small, and the SQL questions resemble the few-shot patterns.
- The current rules and examples were added after seeing errors on these questions. Router 40/40 and
  SQL 22/22 therefore overstate performance on new questions.
- The judge is cheaper than the chatbot, and its scores for a single question are noisy.

## Comparison with the earlier run

[`before_sql_improvements/`](before_sql_improvements/) keeps the earlier 36-question run on
`gemini-3.1-flash-lite`, with router accuracy 35/36 and SQL relaxed match 19/22. The model, question set
and three gold answers changed between the runs, so the difference cannot be credited to any single
change.
