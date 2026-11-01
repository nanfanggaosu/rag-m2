# End-to-end evaluation

Model: `gemini-3.5-flash`, judge `gemini-3.1-flash-lite`. Questions: 40, incomplete: 0.

| Metric | overall | pdf | sql | both |
|---|---|---|---|---|
| Questions | 40 | 17 | 15 | 8 |
| Router accuracy | 1.000 | 1.000 | 1.000 | 1.000 |
| PDF section hit@5 | 1.000 | 1.000 | n/a | 1.000 |
| PDF page hit@5 | 1.000 | 1.000 | n/a | 1.000 |
| SQL exact match | 0.636 | n/a | 0.500 | 0.875 |
| SQL relaxed match | 1.000 | n/a | 1.000 | 1.000 |
| SQL errors | 0 | 0 | 0 | 0 |
| RAGAS faithfulness | 0.963 | 0.977 | 0.939 | 0.980 |
| RAGAS answer_relevancy | 0.917 | 0.874 | 0.949 | 0.951 |
| RAGAS llm_context_precision_with_reference | 0.662 | 0.676 | 1.000 | 0.000 |
| RAGAS context_recall | 0.985 | 0.966 | 1.000 | 1.000 |
| RAGAS answer_correctness | 0.797 | 0.721 | 0.875 | 0.812 |

## Router confusion (rows: expected, columns: routed)

| expected | pdf | sql | both |
|---|---|---|---|
| pdf | 17 | 0 | 0 |
| sql | 0 | 15 | 0 |
| both | 0 | 0 | 8 |

## Per question

| id | routed | section | SQL | faith | relev | c.prec | c.rec | correct |
|---|---|---|---|---|---|---|---|---|
| p-flying-charge | pdf | hit |  | 0.900 | 0.853 | 1.000 | 1.000 | 0.659 |
| p-attacker-defender | pdf | hit |  | 1.000 | 0.897 | 1.000 | 1.000 | 0.671 |
| p-saving-throw | pdf | hit |  | 1.000 | 0.710 | 0.250 | 0.750 | 0.798 |
| p-embark-disembark | pdf | hit |  | 1.000 | 0.897 | 0.000 | 1.000 | 0.637 |
| p-big-guns | pdf | hit |  | 1.000 | 0.914 | 0.833 | 1.000 | 0.594 |
| p-devastating-wounds | pdf | hit |  | 1.000 | 0.887 | 1.000 | 1.000 | 0.438 |
| p-deadly-demise | pdf | hit |  | 1.000 | 0.834 | 1.000 | 1.000 | 0.738 |
| p-charge-phase | pdf | hit |  | 1.000 | 0.854 | 0.333 | 1.000 | 0.739 |
| p-battle-shock | pdf | hit |  | 0.833 | 0.974 | 0.500 | 1.000 | 0.575 |
| p-fall-back | pdf | hit |  | 1.000 | 0.947 | 1.000 | 1.000 | 0.927 |
| p-wound-roll | pdf | hit |  | 0.875 | 0.864 | 0.000 | 1.000 | 0.609 |
| p-command-points | pdf | hit |  | 1.000 | 0.905 | 1.000 | 1.000 | 0.657 |
| p-aura-abilities | pdf | hit |  | 1.000 | 0.924 | 1.000 | 1.000 | 0.977 |
| p-cover | pdf | hit |  | 1.000 | 0.745 | 0.333 | 1.000 | 0.905 |
| s-e01 | sql |  | exact | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| s-e02 | sql |  | relaxed | 1.000 | 0.920 | 1.000 | 1.000 | 0.986 |
| s-e03 | sql |  | relaxed | 1.000 | 0.841 | 1.000 | 1.000 | 0.997 |
| s-e04 | sql |  | exact | 1.000 | 0.845 | 1.000 | 1.000 | 0.829 |
| s-e05 | sql |  | exact | 1.000 | 1.000 | 1.000 | 1.000 | 0.998 |
| s-e06 | sql |  | exact | 1.000 | 0.939 | 1.000 | 1.000 | 0.983 |
| s-e07 | sql |  | relaxed | 1.000 | 0.998 | 1.000 | 1.000 | 0.722 |
| s-e08 | sql |  | relaxed | 0.867 | 0.961 | 1.000 | 1.000 | 0.872 |
| s-e09 | sql |  | relaxed | 0.857 | 0.914 | 1.000 | 1.000 | 0.404 |
| s-e10 | sql |  | relaxed | 1.000 | 0.961 | 1.000 | 1.000 | 0.854 |
| s-e11 | sql |  | exact | 1.000 | 0.996 | 1.000 | 1.000 | 0.995 |
| s-e12 | sql |  | exact | 1.000 | 0.987 | 1.000 | 1.000 | 0.999 |
| s-e13 | sql |  | relaxed | 1.000 | 1.000 | 1.000 | 1.000 | 0.997 |
| s-e14 | sql |  | exact | 1.000 | 0.966 | 1.000 | 1.000 | 0.974 |
| b-deep-strike-necrons | both | hit | exact | 0.947 | 0.935 | 0.000 | 1.000 | 0.944 |
| b-fights-first-aeldari | both | hit | exact | 0.889 | 0.979 | 0.000 | 1.000 | 0.569 |
| b-stealth-tyranids | both | hit | exact | 1.000 | 0.952 | 0.000 | 1.000 | 0.899 |
| b-invuln-hive-tyrant | both | hit | exact | 1.000 | 0.973 | 0.000 | 1.000 | 0.676 |
| b-leader-overlord | both | hit | exact | 1.000 | 0.883 | 0.000 | 1.000 | 0.934 |
| b-blast-hive-tyrant | both | hit | exact | 1.000 | 0.981 | 0.000 | 1.000 | 0.913 |
| b-embark-trukk | both | hit | relaxed | 1.000 | 0.959 | 0.000 | 1.000 | 0.936 |
| b-fnp-death-guard | both | hit | exact | 1.000 | 0.946 | 0.000 | 1.000 | 0.624 |
| t-grenades | pdf | hit |  | 1.000 | 0.954 | 1.000 | 1.000 | 0.987 |
| t-use-stratagem | pdf | hit |  | 1.000 | 0.901 | 1.000 | 1.000 | 0.820 |
| t-score-points | pdf | hit |  | 1.000 | 0.793 | 0.250 | 0.667 | 0.533 |
| t-toughness-space-marine | sql |  |  | 0.364 | 0.900 | 1.000 | 1.000 | 0.511 |
