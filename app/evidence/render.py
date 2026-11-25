import json


def artifact(run):
    packet = {
        'schema': 'review-evidence/2',
        'manifest': run['report']['manifest'],
        'balance': run['report']['balance'],
        'disputes': run['report']['disputes'],
        'supplements': run['report'].get('supplements', {}),
        'recomputed': run['report'].get('recomputed', {}),
        'case_signability': run['report'].get('case_signability', {}),
        'cases': run['report']['cases'],
        'intake': run['report']['intake'],
        'review': {key:run[key] for key in ('status','revision','note','reviewed')},
        'case_reviews': run.get('case_reviews', {}),
    }
    return (json.dumps(packet, ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
