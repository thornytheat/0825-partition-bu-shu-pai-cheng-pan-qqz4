from datetime import datetime, timezone
from hashlib import sha256
from time import monotonic

from app.business import DomainIssue
from app.config import RULE_VERSION
from app.modules.pipeline import run
from app.review.adjudication import build_supplement, recompute, signability


def now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def execute(store, data):
    start = monotonic()
    fingerprint = sha256(data).hexdigest()
    run_id = sha256(f'{RULE_VERSION}:{fingerprint}'.encode()).hexdigest()
    try:
        return store.load(run_id)
    except DomainIssue as error:
        if error.code != 'RUN_NOT_FOUND':
            raise
    report = run(data)
    report['manifest'] = dict(sha256=fingerprint, version=RULE_VERSION, created=now(),
                              duration_ms=round((monotonic()-start)*1000,3), bytes=len(data), run_id=run_id)
    return store.register(run_id,report)


def snapshot(store, run_id):
    """装配批次视图：原始报告叠加已采信补证后的复算、组级判定与复核状态。"""
    batch = store.load(run_id)
    report = batch['report']
    supplements = store.supplements(run_id)
    outcomes = recompute(report, supplements)
    report_view = {**report,
                   'supplements': supplements,
                   'recomputed': {cid: case['status'] for cid, case in outcomes.items()},
                   'case_signability': signability(report, supplements, outcomes)}
    return {**batch, 'report': report_view, 'case_reviews': store.case_reviews(run_id)}


def review(store, run_id, values):
    if not isinstance(values, dict):
        raise DomainIssue('REVIEW_FIELDS')
    revision, status, note = (values.get(key) for key in ('revision','status','note'))
    if type(revision) is not int or revision < 0 or status not in ('APPROVED','HELD') or not isinstance(note,str) or not (3<=len(note.strip())<=200):
        raise DomainIssue('REVIEW_FIELDS')
    current = store.load(run_id)
    if revision != current['revision']:
        raise DomainIssue('STALE_REVIEW')
    if current['status'] == 'APPROVED':
        raise DomainIssue('RUN_FINALIZED')
    if status == 'APPROVED' and not current['report']['balance']['releasable']:
        raise DomainIssue('UNRESOLVED_ISSUES')
    return store.revise(run_id,revision,status,note.strip(),now())


def review_case(store, run_id, values):
    if not isinstance(values, dict):
        raise DomainIssue('REVIEW_FIELDS')
    case_id, revision, status, note = (values.get(key) for key in ('case','revision','status','note'))
    if not isinstance(case_id, str) or type(revision) is not int or revision < 0 \
            or status not in ('APPROVED','HELD') or not isinstance(note, str) or not (3 <= len(note.strip()) <= 200):
        raise DomainIssue('REVIEW_FIELDS')
    batch = store.load(run_id)
    case_ids = {case['case'] for case in batch['report']['cases']}
    if case_id not in case_ids:
        raise DomainIssue('CASE_NOT_FOUND')
    existing = store.case_reviews(run_id).get(case_id)
    if existing and existing['status'] == 'APPROVED':
        # 已签发内容不可被后续操作覆盖。
        raise DomainIssue('CASE_FINALIZED')
    if status == 'APPROVED':
        view = snapshot(store, run_id)
        verdict = view['report']['case_signability'][case_id]
        if not verdict['signable']:
            raise DomainIssue('CASE_NOT_SIGNABLE')
    return store.review_case(run_id, case_id, revision, status, note.strip(), now())


def submit_supplement(store, run_id, values):
    if not isinstance(values, dict):
        raise DomainIssue('SUPPLEMENT_FIELDS')
    dispute_id = values.get('dispute_id')
    batch = store.load(run_id)
    disputes = {item['dispute_id']: item for item in batch['report']['disputes']}
    if not isinstance(dispute_id, str) or dispute_id not in disputes:
        raise DomainIssue('DISPUTE_NOT_FOUND')
    if store.load_supplement(run_id, dispute_id) is not None:
        # 同一争议只采信一个补证版本；并发落败者不会覆盖胜出版本。
        raise DomainIssue('SUPPLEMENT_CONTESTED')
    supplements = store.supplements(run_id)
    # 已签发的组不允许补证改写其内容。
    approved_cases = {cid for cid, item in store.case_reviews(run_id).items() if item['status'] == 'APPROVED'}
    result = build_supplement(batch['report'], disputes[dispute_id], values, supplements)
    if approved_cases & set(result['affected_cases']):
        raise DomainIssue('CASE_FINALIZED')
    return store.save_supplement(run_id, dispute_id, result, now())
