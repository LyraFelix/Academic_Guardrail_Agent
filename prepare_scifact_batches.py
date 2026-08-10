"""Prepare SciFact dev set (claim, evidence_sentence, gold_label) batches for LLM evaluation."""

import json
from pathlib import Path
from benchmark_scifact_official import ensure_scifact_data
from academic_guardrail.providers.claim_eval import ClaimEvaluator

claims_dev, corpus = ensure_scifact_data()
evaluator = ClaimEvaluator()

eval_samples = []
for c in claims_dev:
    claim_text = c["claim"]
    evidence_dict = c.get("evidence", {})
    
    if not evidence_dict:
        for doc_id in c.get("cited_doc_ids", []):
            if doc_id in corpus:
                abstract_text = " ".join(corpus[doc_id].get("abstract", []))
                best_sent, _ = evaluator.find_best_matching_sentence(claim_text, abstract_text)
                eval_samples.append({
                    "id": len(eval_samples) + 1,
                    "claim": claim_text,
                    "evidence": best_sent or abstract_text[:200],
                    "gold": "NEUTRAL"
                })
        continue

    for doc_id_str, ev_list in evidence_dict.items():
        doc_id = int(doc_id_str)
        if doc_id not in corpus:
            continue
        abstract_sentences = corpus[doc_id].get("abstract", [])
        abstract_text = " ".join(abstract_sentences)
        best_sent, _ = evaluator.find_best_matching_sentence(claim_text, abstract_text)

        labels = {ev.get("label") for ev in ev_list}
        if "SUPPORT" in labels:
            gold_label = "SUPPORTS"
        elif "CONTRADICT" in labels:
            gold_label = "CONTRADICTS"
        else:
            gold_label = "NEUTRAL"

        eval_samples.append({
            "id": len(eval_samples) + 1,
            "claim": claim_text,
            "evidence": best_sent or abstract_text[:200],
            "gold": gold_label
        })

out_dir = Path("C:/Users/Felix/.gemini/antigravity/brain/bde8ec19-c1ff-492d-9be0-9d0aed028cd2/scratch")
out_dir.mkdir(parents=True, exist_ok=True)

# Split into 6 batches (~54 items per batch)
batch_size = 55
batches = [eval_samples[i:i + batch_size] for i in range(0, len(eval_samples), batch_size)]

for idx, b in enumerate(batches):
    batch_file = out_dir / f"scifact_batch_{idx+1}.json"
    with open(batch_file, "w", encoding="utf-8") as f:
        json.dump(b, f, ensure_ascii=False, indent=2)

print(f"Prepared {len(eval_samples)} total items across {len(batches)} batches.")
