"""Offline forensic arithmetic for PR 406. Does not call a model or change scores.

Run from repository root:
  .venv/Scripts/python.exe docs/measurements/r407/audit/reproduce.py
Writes analysis.json and row-ledger.md beside this script.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from evals.official.rubric import (AXIS_ORDER, _clean, _heads, _is_descendant,
    answer_conciseness, overall, reference_conciseness,
    reference_correctness_loose, reference_correctness_strict, score_rows)

HERE = Path(__file__).resolve().parent
SCORE = 'docs/measurements/r388/score-r407-direct-bedrock-cohere-v4-pro-hard.json'
CKPT = 'evals/bench/results/official-r407-direct-bedrock-cohere-v4-pro-hard.ckpt.jsonl'
CACHE = 'docs/measurements/r407/judge-cache.jsonl'
GOLD = 'docs/measurements/r388/official_gold_n110.jsonl'

def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))

def lines(path):
    return [json.loads(x) for x in (ROOT / path).read_text(encoding='utf-8').splitlines() if x.strip()]

def avg(xs):
    return statistics.mean(xs) if xs else None

def ci(xs):
    # Question-resampling diagnostic, not independent trials or judge uncertainty.
    rng = random.Random(406)
    samples = sorted(avg(rng.choices(xs, k=len(xs))) for _ in range(5000))
    return [samples[124], samples[4874]]

def main():
    score = read(SCORE)
    checkpoint = {r['id']: r for r in lines(CKPT)}
    cache_lines = lines(CACHE)
    cache = {r['key'].split(':')[0]: r for r in cache_lines}
    gold = {r['id']: r for r in lines(GOLD)}
    assert len(score['rows']) == len(checkpoint) == len(cache) == len(cache_lines) == 110
    rows = []
    ledger = []
    for r in score['rows']:
        qid = r['id']; c = checkpoint[qid]; v = cache[qid]['verdict']
        key = qid + ':' + hashlib.sha256(r['answer'].encode()).hexdigest()[:16] + ':' + hashlib.sha256(score['judge_identity'].encode()).hexdigest()[:12]
        assert key == cache[qid]['key']
        assert r['answer'] == c['pred_answer']
        assert r['criteria'] == v['criteria']
        assert r['criterion_remarks'] == v['criterion_remarks']
        assert len(r['answer']) == r['answer_chars']
        assert len(gold[qid]['reference_answer']) == r['reference_chars']
        assert gold[qid]['criteria'] == r['criteria_text']
        item = dict(r, references=r['refs'], reference_answer=gold[qid]['reference_answer'])
        rows.append(item)
        exp = _clean(r['expected_refs']); pred = _clean(r['refs'])
        missing = [e for e in exp if not any(_is_descendant(p, e) for p in pred)]
        ledger.append({
            'id': qid, 'difficulty': c['difficulty'], 'category': c['difficulty_category'],
            'stage2': c['provenance']['stage2_polish'], 'stage2_model': c['provenance']['stage2_model'],
            'passed': sum(r['criteria']), 'criteria_count': len(r['criteria']),
            'ans_conciseness': 100*answer_conciseness(r['answer'], item['reference_answer']),
            'ref_conciseness': reference_conciseness(pred, exp),
            'ref_loose': reference_correctness_loose(pred, exp),
            'ref_strict': reference_correctness_strict(pred, exp),
            'refs': pred, 'expected_refs': exp, 'missing_strict': missing,
            'extra_heads': sorted(set(_heads(pred))-set(_heads(exp))) if exp else [],
            'raw_refs_differ': pred != _clean(c['pred_refs']),
            'turn1_chars': len(c['turn1_answer']), 'answer_chars': len(r['answer']),
            'reference_chars': r['reference_chars'], 'latency_s': r['latency_s'],
            'judge_disagreements': [i+1 for i in range(len(v['criteria'])) if len({run[i] for run in v['_corr_runs'] if run is not None}) > 1],
        })
    computed = score_rows(rows)
    assert computed == score['axes'], (computed, score['axes'])
    ref_rows = [r for r in ledger if r['expected_refs']]
    cohorts = {}
    for name, ids in {
        'content_easy': {r['id'] for r in ledger if r['difficulty'] == 'EASY'},
        'content_hard': {r['id'] for r in ledger if r['difficulty'] == 'HARD'},
        'stage2_landed': {r['id'] for r in ledger if r['stage2']},
        'stage2_not_landed': {r['id'] for r in ledger if not r['stage2']},
        'all_criteria_pass': {r['id'] for r in ledger if r['passed'] == r['criteria_count']},
        'some_criteria_fail': {r['id'] for r in ledger if r['passed'] != r['criteria_count']},
    }.items():
        cohorts[name] = score_rows([r for r in rows if r['id'] in ids])
    history = {}
    for filename in ['score-r390-opus5-live-easy.json','score-r390-live-hard-opus5-hard.json','score-r405-hard-bedrock-qwen235b-hard.json']:
        s = read('docs/measurements/r388/'+filename)
        old = {r['id']: r for r in s['rows']}
        assert set(old) == set(checkpoint)
        assert all(old[r['id']]['reference_chars'] == r['reference_chars'] for r in rows)
        deltas = [100*(min(1,r['reference_chars']/r['answer_chars']) - min(1,old[r['id']]['reference_chars']/old[r['id']]['answer_chars'])) for r in rows]
        history[filename] = {'axes':s['axes'], 'checkpoint':s['ckpt'], 'judge_identity':s.get('judge_identity'),
            'criteria_equal_rows':sum(old[r['id']]['criteria_text']==r['criteria_text'] for r in rows),
            'expected_equal_rows':sum(old[r['id']]['expected_refs']==r['expected_refs'] for r in rows),
            'ans_conciseness_delta':avg(deltas), 'descriptive_paired_question_bootstrap_95':ci(deltas),
            'shorter':sum(r['answer_chars']<old[r['id']]['answer_chars'] for r in rows),
            'longer':sum(r['answer_chars']>old[r['id']]['answer_chars'] for r in rows),
            'equal_length':sum(r['answer_chars']==old[r['id']]['answer_chars'] for r in rows)}
    turn1 = [dict(r,answer=checkpoint[r['id']]['turn1_answer'],references=checkpoint[r['id']]['turn1_refs']) for r in rows]
    # Never present inherited final-turn criteria/tone as first-turn judgements.
    turn1_axes = {k:v for k,v in score_rows(turn1).items() if k in ['ans_conciseness','ref_correctness_loose','ref_correctness_strict','ref_conciseness','_mean_answer_chars','_mean_refs_per_row']}
    repeat_scores = []
    for i in range(3):
        repeat_scores.append(score_rows([dict(r,criteria=cache[r['id']]['verdict']['_corr_runs'][i],tone_ok=cache[r['id']]['verdict']['_tone_runs_raw'][i]) for r in rows]))
    raw_score = score_rows([dict(r,references=checkpoint[r['id']]['pred_refs']) for r in rows])
    scenarios = {}
    for name, changes in {
        'reference_conciseness_70': {'ref_conciseness':70},
        'reference_conciseness_80': {'ref_conciseness':80},
        'speed_86_7': {'resp_speed':86.7},
        'ref70_and_speed86_7': {'ref_conciseness':70,'resp_speed':86.7},
        'target_all_axes':dict(zip(AXIS_ORDER,[95,90,88,98,85,80,100,90])),
    }.items():
        vals = {**score['axes'],**changes}
        scenarios[name] = {'changes':changes,'overall':100*overall([vals[k]/100 for k in AXIS_ORDER])}
    ref_groups = {}
    for n in sorted({len(r['expected_refs']) for r in ref_rows}):
        rr = [r for r in ref_rows if len(r['expected_refs'])==n]
        ref_groups[str(n)]={'n':len(rr),'mean_provided':avg([len(r['refs']) for r in rr]),'mean_ref_conciseness':100*avg([r['ref_conciseness'] for r in rr])}
    # Evidence-only extra count: the key is reconstructed, so this is NOT an oracle pruning policy.
    result = {
        'verified_score':computed, 'raw_wire_score':raw_score,'cohorts':cohorts,'history':history,
        'turn1_deterministic_axes':turn1_axes,'repetitions':repeat_scores,
        'reference_groups_by_expected_count':ref_groups,
        'counts':{
            'criteria_total':sum(r['criteria_count'] for r in ledger),
            'criteria_failed':sum(r['criteria_count']-r['passed'] for r in ledger),
            'failed_rows':[r['id'] for r in ledger if r['passed']<r['criteria_count']],
            'excluded_ref_rows':[r['id'] for r in ledger if not r['expected_refs']],
            'answer_score_100':sum(r['ans_conciseness']==100 for r in ledger),
            'ref_score_100':sum(r['ref_conciseness']==1 for r in ref_rows),
            'ref_over_budget':sum(len(r['refs'])>len(r['expected_refs']) for r in ref_rows),
            'pred_refs_scored_total':sum(len(r['refs']) for r in ref_rows),
            'expected_refs_total':sum(len(r['expected_refs']) for r in ref_rows),
            'reference_count_excess':sum(max(0,len(r['refs'])-len(r['expected_refs'])) for r in ref_rows),
            'extra_heads_total':sum(len(r['extra_heads']) for r in ref_rows),
            'extra_head_rows':sum(bool(r['extra_heads']) for r in ref_rows),
            'strict_incomplete_rows':sum(r['ref_strict']<1 for r in ref_rows),
            'loose_incomplete_rows':sum(r['ref_loose']<1 for r in ref_rows),
            'wrong_grain_only_rows':[r['id'] for r in ref_rows if r['ref_loose']==1 and r['ref_strict']<1],
            'same_head_redundancy':sum(len(r['refs'])-len(_heads(r['refs'])) for r in ref_rows),
            'score_raw_ref_mismatch_rows':[r['id'] for r in ledger if r['raw_refs_differ']],
            'judge_disagreement_rows':[r['id'] for r in ledger if r['judge_disagreements']],
            'judge_disagreement_criteria':sum(len(r['judge_disagreements']) for r in ledger),
            'judge_runs':dict(Counter(c['verdict']['_judge_runs'] for c in cache_lines)),
            'tone_valid_run_counts':dict(Counter(sum(x is not None for x in c['verdict']['_tone_runs_raw']) for c in cache_lines)),
            'models':dict(Counter(r['stage2_model'] for r in ledger)),
            'difficulty':dict(Counter(r['difficulty'] for r in ledger)),
            'answer_changed_on_pushback':sum(c['turn1_answer']!=c['pushback_answer'] for c in checkpoint.values()),
            'pushback_shorter':sum(len(c['pushback_answer'])<len(c['turn1_answer']) for c in checkpoint.values()),
            'pushback_longer':sum(len(c['pushback_answer'])>len(c['turn1_answer']) for c in checkpoint.values()),
        },
        'scenarios_not_forecasts':scenarios,
        'reference_length_sensitivity':{str(factor):100*avg([min(1,factor*r['reference_chars']/r['answer_chars']) for r in rows]) for factor in [.8,.9,1,1.1,1.2]},
        'sha256':{path:hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in [SCORE,CKPT,CACHE,GOLD,'docs/measurements/r388/official_refkey_n110.jsonl','report.md','docs/measurements/r407/report.md']},
        'rows':ledger,
    }
    (HERE/'analysis.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    out=['# R407 per-question metric ledger','', 'Descriptive recomputation from the frozen score and checkpoint. Reference metrics use the reconstructed key; a full rubric pass is not a legal certification. All percentages are per-question; loose answer correctness in the main report is a micro-average.','', '| ID | Content | Criteria | Ans C % | Ref L % | Ref S % | Ref C % | Provided → expected | Stage 2 |','|---|---|---:|---:|---:|---:|---:|---|---|']
    def pc(v): return '—' if v is None else f'{100*v:.1f}'
    for r in ledger:
        out.append(f"| {r['id']} | {r['difficulty']} | {r['passed']}/{r['criteria_count']} | {r['ans_conciseness']:.1f} | {pc(r['ref_loose'])} | {pc(r['ref_strict'])} | {pc(r['ref_conciseness'])} | {', '.join(r['refs'])} → {', '.join(r['expected_refs']) or 'excluded'} | {'landed' if r['stage2'] else 'not landed'} |")
    (HERE/'row-ledger.md').write_text('\n'.join(out)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ['rows','sha256','repetitions']},indent=2))

if __name__ == '__main__':
    main()
