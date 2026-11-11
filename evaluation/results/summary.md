# Evaluation Results

Questions run: **25**

## Metric summary

| Metric | Value |
| --- | --- |
| citation accuracy | 0.492 |
| tool selection accuracy | 0.625 |
| route accuracy | 0.571 |
| workflow completion rate | 1.0 |
| behaviour accuracy | 0.92 |
| groundedness | 1.0 |
| escalations | 2 |
| capped runs (step limit) | 0 |
| planning errors | 0 |
| latency p50 (ms) | 5253 |
| latency p95 (ms) | 10741 |

## By category

| Category | n | Citation acc. | Route acc. | Behaviour |
| --- | --- | --- | --- | --- |
| ambiguous | 3 | 0.333 | None | 0.333 |
| multi_document | 5 | 0.5 | 1.0 | 1.0 |
| out_of_scope | 3 | None | None | 1.0 |
| simple_policy | 8 | 0.5 | None | 1.0 |
| tool_requiring | 6 | 0.5 | 0.4 | 1.0 |

## Failures worth fixing

- **Q01** — missing tools ['search_policy_documents']; no gold document cited
- **Q02** — missing tools ['search_policy_documents']; no gold document cited
- **Q06** — missing tools ['search_policy_documents']; no gold document cited
- **Q07** — missing tools ['search_policy_documents']; no gold document cited
- **Q11** — no gold document cited
- **Q13** — missing tools ['search_policy_documents']; no gold document cited
- **Q14** — route expected `manager approval required`, got `INSUFFICIENT`
- **Q15** — route expected `insufficient`, got `None`; missing tools ['check_policy_compliance']; no gold document cited
- **Q16** — route expected `NEEDS_PRE_APPROVAL`, got `None`; missing tools ['check_policy_compliance']; no gold document cited
- **Q19** — missing tools ['check_pto_balance']; no gold document cited
- **Q20** — behaviour expected `clarify`
- **Q22** — behaviour expected `clarify`

## Per-question

- Q01 [simple_policy] route=`None` cite=0.0 tools=0 236ms
- Q02 [simple_policy] route=`None` cite=0.0 tools=0 121ms
- Q03 [simple_policy] route=`None` cite=1.0 tools=2 6596ms
- Q04 [simple_policy] route=`None` cite=1.0 tools=1 5253ms
- Q05 [simple_policy] route=`None` cite=1.0 tools=5 10898ms
- Q06 [simple_policy] route=`None` cite=0.0 tools=0 132ms
- Q07 [simple_policy] route=`None` cite=0.0 tools=0 140ms
- Q08 [simple_policy] route=`None` cite=1.0 tools=2 10741ms
- Q09 [multi_document] route=`PEOPLE_OPS_AND_LEGAL` cite=1.0 tools=4 9430ms
- Q10 [multi_document] route=`DECLINED` cite=1.0 tools=4 9954ms
- Q11 [multi_document] route=`NOT_ELIGIBLE` cite=0.0 tools=1 3800ms
- Q12 [multi_document] route=`MANAGER_APPROVAL` cite=0.5 tools=3 7876ms
- Q13 [multi_document] route=`INSUFFICIENT` cite=0.0 tools=2 5361ms
- Q14 [tool_requiring] route=`INSUFFICIENT` cite=1.0 tools=3 7185ms
- Q15 [tool_requiring] route=`None` cite=0.0 tools=1 4081ms
- Q16 [tool_requiring] route=`None` cite=0.0 tools=1 4570ms
- Q17 [tool_requiring] route=`CLAIM_WITH_RECEIPT` cite=1.0 tools=1 6706ms
- Q18 [tool_requiring] route=`INELIGIBLE` cite=1.0 tools=3 6308ms
- Q19 [tool_requiring] route=`None` cite=0.0 tools=0 137ms
- Q20 [ambiguous] route=`INSUFFICIENT` cite=None tools=3 5551ms
- Q21 [ambiguous] route=`None` cite=0.333 tools=2 5635ms
- Q22 [ambiguous] route=`INSUFFICIENT` cite=None tools=5 9128ms
- Q23 [out_of_scope] route=`None` cite=None tools=0 123ms
- Q24 [out_of_scope] route=`None` cite=None tools=0 300ms
- Q25 [out_of_scope] route=`None` cite=None tools=0 138ms
