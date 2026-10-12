"""Merges kb_part1.py + kb_part2.py into x500_rag_knowledge_base_v2.json and validates tags against taxonomy_v2.json."""
import json
from kb_part1 import P1
from kb_part2 import P2
allc=P1+P2; tax=json.load(open('taxonomy_v2.json'))
assert len({c['chunk_id'] for c in allc})==len(allc)
for c in allc:
    assert all(i in tax['issue_types'] or i=='general' for i in c['issue_types']), c['chunk_id']
    assert all(s in tax['symptoms'] for s in c['symptoms']), c['chunk_id']
json.dump({"dataset_name":"ProductLoop X500 RAG Knowledge Base v2","disclaimer":"Synthetic, fictional prototype documentation built from Data_synthetic/*.md.","taxonomy_version":tax['version'],
 "product":{"model":"X500","category":"electric_shaver"},"conflict_rule":"When files disagree, 03_safety_escalation.md wins.","chunks":allc},
 open('x500_rag_knowledge_base_v2.json','w'),indent=1,ensure_ascii=False)
print(len(allc),"chunks")
