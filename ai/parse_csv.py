import csv
from collections import Counter
import sys

path = "build/reports/naver-place-pipeline/qwen3.5-provider-fusion-heldout-50-v2.csv"
with open(path, encoding='utf-8') as f:
    reader = csv.DictReader(f)
    rows = list(reader)

decisions = Counter(r.get("decision", "") for r in rows)
errors = Counter(r.get("error", "") for r in rows)
kakao_errors = Counter(r.get("kakao_error", "") for r in rows)
naver_errors = Counter(r.get("naver_error", "") for r in rows)
qwen_decisions = Counter(r.get("qwen_decision", "") for r in rows)

print(f"Total Rows: {len(rows)}")
for k, v in decisions.items():
    print(f"Decision: {k} = {v}")
    
for k, v in qwen_decisions.items():
    if k:
        print(f"Qwen Decision: {k} = {v}")

no_candidate = sum(1 for r in rows if r.get("kakao_candidate_count") == "0" and r.get("naver_candidate_count") == "0")
print(f"NO_CANDIDATE (0 on both providers): {no_candidate}")
