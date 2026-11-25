from flask import jsonify

LABELS = {
    'FILE_TOO_LARGE':'文件超过 256 KiB', 'FILE_EMPTY':'文件没有内容', 'FILE_BLANK':'文件只有空白',
    'HEADER_ONLY':'文件只有标题行', 'HEADER_MISMATCH':'列名与字段字典不一致', 'ENCODING_INVALID':'请使用 UTF-8 CSV',
    'CSV_MALFORMED':'CSV 引号或行格式异常', 'ROW_LIMIT':'文件超过 2000 行', 'FILE_REQUIRED':'请选择 CSV 文件',
    'RUN_NOT_FOUND':'批次不存在', 'REVIEW_FIELDS':'请填写 3 至 200 字复核意见', 'STALE_REVIEW':'批次已更新，请刷新',
    'RUN_FINALIZED':'批次已签发', 'UNRESOLVED_ISSUES':'存在待处理差异', 'SAMPLE_UNKNOWN':'样例不存在', 'STAGE_UNKNOWN':'处理阶段不存在',
    'CASE_NOT_FOUND':'业务组不存在', 'CASE_FINALIZED':'该组已签发，不可覆盖',
    'CASE_NOT_SIGNABLE':'该组存在未决争议或复算未通过，暂缓签发',
    'DISPUTE_NOT_FOUND':'争议不存在或已关闭', 'SUPPLEMENT_FIELDS':'补证行字段不符合输入规范',
    'SUPPLEMENT_CONTESTED':'同一争议只采信一个补证版本',
}

CONFLICT = {'STALE_REVIEW','RUN_FINALIZED','UNRESOLVED_ISSUES','CASE_FINALIZED',
            'CASE_NOT_SIGNABLE','SUPPLEMENT_CONTESTED'}
NOT_FOUND = {'RUN_NOT_FOUND','SAMPLE_UNKNOWN','STAGE_UNKNOWN','CASE_NOT_FOUND','DISPUTE_NOT_FOUND'}
TOO_LARGE = {'FILE_TOO_LARGE'}


def response(error):
    code = error.code
    status = 404 if code in NOT_FOUND else 409 if code in CONFLICT else 413 if code in TOO_LARGE else 422
    return jsonify(code=code,message=LABELS.get(code,code)),status
