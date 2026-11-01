# Demo transcript

Reference run of `make demo` on `gemini-3.1-flash-lite`, 2026-11-01. Covers the three router paths
(pdf / sql / both) plus one multi-turn follow-up. Reproduce with:

```bash
GEMINI_MODEL=gemini-3.1-flash-lite make demo
```

For the four sanity questions the grader said he would ask (Lecture 1 PDF, p. 42), see the
["Teacher sanity questions"](#teacher-sanity-questions-make-sanity) section at the bottom.
Reproduce with `make sanity`.

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

---

## Teacher sanity questions (`make sanity`)

Four questions the grader explicitly listed in the Lecture 1 PDF (p. 42) as what the chatbot
should be able to answer. Run on `gemini-3.1-flash-lite`, 2026-11-01.

### 1. "What is the rule for grenades?"

```
router: pdf  —  Grenades are a specific stratagem/action rule defined in the core rules.
pdf: 5 chunks, pages [24, 28, 42]
```

> The rules for the Grenades Stratagem are as follows:
>
> * **When:** Your Shooting phase (p. 42).
> * **Target:** One Grenades unit from your army that is not within Engagement Range of any enemy units and has not been selected to shoot this phase (p. 42).
> * **Effect:** Select one enemy unit that is not within Engagement Range of any units from your army and is within 8" of and visible to your Grenades unit. Roll six D6: for each 4+, that enemy unit suffers 1 mortal wound (p. 42).

### 2. "How can I use a stratagem?"

```
router: pdf  —  The process of using a stratagem is a core game mechanic defined in the rules.
pdf: 5 chunks, pages [11, 41, 42]
```

> To use a Stratagem, you must pay the Command Point (CP) cost specified on that Stratagem (p. 41). You can spend CP during the battle to use them (p. 11, p. 41).
>
> When using a Stratagem, you must adhere to the following rules:
> * **Cost:** You must have enough CP to pay the amount listed on the Stratagem; if you do not, you cannot use it (p. 41).
> * **Frequency:** You can use the same Stratagem multiple times during a battle, but you cannot use the same Stratagem more than once in the same phase (p. 41).
> * **Timing:** You must use the Stratagem at the time specified in its rules (e.g., the "WHEN" section of the Stratagem) (p. 42).

### 3. "What are the different ways to score points?"

```
router: pdf  —  Scoring points is a core mechanic defined in the mission rules and core rulebook.
pdf: 5 chunks, pages [11, 55, 57, 59]
```

> According to the Core Rules, the ways to score points are determined by the specific mission being played:
>
> * **Mission Objectives:** Each mission will tell you what you need to do in order to win the game (p. 57).
> * **Progressive Objectives:** In missions using the "Capture and Control" rules, the player whose turn it is scores 1 Victory point (VP) for each objective marker they control at the end of their Command phase, starting from the second battle round (to a maximum of 3VP per turn) (p. 59).
>
> The provided excerpts do not list any other specific methods for scoring points. Note that "points" used for building an army (p. 55) and "Command points" (p. 11) are distinct from Victory points used to determine the victor.

The answer explicitly distinguishes army-building points, Command points, and Victory points — the
same three senses of "points" in the rulebook.

### 4. "What is the toughness of a space marine?"

```
router: sql  —  The user is asking for a specific stat (toughness) of a unit (Space Marine), which
                requires a lookup in the datasheets.
sql: 50 rows of 287
```

```sql
SELECT DISTINCT dm.name, dm.t
FROM datasheets d
  JOIN factions f ON d.factionId = f.Id
  JOIN datasheets_models dm ON d.Id = dm.DatasheetId
WHERE f.name = 'Space Marines'
```

> The toughness of a Space Marine varies depending on the specific unit, armor, and equipment. Standard infantry (such as Tactical Squads, Captains, or Infiltrators) typically have a Toughness of 4, while units in Terminator armor or on bikes have a Toughness of 5. Heavier units, such as those in Gravis armor (like Eradicators) or specialized support units, have a Toughness of 6. Vehicles and Dreadnoughts have significantly higher values, ranging from 7 to 12.
>
> The list provided is partial, as there are 287 total rows in the database for the Space Marines faction.

The router correctly chose SQL (datasheet stats, not a rules question); the answer honestly flags
that the 50-row limit cut off the full list.

---

## Translation (`/zh`, `/fr`, `/en`)

A `/zh`, `/fr` or `/en` command in the chat translates the previous answer into that language
while keeping `(p. XX)` citations and any trailing SQL `Source:` block unchanged. Lecture 1's
PPT (p. 42) listed translation as a nice-to-have for the chat interface. Sample `/zh` after
"How does deep strike work?":

> "深层打击"（Deep Strike）的功能如下：
>
> * **部署：** 在"宣布战斗编队"步骤中，如果一个单位中的所有模型都拥有"深层打击"能力，你可以选择将该单位设置在预备队中，而不是战场上（p. 39）。
> * **抵达：** 在你任意一个移动阶段的"增援"步骤中，你可以将因"深层打击"能力而处于预备队中的单位设置在战场上的任意位置，前提是该单位距离所有敌方模型水平距离超过9英寸（p. 39）。
