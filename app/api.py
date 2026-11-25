from flask import Blueprint, Response, current_app, jsonify, request

from app.business import DomainIssue
from app.evidence.render import artifact
from app.inputs import read_input
from app.modules.pipeline import run
from app.review.service import execute, review, review_case, snapshot, submit_supplement

api = Blueprint('api',__name__,url_prefix='/api')
STAGES = {'intake':1,'prepare':2,'calculate':3,'policy':4,'balance':5}


@api.post('/stages/<stage>')
def preview(stage):
    if stage not in STAGES:
        raise DomainIssue('STAGE_UNKNOWN')
    return jsonify(run(read_input(),STAGES[stage]))


@api.route('/runs',methods=['GET','POST'])
def runs():
    store = current_app.extensions['runs']
    if request.method == 'GET':
        return jsonify(items=store.list())
    batch = execute(store,read_input())
    return jsonify(snapshot(store, batch['id']))


@api.route('/runs/<run_id>', methods=['GET','PATCH'])
def batch(run_id):
    store = current_app.extensions['runs']
    if request.method == 'GET':
        return jsonify(snapshot(store,run_id))
    return jsonify(review(store,run_id,request.get_json(silent=True)))


@api.patch('/runs/<run_id>/cases/<case_id>')
def case_review(run_id, case_id):
    store = current_app.extensions['runs']
    values = request.get_json(silent=True) or {}
    values.setdefault('case', case_id)
    if values['case'] != case_id:
        raise DomainIssue('REVIEW_FIELDS')
    return jsonify(review_case(store,run_id,values))


@api.post('/runs/<run_id>/supplements')
def supplement(run_id):
    store = current_app.extensions['runs']
    return jsonify(submit_supplement(store,run_id,request.get_json(silent=True)))


@api.get('/runs/<run_id>/evidence')
def export(run_id):
    report = snapshot(current_app.extensions['runs'],run_id)
    return Response(artifact(report),mimetype='application/json', headers={
        'Content-Disposition':f'attachment; filename="review-{report["id"][:12]}.json"',
        'Cache-Control':'no-store',
    })
