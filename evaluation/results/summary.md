# Evaluation Results

Questions run: **30**

## Metric summary

| Metric | Value |
| --- | --- |
| citation accuracy | 0.0 |
| tool selection accuracy | 0.886 |
| route accuracy | 0.0 |
| workflow completion rate | 0.933 |
| behaviour accuracy | 0.767 |
| groundedness | 1.0 |
| escalations | 0 |
| capped runs (step limit) | 3 |
| planning errors | 2 |
| latency p50 (ms) | 14126 |
| latency p95 (ms) | 26606 |

## By category

| Category | n | Citation acc. | Route acc. | Behaviour |
| --- | --- | --- | --- | --- |
| ambiguous | 4 | None | None | 0.25 |
| multi_document | 7 | 0.0 | 0.0 | 0.857 |
| out_of_scope | 4 | None | None | 0.25 |
| simple_policy | 8 | 0.0 | None | 1.0 |
| tool_requiring | 7 | 0.0 | 0.0 | 1.0 |

## Failures worth fixing

- **Q01** — no gold document cited
- **Q02** — no gold document cited
- **Q03** — no gold document cited
- **Q04** — no gold document cited
- **Q05** — no gold document cited
- **Q06** — no gold document cited
- **Q07** — no gold document cited
- **Q08** — no gold document cited
- **Q09** — route expected `PEOPLE_OPS_AND_LEGAL_APPROVAL`, got `None`; missing tools ['search_policy_documents']; no gold document cited
- **Q10** — behaviour expected `answer_with_escalation`; no gold document cited
- **Q11** — missing tools ['lookup_benefits_status']; no gold document cited
- **Q12** — no gold document cited
- **Q13** — no gold document cited
- **Q14** — route expected `MANAGER_APPROVAL`, got `INSUFFICIENT`; no gold document cited
- **Q15** — route expected `INSUFFICIENT_BALANCE`, got `INSUFFICIENT`; no gold document cited
- **Q16** — route expected `NEEDS_PRE_APPROVAL`, got `None`; missing tools ['check_policy_compliance']; no gold document cited
- **Q17** — route expected `CLAIM_WITH_RECEIPT`, got `INSUFFICIENT`; no gold document cited
- **Q18** — route expected `NOT_ELIGIBLE`, got `None`; no gold document cited
- **Q19** — route expected `CLAIM_WITH_RECEIPT`, got `None`; missing tools ['check_policy_compliance']; no gold document cited; planning error
- **Q20** — route expected `PARTIAL_UP_TO_LIMIT`, got `None`; missing tools ['check_policy_compliance']; no gold document cited; planning error
- **Q22** — behaviour expected `clarify`
- **Q23** — behaviour expected `clarify`
- **Q24** — behaviour expected `clarify`
- **Q26** — behaviour expected `refuse`
- **Q27** — behaviour expected `refuse`
- **Q28** — behaviour expected `refuse`
- **Q29** — no gold document cited
- **Q30** — no gold document cited

## Per-question

- Q01 [simple_policy] route=`None` cite=0.0 tools=1 11976ms
- Q02 [simple_policy] route=`None` cite=0.0 tools=4 17196ms
- Q03 [simple_policy] route=`None` cite=0.0 tools=1 9706ms
- Q04 [simple_policy] route=`None` cite=0.0 tools=1 9122ms
- Q05 [simple_policy] route=`CLAIM_WITH_RECEIPT` cite=0.0 tools=3 16181ms
- Q06 [simple_policy] route=`None` cite=0.0 tools=3 16057ms
- Q07 [simple_policy] route=`None` cite=0.0 tools=2 12033ms
- Q08 [simple_policy] route=`None` cite=0.0 tools=1 10128ms
- Q09 [multi_document] route=`None` cite=0.0 tools=3 9936ms
- Q10 [multi_document] route=`None` cite=0.0 tools=3 14681ms
- Q11 [multi_document] route=`None` cite=0.0 tools=3 13443ms
- Q12 [multi_document] route=`None` cite=0.0 tools=7 26606ms
- Q13 [multi_document] route=`CLAIM_WITH_RECEIPT` cite=0.0 tools=5 28824ms
- Q14 [tool_requiring] route=`INSUFFICIENT` cite=0.0 tools=3 14018ms
- Q15 [tool_requiring] route=`INSUFFICIENT` cite=0.0 tools=4 16957ms
- Q16 [tool_requiring] route=`None` cite=0.0 tools=2 15021ms
- Q17 [tool_requiring] route=`INSUFFICIENT` cite=0.0 tools=3 23720ms
- Q18 [tool_requiring] route=`None` cite=0.0 tools=2 10800ms
- Q19 [tool_requiring] route=`None` cite=0.0 tools=1 9267ms
- Q20 [tool_requiring] route=`None` cite=0.0 tools=3 15749ms
- Q21 [ambiguous] route=`None` cite=None tools=0 941ms
- Q22 [ambiguous] route=`None` cite=None tools=3 15765ms
- Q23 [ambiguous] route=`None` cite=None tools=6 22938ms
- Q24 [ambiguous] route=`None` cite=None tools=4 14746ms
- Q25 [out_of_scope] route=`None` cite=None tools=0 917ms
- Q26 [out_of_scope] route=`None` cite=None tools=0 3173ms
- Q27 [out_of_scope] route=`None` cite=None tools=4 19457ms
- Q28 [out_of_scope] route=`None` cite=None tools=2 14126ms
- Q29 [multi_document] route=`None` cite=0.0 tools=7 27289ms
- Q30 [multi_document] route=`None` cite=0.0 tools=2 13361ms
