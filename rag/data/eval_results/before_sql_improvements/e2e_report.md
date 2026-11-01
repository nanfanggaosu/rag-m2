# End-to-end evaluation

Model: `gemini-3.1-flash-lite`. Questions: 36, incomplete: 0.

| Metric | overall | pdf | sql | both |
|---|---|---|---|---|
| Questions | 36 | 14 | 14 | 8 |
| Router accuracy | 0.972 | 1.000 | 0.929 | 1.000 |
| PDF section hit@5 | 1.000 | 1.000 | n/a | 1.000 |
| PDF page hit@5 | 1.000 | 1.000 | n/a | 1.000 |
| SQL exact match | 0.773 | n/a | 0.714 | 0.875 |
| SQL relaxed match | 0.864 | n/a | 0.857 | 0.875 |
| SQL errors | 0 | 0 | 0 | 0 |
| RAGAS faithfulness | 0.900 | 0.935 | 0.858 | 0.914 |
| RAGAS answer_relevancy | 0.913 | 0.859 | 0.939 | 0.964 |
| RAGAS llm_context_precision_with_reference | 0.623 | 0.661 | 0.929 | 0.021 |
| RAGAS context_recall | 0.951 | 0.982 | 0.929 | 0.938 |
| RAGAS answer_correctness | 0.783 | 0.731 | 0.864 | 0.729 |

## Router confusion (rows: expected, columns: routed)

| expected | pdf | sql | both |
|---|---|---|---|
| pdf | 14 | 0 | 0 |
| sql | 0 | 13 | 1 |
| both | 0 | 0 | 8 |

## Per question

| id | routed | section | SQL | faith | relev | c.prec | c.rec | correct |
|---|---|---|---|---|---|---|---|---|
| p-flying-charge | pdf | hit |  | 1.000 | 0.810 | 1.000 | 1.000 | 0.513 |
| p-attacker-defender | pdf | hit |  | 1.000 | 0.924 | 1.000 | 1.000 | 0.789 |
| p-saving-throw | pdf | hit |  | 1.000 | 0.741 | 0.250 | 0.750 | 0.823 |
| p-embark-disembark | pdf | hit |  | 1.000 | 0.865 | 0.000 | 1.000 | 0.682 |
| p-big-guns | pdf | hit |  | 1.000 | 0.887 | 0.833 | 1.000 | 0.600 |
| p-devastating-wounds | pdf | hit |  | 1.000 | 0.789 | 1.000 | 1.000 | 0.537 |
| p-deadly-demise | pdf | hit |  | 1.000 | 0.834 | 1.000 | 1.000 | 0.924 |
| p-charge-phase | pdf | hit |  | 1.000 | 0.865 | 0.333 | 1.000 | 0.743 |
| p-battle-shock | pdf | hit |  | 0.500 | 0.856 | 0.500 | 1.000 | 0.578 |
| p-fall-back | pdf | hit |  | 1.000 | 0.955 | 1.000 | 1.000 | 0.876 |
| p-wound-roll | pdf | hit |  | 0.583 | 0.848 | 0.000 | 1.000 | 0.878 |
| p-command-points | pdf | hit |  | 1.000 | 0.919 | 1.000 | 1.000 | 0.729 |
| p-aura-abilities | pdf | hit |  | 1.000 | 0.891 | 1.000 | 1.000 | 0.824 |
| p-cover | pdf | hit |  | 1.000 | 0.835 | 0.333 | 1.000 | 0.737 |
| s-e01 | sql |  | exact | 0.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| s-e02 | sql |  | exact | 1.000 | 0.915 | 1.000 | 1.000 | 0.963 |
| s-e03 | sql |  | exact | 1.000 | 0.841 | 1.000 | 1.000 | 0.997 |
| s-e04 | sql |  | exact | 1.000 | 0.853 | 1.000 | 1.000 | 0.983 |
| s-e05 | sql |  | exact | 1.000 | 0.987 | 1.000 | 1.000 | 0.997 |
| s-e06 | sql |  | exact | 1.000 | 0.933 | 1.000 | 1.000 | 0.983 |
| s-e07 | both |  | wrong | 0.625 | 0.863 | 0.000 | 0.000 | 0.240 |
| s-e08 | sql |  | relaxed | 1.000 | 0.927 | 1.000 | 1.000 | 0.984 |
| s-e09 | sql |  | relaxed | 0.889 | 0.937 | 1.000 | 1.000 | 0.353 |
| s-e10 | sql |  | exact | 1.000 | 0.977 | 1.000 | 1.000 | 0.900 |
| s-e11 | sql |  | exact | 1.000 | 0.996 | 1.000 | 1.000 | 0.995 |
| s-e12 | sql |  | exact | 0.500 | 0.956 | 1.000 | 1.000 | 0.732 |
| s-e13 | sql |  | wrong | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| s-e14 | sql |  | exact | 1.000 | 0.966 | 1.000 | 1.000 | 0.975 |
| b-deep-strike-necrons | both | hit | exact | 0.950 | 0.935 | 0.000 | 1.000 | 0.923 |
| b-fights-first-aeldari | both | hit | exact | 1.000 | 0.979 | 0.000 | 1.000 | 0.576 |
| b-stealth-tyranids | both | hit | wrong | 0.800 | 0.942 | 0.000 | 0.500 | 0.334 |
| b-invuln-hive-tyrant | both | hit | exact | 0.833 | 0.972 | 0.167 | 1.000 | 0.572 |
| b-leader-overlord | both | hit | exact | 0.727 | 1.000 | 0.000 | 1.000 | 0.869 |
| b-blast-hive-tyrant | both | hit | exact | 1.000 | 0.978 | 0.000 | 1.000 | 0.922 |
| b-embark-trukk | both | hit | exact | 1.000 | 0.954 | 0.000 | 1.000 | 0.932 |
| b-fnp-death-guard | both | hit | exact | 1.000 | 0.949 | 0.000 | 1.000 | 0.709 |
