"""争议发现：同一记录号出现互不相同的版本时，登记争议并标记受影响分组。

争议有两种形态：
- 组内争议：各版本指向同一个业务组，只暂缓该组；
- 跨组争议：版本指向不同业务组，所有涉及组一起暂缓，
  因为单条记录无法同时归属两个组，任一组在裁决前都不完整。
"""
from collections import defaultdict

from app.business import DomainIssue
from app.intake.schema import record


def collect(isolation):
    """从隔离明细中提取 DUPLICATE_CONFLICT 行并归并成争议。"""
    grouped = defaultdict(list)
    for item in isolation:
        if item['reason'] == 'DUPLICATE_CONFLICT':
            grouped[item['record']].append(item)
    disputes = []
    for index, record_key in enumerate(sorted(grouped), start=1):
        versions = sorted(grouped[record_key], key=lambda item: item['line'])
        cases = sorted({item['case'] for item in versions})
        disputes.append({
            'dispute_id': f'D{index:03d}',
            'record': record_key,
            'cases': cases,
            'cross_case': len(cases) > 1,
            'lines': [item['line'] for item in versions],
            'status': 'OPEN',
        })
    return disputes


def case_index(disputes):
    """返回 case -> 争议号列表 的索引，供分组打标。"""
    index = defaultdict(list)
    for dispute in disputes:
        for case in dispute['cases']:
            index[case].append(dispute['dispute_id'])
    return dict(index)


def parse_correction(values):
    """补证行必须与标准列结构一致，解析后返回规范化记录。"""
    try:
        return record(values)
    except DomainIssue:
        raise DomainIssue('SUPPLEMENT_FIELDS')
