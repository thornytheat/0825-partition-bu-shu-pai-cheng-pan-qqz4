"""争议与补证的 HTTP 入口测试。"""
import io

import pytest

from test_disputes import correction, disputed_csv


@pytest.fixture
def disputed_run(client):
    response = client.post('/api/runs', data={'file': (io.BytesIO(disputed_csv()), 'dispute.csv')},
                           content_type='multipart/form-data')
    assert response.status_code == 200
    return response.json['id']


def test_run_snapshot_exposes_disputes_and_signability(client, disputed_run):
    payload = client.get(f'/api/runs/{disputed_run}').json
    assert payload['report']['disputes'][0]['cases'] == ['000A', '000B']
    signable = payload['report']['case_signability']
    assert signable['000A']['signable'] is False and signable['000C']['signable'] is True


def test_case_issue_endpoint_approves_unaffected_group(client, disputed_run):
    response = client.patch(f'/api/runs/{disputed_run}/cases/000C', json={
        'revision': 0, 'status': 'APPROVED', 'note': '无争议组放行'})
    assert response.status_code == 200 and response.json['status'] == 'APPROVED'
    blocked = client.patch(f'/api/runs/{disputed_run}/cases/000A', json={
        'revision': 0, 'status': 'APPROVED', 'note': '带争议签发'})
    assert blocked.status_code == 409 and blocked.json['code'] == 'CASE_NOT_SIGNABLE'


def test_supplement_flow_over_http(client, disputed_run):
    response = client.post(f'/api/runs/{disputed_run}/supplements',
                           json={'dispute_id': 'D001', 'row': correction()})
    assert response.status_code == 200 and response.json['accepted'] is True
    duplicate = client.post(f'/api/runs/{disputed_run}/supplements',
                            json={'dispute_id': 'D001', 'row': correction(case='000B')})
    assert duplicate.status_code == 409 and duplicate.json['code'] == 'SUPPLEMENT_CONTESTED'
    payload = client.get(f'/api/runs/{disputed_run}').json
    assert payload['report']['case_signability']['000A']['signable'] is True
    assert payload['case_reviews'] == {}


def test_supplement_unknown_dispute_is_404(client, disputed_run):
    response = client.post(f'/api/runs/{disputed_run}/supplements',
                           json={'dispute_id': 'D404', 'row': correction()})
    assert response.status_code == 404 and response.json['code'] == 'DISPUTE_NOT_FOUND'


def test_evidence_includes_dispute_adjudication(client, disputed_run):
    client.post(f'/api/runs/{disputed_run}/supplements', json={'dispute_id': 'D001', 'row': correction()})
    packet = client.get(f'/api/runs/{disputed_run}/evidence').json
    assert packet['schema'] == 'review-evidence/2'
    assert packet['supplements']['D001']['accepted'] is True
    assert packet['case_signability']['000B']['signable'] is True
