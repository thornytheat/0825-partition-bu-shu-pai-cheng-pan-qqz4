"""争议感知签发与补证裁决的规则测试。

覆盖：
- 补数单含冲突行时，无争议组照常签发，争议组暂缓；
- 同一记录号指向不同组（跨组争议），两组同时暂缓；
- 补证改归另一组后，任一组复算失败则两组都不能签发；
- 同一争议两个补证版本并发提交，只采信一个；
- 已签发组上的落败补证重试不覆盖已签发内容。
"""
import threading

import pytest

from app.business import DomainIssue
from app.review.service import execute, review_case, snapshot, submit_supplement
from conftest import csv_data


def make_row(record, case, kind='task', task=1, slots=1, deadline=9, note='补数明细'):
    return [record, case, kind, str(task), '0', str(slots), '0', str(deadline), note]


def group_rows(case, count=3, plan_slots=None):
    rows = []
    for number in range(1, count + 1):
        rows.append(make_row(f'{case}{number:02d}', case, task=number, slots=1, deadline=9))
    rows.append([f'{case}99', case, 'plan', '0', '0', str(plan_slots if plan_slots is not None else count), '0', '9', '排程基线'])
    return rows


def disputed_csv():
    """组 000A 与 000B 共享记录号 X100 却指向不同组，组 000C 与争议无关。

    000A 的 plan 基线预留一个任务位，等待 X100 补证补齐；000B 自身已完整。
    """
    rows = group_rows('000A', plan_slots=4) + group_rows('000B') + group_rows('000C')
    rows.append(make_row('X100', '000A', task=4, note='甲版本'))
    rows.append(make_row('X100', '000B', task=4, note='乙版本'))
    return csv_data(rows)


def correction(record='X100', case='000A', task=4, note='补证甲版本'):
    return make_row(record, case, task=task, note=note)


def test_dispute_is_detected_and_tags_both_cross_case_groups(store):
    run = execute(store, disputed_csv())
    report = run['report']
    disputes = report['disputes']
    assert len(disputes) == 1
    dispute = disputes[0]
    assert dispute['record'] == 'X100' and dispute['cross_case'] is True
    assert dispute['cases'] == ['000A', '000B']
    tagged = {case['case']: case['dispute_ids'] for case in report['cases']}
    assert tagged['000A'] == tagged['000B'] == ['D001']
    assert tagged['000C'] == []


def test_unaffected_group_can_be_issued_while_disputed_groups_hold(store):
    run = execute(store, disputed_csv())
    view = snapshot(store, run['id'])
    signable = view['report']['case_signability']
    assert signable['000A']['signable'] is False
    assert signable['000B']['signable'] is False
    assert signable['000C']['signable'] is True
    # 争议组即使业务判定 READY 也不能签发
    with pytest.raises(DomainIssue, match='CASE_NOT_SIGNABLE'):
        review_case(store, run['id'], dict(case='000A', revision=0, status='APPROVED', note='试图带争议签发'))
    # 无争议组照常签发
    result = review_case(store, run['id'], dict(case='000C', revision=0, status='APPROVED', note='该组无争议放行'))
    assert result['status'] == 'APPROVED' and result['revision'] == 1
    # 争议组允许填写暂缓意见
    held = review_case(store, run['id'], dict(case='000A', revision=0, status='HELD', note='等待补证裁决'))
    assert held['status'] == 'HELD'


def test_accepted_supplement_recomputes_both_groups_and_unblocks(store):
    run = execute(store, disputed_csv())
    outcome = submit_supplement(store, run['id'], dict(dispute_id='D001', row=correction(case='000A')))
    assert outcome['accepted'] is True
    assert sorted(outcome['affected_cases']) == ['000A', '000B']
    assert outcome['outcomes'] == {'000A': 'READY', '000B': 'READY'}
    view = snapshot(store, run['id'])
    signable = view['report']['case_signability']
    assert signable['000A']['signable'] and signable['000B']['signable']
    assert view['report']['recomputed']['000A'] == 'READY'


def test_reassignment_supplement_recomputes_origin_and_target_groups(store):
    # 补证把 X100 从 000A 改归 000B：000A 剩 3 个任务与 plan=4 不符，
    # 但把 000B 的补证行当作 plan 之外的额外任务会让 000B MISMATCH，
    # 因此该裁决下两组仍需各自 READY 才能放行。这里验证受影响组的集合正确。
    run = execute(store, disputed_csv())
    outcome = submit_supplement(store, run['id'], dict(dispute_id='D001', row=correction(case='000B')))
    assert set(outcome['affected_cases']) == {'000A', '000B'}
    assert outcome['target_case'] == '000B'
    assert set(outcome['outcomes']) == {'000A', '000B'}


def test_failed_recompute_blocks_both_groups(store):
    # 补证把记录改归 000B，并使用 000B 已有的任务号，触发重复任务导致复算失败
    bad = correction(case='000B', task=1, note='重复任务号补证')
    run = execute(store, disputed_csv())
    outcome = submit_supplement(store, run['id'], dict(dispute_id='D001', row=bad))
    assert outcome['accepted'] is False
    assert outcome['outcomes']['000B'] != 'READY'
    view = snapshot(store, run['id'])
    signable = view['report']['case_signability']
    assert signable['000A']['signable'] is False and signable['000B']['signable'] is False
    with pytest.raises(DomainIssue, match='CASE_NOT_SIGNABLE'):
        review_case(store, run['id'], dict(case='000A', revision=0, status='APPROVED', note='复算未过仍签发'))


def test_two_supplement_versions_only_one_is_adopted(store):
    run = execute(store, disputed_csv())
    first = submit_supplement(store, run['id'], dict(dispute_id='D001', row=correction(case='000A', note='版本一')))
    assert first['accepted'] is True
    with pytest.raises(DomainIssue, match='SUPPLEMENT_CONTESTED'):
        submit_supplement(store, run['id'], dict(dispute_id='D001', row=correction(case='000B', note='版本二')))
    # 胜出版本保持不变，落败版本没有落库
    stored = store.load_supplement(run['id'], 'D001')
    assert stored['corrected_row']['note'] == '版本一'


def test_concurrent_supplements_have_single_winner(store):
    run = execute(store, disputed_csv())
    barrier = threading.Barrier(2)
    errors = []

    def attempt(case):
        barrier.wait(3)
        try:
            submit_supplement(store, run['id'], dict(dispute_id='D001', row=correction(case=case, note=f'并发-{case}')))
        except DomainIssue as error:
            errors.append(error.code)

    threads = [threading.Thread(target=attempt, args=('000A',)),
               threading.Thread(target=attempt, args=('000B',))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == ['SUPPLEMENT_CONTESTED']
    assert len(store.supplements(run['id'])) == 1


def test_losing_supplement_retry_after_issue_does_not_overwrite(store):
    run = execute(store, disputed_csv())
    submit_supplement(store, run['id'], dict(dispute_id='D001', row=correction(case='000A', note='胜出版本')))
    review_case(store, run['id'], dict(case='000A', revision=0, status='APPROVED', note='补证后签发'))
    # 落败方重试：争议已有胜出版本，直接被拒
    with pytest.raises(DomainIssue, match='SUPPLEMENT_CONTESTED'):
        submit_supplement(store, run['id'], dict(dispute_id='D001', row=correction(case='000B', note='落败重试')))
    # 已签发的 000A 不受任何后续操作影响
    approved = store.case_reviews(run['id'])['000A']
    assert approved['status'] == 'APPROVED' and approved['note'] == '补证后签发'
    with pytest.raises(DomainIssue, match='CASE_FINALIZED'):
        review_case(store, run['id'], dict(case='000A', revision=1, status='HELD', note='试图撤销签发'))


def test_supplement_touching_issued_group_is_rejected(store):
    run = execute(store, disputed_csv())
    review_case(store, run['id'], dict(case='000C', revision=0, status='APPROVED', note='无关组先签发'))
    # 000C 不受争议影响，补证仍可提交；但一旦补证目标改成已签发组则拒绝
    with pytest.raises(DomainIssue, match='CASE_FINALIZED'):
        submit_supplement(store, run['id'], dict(dispute_id='D001', row=correction(case='000C', note='改归已签发组')))


def test_case_review_optimistic_lock(store):
    run = execute(store, disputed_csv())
    review_case(store, run['id'], dict(case='000C', revision=0, status='HELD', note='首次暂缓'))
    with pytest.raises(DomainIssue, match='STALE_REVIEW'):
        review_case(store, run['id'], dict(case='000C', revision=0, status='HELD', note='过期修订号'))


def test_supplement_validates_row_schema(store):
    run = execute(store, disputed_csv())
    with pytest.raises(DomainIssue, match='SUPPLEMENT_FIELDS'):
        submit_supplement(store, run['id'], dict(dispute_id='D001', row=['X100']))
    with pytest.raises(DomainIssue, match='SUPPLEMENT_FIELDS'):
        submit_supplement(store, run['id'], dict(dispute_id='D001', row=correction(record='OTHER')))


def test_unknown_dispute_and_case_are_rejected(store):
    run = execute(store, disputed_csv())
    with pytest.raises(DomainIssue, match='DISPUTE_NOT_FOUND'):
        submit_supplement(store, run['id'], dict(dispute_id='D999', row=correction()))
    with pytest.raises(DomainIssue, match='CASE_NOT_FOUND'):
        review_case(store, run['id'], dict(case='999Z', revision=0, status='APPROVED', note='未知分组'))
