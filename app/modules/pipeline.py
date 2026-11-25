from app.business import DomainIssue
from app.intake.disputes import case_index, collect
from app.intake.service import inspect
from app.modules.calculate import compute
from app.modules.grouping import case_groups
from app.modules.policy import policy
from app.modules.prepare import prepare
from app.modules.reconcile import balance


def evaluate(rows, stage):
    case = {'case':rows[0]['case'],'records':[r['record'] for r in rows], 'status':'READY'}
    try:
        case['prep'], payload = prepare(rows)
        if stage >= 3:
            case['measure'] = compute(payload)
        if stage >= 4:
            case.update(policy(case['measure']))
    except DomainIssue as error:
        case['status'] = error.code
    return case


def run(data, stage=5):
    intake = inspect(data)
    disputes = collect(intake['isolation'])
    disputed = case_index(disputes)
    output = {'intake': {k:v for k,v in intake.items() if k!='rows'},
              'disputes': disputes,
              'source_rows': intake['rows']}
    if stage == 1:
        return output
    cases = [evaluate(rows, stage) for _, rows in case_groups(intake['rows'])]
    for case in cases:
        case['dispute_ids'] = disputed.get(case['case'], [])
    output['cases'] = cases
    if stage >= 5:
        output['balance'] = balance(intake,cases)
    return output
