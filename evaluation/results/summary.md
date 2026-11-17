# Evaluation Results

Questions run: **30**

## Metric summary

| Metric | Value |
| --- | --- |
| citation accuracy | 0.386 |
| tool selection accuracy | 0.932 |
| route accuracy | 0.625 |
| workflow completion rate | 1.0 |
| behaviour accuracy | 0.767 |
| groundedness | None |
| escalations | 0 |
| capped runs (step limit) | 0 |
| planning errors | 0 |
| latency p50 (ms) | 13665 |
| latency p95 (ms) | 15358 |

## By category

| Category | n | Citation acc. | Route acc. | Behaviour |
| --- | --- | --- | --- | --- |
| ambiguous | 4 | None | None | 0.25 |
| multi_document | 7 | 0.286 | 1.0 | 0.857 |
| out_of_scope | 4 | None | None | 0.25 |
| simple_policy | 8 | 0.625 | None | 1.0 |
| tool_requiring | 7 | 0.214 | 0.571 | 1.0 |

## Failures worth fixing

- **Q02** — missing tools ['search_policy_documents']; no gold document cited
- **Q06** — no gold document cited
- **Q08** — no gold document cited
- **Q09** — no gold document cited
- **Q10** — behaviour expected `answer_with_escalation`; no gold document cited
- **Q11** — no gold document cited
- **Q13** — no gold document cited
- **Q14** — no gold document cited
- **Q15** — no gold document cited
- **Q16** — route expected `NEEDS_PRE_APPROVAL`, got `CANNOT_DETERMINE`; no gold document cited
- **Q17** — route expected `CLAIM_WITH_RECEIPT`, got `CANNOT_DETERMINE`; no gold document cited
- **Q18** — missing tools ['lookup_employee_profile']; no gold document cited
- **Q19** — route expected `CLAIM_WITH_RECEIPT`, got `NOT_ELIGIBLE`
- **Q22** — behaviour expected `clarify`
- **Q23** — behaviour expected `clarify`
- **Q24** — behaviour expected `clarify`
- **Q26** — behaviour expected `refuse`
- **Q27** — behaviour expected `refuse`
- **Q28** — behaviour expected `refuse`

## Per-question

- Q01 [simple_policy] route=`None` cite=1.0 tools=1 13231ms
- Q02 [simple_policy] route=`None` cite=0.0 tools=0 9313ms
- Q03 [simple_policy] route=`None` cite=1.0 tools=1 13046ms
- Q04 [simple_policy] route=`None` cite=1.0 tools=1 12437ms
- Q05 [simple_policy] route=`None` cite=1.0 tools=1 13268ms
- Q06 [simple_policy] route=`None` cite=0.0 tools=1 13232ms
- Q07 [simple_policy] route=`None` cite=1.0 tools=2 14678ms
- Q08 [simple_policy] route=`None` cite=0.0 tools=1 12540ms
- Q09 [multi_document] route=`PEOPLE_OPS_AND_LEGAL_APPROVAL` cite=0.0 tools=2 14717ms
- Q10 [multi_document] route=`PEOPLE_OPS_AND_LEGAL_APPROVAL` cite=0.0 tools=2 14673ms
- Q11 [multi_document] route=`None` cite=0.0 tools=2 14827ms
- Q12 [multi_document] route=`None` cite=0.5 tools=1 13262ms
- Q13 [multi_document] route=`None` cite=0.0 tools=1 13665ms
- Q14 [tool_requiring] route=`MANAGER_APPROVAL` cite=0.0 tools=3 15358ms
- Q15 [tool_requiring] route=`INSUFFICIENT_BALANCE` cite=0.0 tools=3 15153ms
- Q16 [tool_requiring] route=`CANNOT_DETERMINE` cite=0.0 tools=2 14115ms
- Q17 [tool_requiring] route=`CANNOT_DETERMINE` cite=0.0 tools=2 14930ms
- Q18 [tool_requiring] route=`NOT_ELIGIBLE` cite=0.0 tools=2 13807ms
- Q19 [tool_requiring] route=`NOT_ELIGIBLE` cite=1.0 tools=2 14183ms
- Q20 [tool_requiring] route=`PARTIAL_UP_TO_LIMIT` cite=0.5 tools=2 14655ms
- Q21 [ambiguous] route=`None` cite=None tools=0 809ms
- Q22 [ambiguous] route=`PARTIAL_UP_TO_LIMIT` cite=None tools=2 15506ms
- Q23 [ambiguous] route=`MANAGER_APPROVAL` cite=None tools=4 16924ms
- Q24 [ambiguous] route=`MANAGER_APPROVAL` cite=None tools=2 14320ms
- Q25 [out_of_scope] route=`None` cite=None tools=0 455ms
- Q26 [out_of_scope] route=`None` cite=None tools=0 9200ms
- Q27 [out_of_scope] route=`None` cite=None tools=1 13171ms
- Q28 [out_of_scope] route=`None` cite=None tools=0 10203ms
- Q29 [multi_document] route=`None` cite=0.5 tools=2 14800ms
- Q30 [multi_document] route=`None` cite=1.0 tools=1 13349ms
