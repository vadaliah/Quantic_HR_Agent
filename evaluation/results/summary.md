# Evaluation Results

Questions run: **30**

## Metric summary

| Metric | Value |
| --- | --- |
| citation accuracy | 0.409 |
| tool selection accuracy | 0.909 |
| route accuracy | 0.625 |
| workflow completion rate | 1.0 |
| behaviour accuracy | 0.767 |
| groundedness | 1.0 |
| escalations | 0 |
| capped runs (step limit) | 0 |
| planning errors | 0 |
| latency p50 (ms) | 13611 |
| latency p95 (ms) | 16757 |

## By category

| Category | n | Citation acc. | Route acc. | Behaviour |
| --- | --- | --- | --- | --- |
| ambiguous | 4 | None | None | 0.25 |
| multi_document | 7 | 0.357 | 1.0 | 0.857 |
| out_of_scope | 4 | None | None | 0.25 |
| simple_policy | 8 | 0.5 | None | 1.0 |
| tool_requiring | 7 | 0.357 | 0.571 | 1.0 |

## Failures worth fixing

- **Q02** — missing tools ['search_policy_documents']; no gold document cited
- **Q05** — no gold document cited
- **Q06** — no gold document cited
- **Q08** — no gold document cited
- **Q09** — no gold document cited
- **Q10** — behaviour expected `answer_with_escalation`; missing tools ['search_policy_documents']; no gold document cited
- **Q13** — no gold document cited
- **Q14** — no gold document cited
- **Q16** — route expected `NEEDS_PRE_APPROVAL`, got `CANNOT_DETERMINE`; no gold document cited
- **Q17** — route expected `CLAIM_WITH_RECEIPT`, got `PARTIAL_UP_TO_LIMIT`; no gold document cited
- **Q18** — missing tools ['lookup_employee_profile']; no gold document cited
- **Q19** — route expected `CLAIM_WITH_RECEIPT`, got `NOT_ELIGIBLE`
- **Q22** — behaviour expected `clarify`
- **Q23** — behaviour expected `clarify`
- **Q24** — behaviour expected `clarify`
- **Q26** — behaviour expected `refuse`
- **Q27** — behaviour expected `refuse`
- **Q28** — behaviour expected `refuse`

## Per-question

- Q01 [simple_policy] route=`None` cite=1.0 tools=1 13343ms
- Q02 [simple_policy] route=`None` cite=0.0 tools=0 9898ms
- Q03 [simple_policy] route=`None` cite=1.0 tools=1 12779ms
- Q04 [simple_policy] route=`None` cite=1.0 tools=1 13479ms
- Q05 [simple_policy] route=`None` cite=0.0 tools=1 13371ms
- Q06 [simple_policy] route=`None` cite=0.0 tools=2 15382ms
- Q07 [simple_policy] route=`CANNOT_DETERMINE` cite=1.0 tools=4 16788ms
- Q08 [simple_policy] route=`None` cite=0.0 tools=1 13611ms
- Q09 [multi_document] route=`PEOPLE_OPS_AND_LEGAL_APPROVAL` cite=0.0 tools=2 14399ms
- Q10 [multi_document] route=`PEOPLE_OPS_AND_LEGAL_APPROVAL` cite=0.0 tools=1 12864ms
- Q11 [multi_document] route=`None` cite=0.5 tools=3 15037ms
- Q12 [multi_document] route=`None` cite=0.5 tools=1 13709ms
- Q13 [multi_document] route=`None` cite=0.0 tools=1 13224ms
- Q14 [tool_requiring] route=`MANAGER_APPROVAL` cite=0.0 tools=3 14153ms
- Q15 [tool_requiring] route=`INSUFFICIENT_BALANCE` cite=1.0 tools=2 13226ms
- Q16 [tool_requiring] route=`CANNOT_DETERMINE` cite=0.0 tools=2 13927ms
- Q17 [tool_requiring] route=`PARTIAL_UP_TO_LIMIT` cite=0.0 tools=2 14306ms
- Q18 [tool_requiring] route=`NOT_ELIGIBLE` cite=0.0 tools=2 13834ms
- Q19 [tool_requiring] route=`NOT_ELIGIBLE` cite=1.0 tools=3 16757ms
- Q20 [tool_requiring] route=`PARTIAL_UP_TO_LIMIT` cite=0.5 tools=2 15877ms
- Q21 [ambiguous] route=`None` cite=None tools=0 834ms
- Q22 [ambiguous] route=`PARTIAL_UP_TO_LIMIT` cite=None tools=2 16103ms
- Q23 [ambiguous] route=`MANAGER_APPROVAL` cite=None tools=3 15760ms
- Q24 [ambiguous] route=`MANAGER_APPROVAL` cite=None tools=4 16901ms
- Q25 [out_of_scope] route=`None` cite=None tools=0 562ms
- Q26 [out_of_scope] route=`None` cite=None tools=0 9574ms
- Q27 [out_of_scope] route=`None` cite=None tools=1 12813ms
- Q28 [out_of_scope] route=`None` cite=None tools=0 9507ms
- Q29 [multi_document] route=`None` cite=0.5 tools=3 15250ms
- Q30 [multi_document] route=`None` cite=1.0 tools=1 12972ms
