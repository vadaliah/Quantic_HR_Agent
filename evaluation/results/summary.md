# Evaluation Results

Questions run: **25**

## Metric summary

| Metric | Value |
| --- | --- |
| citation accuracy | 0.492 |
| tool selection accuracy | 0.675 |
| route accuracy | 0.714 |
| workflow completion rate | 1.0 |
| behaviour accuracy | 0.92 |
| groundedness | 1.0 |
| escalations | 2 |
| capped runs (step limit) | 1 |
| planning errors | 0 |
| latency p50 (ms) | 7026 |
| latency p95 (ms) | 11605 |

## By category

| Category | n | Citation acc. | Route acc. | Behaviour |
| --- | --- | --- | --- | --- |
| ambiguous | 3 | 0.333 | None | 0.333 |
| multi_document | 5 | 0.7 | 1.0 | 1.0 |
| out_of_scope | 3 | None | None | 1.0 |
| simple_policy | 8 | 0.5 | None | 1.0 |
| tool_requiring | 6 | 0.333 | 0.6 | 1.0 |

## Failures worth fixing

- **Q01** — missing tools ['search_policy_documents']; no gold document cited
- **Q02** — missing tools ['search_policy_documents']; no gold document cited
- **Q06** — missing tools ['search_policy_documents']; no gold document cited
- **Q07** — missing tools ['search_policy_documents']; no gold document cited
- **Q11** — no gold document cited
- **Q14** — route expected `manager approval required`, got `None`; missing tools ['check_policy_compliance']; no gold document cited
- **Q15** — no gold document cited
- **Q16** — route expected `NEEDS_PRE_APPROVAL`, got `None`; missing tools ['check_policy_compliance']; no gold document cited
- **Q19** — missing tools ['check_pto_balance']; no gold document cited
- **Q20** — behaviour expected `clarify`
- **Q22** — behaviour expected `clarify`

## Per-question

- Q01 [simple_policy] route=`None` cite=0.0 tools=0 293ms
- Q02 [simple_policy] route=`None` cite=0.0 tools=0 298ms
- Q03 [simple_policy] route=`None` cite=1.0 tools=2 8392ms
- Q04 [simple_policy] route=`None` cite=1.0 tools=1 7593ms
- Q05 [simple_policy] route=`None` cite=1.0 tools=6 13904ms
- Q06 [simple_policy] route=`None` cite=0.0 tools=0 145ms
- Q07 [simple_policy] route=`None` cite=0.0 tools=0 150ms
- Q08 [simple_policy] route=`None` cite=1.0 tools=2 9220ms
- Q09 [multi_document] route=`PEOPLE_OPS_AND_LEGAL` cite=1.0 tools=4 11605ms
- Q10 [multi_document] route=`DECLINED` cite=1.0 tools=4 10088ms
- Q11 [multi_document] route=`NOT_ELIGIBLE` cite=0.0 tools=1 4553ms
- Q12 [multi_document] route=`None` cite=0.5 tools=2 7732ms
- Q13 [multi_document] route=`INSUFFICIENT` cite=1.0 tools=3 9189ms
- Q14 [tool_requiring] route=`None` cite=0.0 tools=2 7340ms
- Q15 [tool_requiring] route=`INSUFFICIENT` cite=0.0 tools=3 9507ms
- Q16 [tool_requiring] route=`None` cite=0.0 tools=1 5409ms
- Q17 [tool_requiring] route=`CLAIM_WITH_RECEIPT` cite=1.0 tools=2 7026ms
- Q18 [tool_requiring] route=`INELIGIBLE` cite=1.0 tools=3 7515ms
- Q19 [tool_requiring] route=`None` cite=0.0 tools=0 229ms
- Q20 [ambiguous] route=`INSUFFICIENT` cite=None tools=5 11006ms
- Q21 [ambiguous] route=`None` cite=0.333 tools=2 7242ms
- Q22 [ambiguous] route=`None` cite=None tools=0 2759ms
- Q23 [out_of_scope] route=`None` cite=None tools=0 210ms
- Q24 [out_of_scope] route=`None` cite=None tools=0 294ms
- Q25 [out_of_scope] route=`None` cite=None tools=0 546ms
