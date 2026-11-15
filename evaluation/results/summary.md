# Evaluation Results

Questions run: **30**

## Metric summary

| Metric | Value |
| --- | --- |
| citation accuracy | 0.0 |
| tool selection accuracy | 0.0 |
| route accuracy | 0.0 |
| workflow completion rate | 0.067 |
| behaviour accuracy | 0.767 |
| groundedness | 1.0 |
| escalations | 0 |
| capped runs (step limit) | 0 |
| planning errors | 28 |
| latency p50 (ms) | 403 |
| latency p95 (ms) | 644 |

## By category

| Category | n | Citation acc. | Route acc. | Behaviour |
| --- | --- | --- | --- | --- |
| ambiguous | 4 | None | None | 0.25 |
| multi_document | 7 | 0.0 | 0.0 | 0.857 |
| out_of_scope | 4 | None | None | 0.25 |
| simple_policy | 8 | 0.0 | None | 1.0 |
| tool_requiring | 7 | 0.0 | 0.0 | 1.0 |

## Failures worth fixing

- **Q01** — missing tools ['search_policy_documents']; no gold document cited; planning error
- **Q02** — missing tools ['search_policy_documents']; no gold document cited; planning error
- **Q03** — missing tools ['search_policy_documents']; no gold document cited; planning error
- **Q04** — missing tools ['search_policy_documents']; no gold document cited; planning error
- **Q05** — missing tools ['search_policy_documents']; no gold document cited; planning error
- **Q06** — missing tools ['search_policy_documents']; no gold document cited; planning error
- **Q07** — missing tools ['search_policy_documents']; no gold document cited; planning error
- **Q08** — missing tools ['search_policy_documents']; no gold document cited; planning error
- **Q09** — route expected `PEOPLE_OPS_AND_LEGAL_APPROVAL`, got `None`; missing tools ['check_policy_compliance', 'search_policy_documents']; no gold document cited; planning error
- **Q10** — behaviour expected `answer_with_escalation`; missing tools ['check_policy_compliance', 'search_policy_documents']; no gold document cited; planning error
- **Q11** — missing tools ['lookup_benefits_status', 'search_policy_documents']; no gold document cited; planning error
- **Q12** — missing tools ['search_policy_documents']; no gold document cited; planning error
- **Q13** — missing tools ['search_policy_documents']; no gold document cited; planning error
- **Q14** — route expected `MANAGER_APPROVAL`, got `None`; missing tools ['check_pto_balance', 'check_policy_compliance']; no gold document cited; planning error
- **Q15** — route expected `INSUFFICIENT_BALANCE`, got `None`; missing tools ['check_pto_balance', 'check_policy_compliance']; no gold document cited; planning error
- **Q16** — route expected `NEEDS_PRE_APPROVAL`, got `None`; missing tools ['check_policy_compliance', 'search_policy_documents']; no gold document cited; planning error
- **Q17** — route expected `CLAIM_WITH_RECEIPT`, got `None`; missing tools ['check_policy_compliance', 'search_policy_documents']; no gold document cited; planning error
- **Q18** — route expected `NOT_ELIGIBLE`, got `None`; missing tools ['lookup_employee_profile', 'check_policy_compliance']; no gold document cited; planning error
- **Q19** — route expected `CLAIM_WITH_RECEIPT`, got `None`; missing tools ['check_policy_compliance', 'search_policy_documents']; no gold document cited; planning error
- **Q20** — route expected `PARTIAL_UP_TO_LIMIT`, got `None`; missing tools ['check_policy_compliance', 'search_policy_documents']; no gold document cited; planning error
- **Q22** — behaviour expected `clarify`; planning error
- **Q23** — behaviour expected `clarify`; planning error
- **Q24** — behaviour expected `clarify`; planning error
- **Q26** — behaviour expected `refuse`; planning error
- **Q27** — behaviour expected `refuse`; planning error
- **Q28** — behaviour expected `refuse`; planning error
- **Q29** — missing tools ['search_policy_documents']; no gold document cited; planning error
- **Q30** — missing tools ['search_policy_documents']; no gold document cited; planning error

## Per-question

- Q01 [simple_policy] route=`None` cite=0.0 tools=0 991ms
- Q02 [simple_policy] route=`None` cite=0.0 tools=0 537ms
- Q03 [simple_policy] route=`None` cite=0.0 tools=0 403ms
- Q04 [simple_policy] route=`None` cite=0.0 tools=0 644ms
- Q05 [simple_policy] route=`None` cite=0.0 tools=0 460ms
- Q06 [simple_policy] route=`None` cite=0.0 tools=0 570ms
- Q07 [simple_policy] route=`None` cite=0.0 tools=0 524ms
- Q08 [simple_policy] route=`None` cite=0.0 tools=0 404ms
- Q09 [multi_document] route=`None` cite=0.0 tools=0 395ms
- Q10 [multi_document] route=`None` cite=0.0 tools=0 393ms
- Q11 [multi_document] route=`None` cite=0.0 tools=0 395ms
- Q12 [multi_document] route=`None` cite=0.0 tools=0 574ms
- Q13 [multi_document] route=`None` cite=0.0 tools=0 497ms
- Q14 [tool_requiring] route=`None` cite=0.0 tools=0 397ms
- Q15 [tool_requiring] route=`None` cite=0.0 tools=0 398ms
- Q16 [tool_requiring] route=`None` cite=0.0 tools=0 393ms
- Q17 [tool_requiring] route=`None` cite=0.0 tools=0 397ms
- Q18 [tool_requiring] route=`None` cite=0.0 tools=0 643ms
- Q19 [tool_requiring] route=`None` cite=0.0 tools=0 442ms
- Q20 [tool_requiring] route=`None` cite=0.0 tools=0 423ms
- Q21 [ambiguous] route=`None` cite=None tools=0 6ms
- Q22 [ambiguous] route=`None` cite=None tools=0 394ms
- Q23 [ambiguous] route=`None` cite=None tools=0 393ms
- Q24 [ambiguous] route=`None` cite=None tools=0 402ms
- Q25 [out_of_scope] route=`None` cite=None tools=0 7ms
- Q26 [out_of_scope] route=`None` cite=None tools=0 690ms
- Q27 [out_of_scope] route=`None` cite=None tools=0 408ms
- Q28 [out_of_scope] route=`None` cite=None tools=0 398ms
- Q29 [multi_document] route=`None` cite=0.0 tools=0 396ms
- Q30 [multi_document] route=`None` cite=0.0 tools=0 410ms
