"""补证裁决与组级可签发判定。

有效行集合 = 原始采信行剔除全部争议记录，再叠加每个争议已采信的补证行。
补证把任务改归另一组时，原组与目标组都要在同一有效集合上整体复算，
任一组未通过（非 READY），所有受影响组都不具备签发条件。
"""
from app.business import DomainIssue
from app.intake.disputes import parse_correction
from app.modules.grouping import case_groups
from app.modules.pipeline import evaluate


def effective_rows(report, supplements):
    disputed = {dispute['record'] for dispute in report['disputes']}
    rows = [row for row in report['source_rows'] if row['record'] not in disputed]
    for supplement in supplements.values():
        rows.append(supplement['corrected_row'])
    return rows


def recompute(report, supplements):
    """按当前有效行集合复算所有分组，返回 case -> 复算结果。"""
    groups = dict(case_groups(effective_rows(report, supplements)))
    outcomes = {}
    for case in report['cases']:
        cid = case['case']
        if cid in groups:
            outcomes[cid] = evaluate(groups[cid], 5)
        else:
            outcomes[cid] = {'case': cid, 'records': [], 'status': 'EMPTY_CASE', 'dispute_ids': []}
    return outcomes


def affected_cases(dispute, corrected_row, outcomes):
    """受影响分组 = 争议原涉及分组 ∪ 补证改归的目标分组。"""
    cases = set(dispute['cases'])
    cases.add(corrected_row['case'])
    return sorted(cases & set(outcomes))


def build_supplement(report, dispute, values, supplements):
    """校验并构造补证复算结果，不落库（落库的并发裁决由 Store 负责）。"""
    if not isinstance(values, dict) or not isinstance(values.get('row'), list):
        raise DomainIssue('SUPPLEMENT_FIELDS')
    corrected = parse_correction(values['row'])
    if corrected['record'] != dispute['record']:
        raise DomainIssue('SUPPLEMENT_FIELDS')
    candidate = dict(supplements)
    # 先以候选行试算，验证两个受影响组能否同时通过复算。
    candidate[dispute['dispute_id']] = {'corrected_row': corrected}
    outcomes = recompute(report, candidate)
    touched = affected_cases(dispute, corrected, outcomes)
    result = {
        'dispute_id': dispute['dispute_id'],
        'record': dispute['record'],
        'corrected_row': corrected,
        'target_case': corrected['case'],
        'affected_cases': touched,
        'outcomes': {cid: outcomes[cid]['status'] for cid in touched},
        'accepted': all(outcomes[cid]['status'] == 'READY' for cid in touched),
    }
    return result


def linked_disputes(report, supplements, case_id):
    """与某分组相关的争议（原涉及或补证后受影响）。"""
    linked = []
    for dispute in report['disputes']:
        supplement = supplements.get(dispute['dispute_id'])
        touched = set(dispute['cases'])
        if supplement:
            touched.update(supplement['affected_cases'])
        if case_id in touched:
            linked.append(dispute['dispute_id'])
    return linked


def signability(report, supplements, outcomes):
    """逐组给出有效状态、关联争议与是否可签发。"""
    result = {}
    for case in report['cases']:
        cid = case['case']
        effective = outcomes.get(cid, case)
        links = linked_disputes(report, supplements, cid)
        blocked = []
        for dispute_id in links:
            supplement = supplements.get(dispute_id)
            if supplement is None:
                blocked.append((dispute_id, 'DISPUTE_OPEN'))
            elif not supplement['accepted'] or any(status != 'READY' for status in supplement['outcomes'].values()):
                blocked.append((dispute_id, 'RECOMPUTE_FAILED'))
        result[cid] = {
            'effective_status': effective['status'],
            'dispute_ids': links,
            'signable': effective['status'] == 'READY' and not blocked,
            'blockers': [{'dispute_id': did, 'reason': reason} for did, reason in blocked],
        }
    return result
