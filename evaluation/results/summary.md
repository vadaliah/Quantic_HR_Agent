# Evaluation Results

Questions run: **25**

## Metric summary

| Metric | Value |
| --- | --- |
| citation accuracy | 0.692 |
| tool selection accuracy | 0.908 |
| route accuracy | 0.714 |
| workflow completion rate | 1.0 |
| behaviour accuracy | 1.0 |
| groundedness | 1.0 |
| escalations | 2 |
| capped runs (step limit) | 0 |
| planning errors | 0 |
| latency p50 (ms) | 5873 |
| latency p95 (ms) | 8505 |

## By category

| Category | n | Citation acc. | Route acc. | Behaviour |
| --- | --- | --- | --- | --- |
| ambiguous | 3 | 0.333 | None | 1.0 |
| multi_document | 5 | 0.7 | 1.0 | 1.0 |
| out_of_scope | 3 | None | None | 1.0 |
| simple_policy | 8 | 0.875 | None | 1.0 |
| tool_requiring | 6 | 0.5 | 0.6 | 1.0 |

## Failures worth fixing

- **Q02** — no gold document cited
- **Q11** — missing tools ['search_policy_documents']; no gold document cited
- **Q14** — route expected `MANAGER_APPROVAL`, got `INSUFFICIENT`; missing tools ['search_policy_documents']
- **Q15** — no gold document cited
- **Q16** — route expected `NEEDS_PRE_APPROVAL`, got `None`; missing tools ['check_policy_compliance']; no gold document cited
- **Q19** — missing tools ['search_policy_documents']; no gold document cited

## Per-question

- Q01 [simple_policy] route=`None` cite=1.0 tools=2 6354ms
- Q02 [simple_policy] route=`None` cite=0.0 tools=3 8077ms
- Q03 [simple_policy] route=`None` cite=1.0 tools=2 5842ms
- Q04 [simple_policy] route=`None` cite=1.0 tools=1 4697ms
- Q05 [simple_policy] route=`CLAIM_WITH_RECEIPT` cite=1.0 tools=3 6885ms
- Q06 [simple_policy] route=`FULL` cite=1.0 tools=3 7105ms
- Q07 [simple_policy] route=`INSUFFICIENT` cite=1.0 tools=3 7530ms
- Q08 [simple_policy] route=`None` cite=1.0 tools=2 5873ms
- Q09 [multi_document] route=`PEOPLE_OPS_AND_LEGAL` cite=1.0 tools=4 9141ms
- Q10 [multi_document] route=`DECLINED` cite=1.0 tools=4 8505ms
- Q11 [multi_document] route=`NOT_ELIGIBLE` cite=0.0 tools=1 3630ms
- Q12 [multi_document] route=`None` cite=0.5 tools=2 5705ms
- Q13 [multi_document] route=`INSUFFICIENT` cite=1.0 tools=3 7725ms
- Q14 [tool_requiring] route=`INSUFFICIENT` cite=1.0 tools=3 6525ms
- Q15 [tool_requiring] route=`INSUFFICIENT` cite=0.0 tools=4 7672ms
- Q16 [tool_requiring] route=`None` cite=0.0 tools=1 4908ms
- Q17 [tool_requiring] route=`CLAIM_WITH_RECEIPT` cite=1.0 tools=2 6403ms
- Q18 [tool_requiring] route=`INELIGIBLE` cite=1.0 tools=3 6905ms
- Q19 [tool_requiring] route=`None` cite=0.0 tools=1 4424ms
- Q20 [ambiguous] route=`None` cite=None tools=0 182ms
- Q21 [ambiguous] route=`None` cite=0.333 tools=2 6342ms
- Q22 [ambiguous] route=`None` cite=None tools=0 193ms
- Q23 [out_of_scope] route=`None` cite=None tools=0 134ms
- Q24 [out_of_scope] route=`None` cite=None tools=0 135ms
- Q25 [out_of_scope] route=`None` cite=None tools=0 195ms
