# Demo transcript

Reference run of `make demo` on `gemini-3.1-flash-lite`, 2026-11-01. Covers the three router paths
(pdf / sql / both) plus one multi-turn follow-up. Reproduce with:

```bash
GEMINI_MODEL=gemini-3.1-flash-lite make demo
```

The LLM-driven router, retrievers and synthesizer are not deterministic, so the exact wording
may change between runs. Pages, SQL queries, row counts, and the router's choice should match.

---

## 1. PDF rule — `How does deep strike work?`

```
router: pdf  —  Deep Strike is a core rule mechanic described in the rulebook.
pdf: 5 chunks, pages [32, 33, 39, 49]
```

> Deep Strike functions as follows:
>
> * **Deployment:** During the Declare Battle Formations step, if every model in a unit has the Deep Strike ability, you may choose to set that unit up in Reserves instead of on the battlefield (p. 39).
> * **Arrival:** During the Reinforcements step of one of your Movement phases, you can set up a unit that is in Reserves due to the Deep Strike ability anywhere on the battlefield, provided the unit is more than 9" horizontally away from all enemy models (p. 39).

Top-ranked chunk is page 39 (DEEP STRIKE section). Section hit@5 on this question is confirmed
in `rag/data/eval_results/e2e_report.md`.

## 2. SQL lookup — `How many datasheets does the Orks faction have?`

```
router: sql  —  A count query against the datasheets table filtered by faction.
sql: 1 rows of 1
```

```sql
SELECT count(*) AS n_datasheets
FROM datasheets d JOIN factions f ON f.Id = d.factionId
WHERE f.name = 'Orks' AND d.virtual = 'false'
```

> The Orks faction has 88 datasheets.

The query joins `datasheets ↔ factions` and filters out virtual sheets (per the data
dictionary). Exact match against the gold query in `questions_e2e.jsonl`.

## 3. Both — `What is Deep Strike, and which Necrons units have it?`

```
router: both  —  Needs the Deep Strike rule definition (PDF) and a list of
                 units filtered by that keyword (SQL).
  split pdf: What is the Deep Strike rule?
  split sql: Which Necrons units have the Deep Strike keyword?
pdf: 5 chunks, pages [16, 32, 39, 41, 60]
sql: 14 rows of 14
```

```sql
SELECT DISTINCT d.name
FROM datasheets d
  JOIN factions f ON f.Id = d.factionId
  JOIN datasheets_abilities da ON da.DatasheetId = d.Id
  JOIN abilities a ON a.Id = da.abilityId
WHERE f.name = 'Necrons' AND a.name LIKE 'Deep Strike' AND d.virtual = 'false'
```

> Deep Strike is a special ability that allows a unit to be set up in Reserves during the Declare Battle Formations step instead of on the battlefield. During the Reinforcements step of any of your Movement phases, these units can be set up anywhere on the battlefield, provided they are more than 9" horizontally away from all enemy models (Core Rules, p. 39). Units arriving via Deep Strike count as having made a Normal move and cannot move further that phase, but may otherwise act normally (Core Rules, p. 16).
>
> The following Necron units possess the Deep Strike ability:
> 1. Deathmarks
> 2. Triarch Praetorians
> 3. C’tan Shard of the Nightbringer
> 4. C’tan Shard of the Deceiver
> 5. Night Scythe
> 6. Monolith
> 7. Transcendent C’tan
> 8. Obelisk
> 9. Canoptek Tomb Stalker
> 10. Canoptek Tomb Sentinel
> 11. Hexmark Destroyer
> 12. C’tan Shard of the Void Dragon
> 13. Ophydian Destroyers
> 14. Nekrosor Ammentar

The router split the question into one PDF sub-query and one SQL sub-query — each goes to the
right retriever, then the synthesizer stitches them.

## 4. Multi-turn follow-up — `And which of them have the FLY keyword too?`

Carries history from steps 1–3. The contextualizer rewrites the follow-up into a standalone
question before the router sees it; then it's a straight SQL filter.

```
router: sql  —  This is a filtering query across the datasheets table to find
                units matching multiple keyword criteria.
sql: 8 rows of 8
```

```sql
SELECT DISTINCT d.name
FROM datasheets d
  JOIN datasheets_keywords dk ON d.Id = dk.DatasheetId
  JOIN datasheets_abilities da ON d.Id = da.DatasheetId
  JOIN abilities a ON da.abilityId = a.Id
  JOIN factions f ON d.factionId = f.Id
WHERE f.name = 'Necrons' AND a.name = 'Deep Strike' AND dk.keyword = 'Fly'
  AND d.virtual = 'false'
```

> The following Necron units possess both the Deep Strike ability and the FLY keyword:
> 1. Triarch Praetorians
> 2. C’tan Shard of the Nightbringer
> 3. C’tan Shard of the Deceiver
> 4. Night Scythe
> 5. Monolith
> 6. Transcendent C’tan
> 7. Obelisk
> 8. C’tan Shard of the Void Dragon

The pronoun "them" is resolved against the prior turn (Necron Deep-Strike units), and the router
goes straight to SQL instead of asking the PDF again.
