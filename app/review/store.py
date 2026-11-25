import json
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

from app.business import DomainIssue

SCHEMA = '''CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY, report TEXT NOT NULL, created TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING', revision INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '', reviewed TEXT
);
CREATE TABLE IF NOT EXISTS case_reviews (
    run_id TEXT NOT NULL, case_id TEXT NOT NULL,
    status TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '', reviewed TEXT,
    PRIMARY KEY (run_id, case_id)
);
CREATE TABLE IF NOT EXISTS supplements (
    run_id TEXT NOT NULL, dispute_id TEXT NOT NULL,
    report TEXT NOT NULL, created TEXT NOT NULL,
    PRIMARY KEY (run_id, dispute_id)
);'''


class Store:
    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=15)) as db, db:
            db.row_factory = sqlite3.Row
            db.executescript(SCHEMA)
            yield db

    def register(self, run_id, report):
        with self.connect() as db:
            db.execute('INSERT INTO runs(id,report,created) VALUES (?,?,?) ON CONFLICT(id) DO NOTHING',
                       (run_id,json.dumps(report,ensure_ascii=False),report['manifest']['created']))
        return self.load(run_id)

    def load(self, run_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM runs WHERE id=?',(run_id,)).fetchone()
        if row is None:
            raise DomainIssue('RUN_NOT_FOUND')
        result = dict(row)
        result['report'] = json.loads(result['report'])
        return result

    def list(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT id,created,status,revision,note FROM runs ORDER BY created DESC,id LIMIT 50')]

    def revise(self, run_id, revision, status, note, now):
        with self.connect() as db:
            cursor = db.execute('UPDATE runs SET status=?,note=?,reviewed=?,revision=revision+1 WHERE id=? AND revision=?',
                                (status,note,now,run_id,revision))
            if cursor.rowcount != 1:
                raise DomainIssue('STALE_REVIEW')
        return self.load(run_id)

    def case_reviews(self, run_id):
        with self.connect() as db:
            rows = db.execute('SELECT case_id,status,revision,note,reviewed FROM case_reviews WHERE run_id=? ORDER BY case_id',
                              (run_id,)).fetchall()
        return {row['case_id']: {k: row[k] for k in ('status','revision','note','reviewed')} for row in rows}

    def review_case(self, run_id, case_id, revision, status, note, now):
        with self.connect() as db:
            db.execute('INSERT INTO case_reviews(run_id,case_id,status,note,reviewed) VALUES (?,?,?,?,?) '
                       'ON CONFLICT(run_id,case_id) DO NOTHING',
                       (run_id,case_id,status,note,now))
            cursor = db.execute('UPDATE case_reviews SET status=?,note=?,reviewed=?,revision=revision+1 '
                                'WHERE run_id=? AND case_id=? AND revision=?',
                                (status,note,now,run_id,case_id,revision))
            if cursor.rowcount != 1:
                exists = db.execute('SELECT 1 FROM case_reviews WHERE run_id=? AND case_id=?',
                                    (run_id,case_id)).fetchone()
                raise DomainIssue('STALE_REVIEW' if exists else 'RUN_NOT_FOUND')
        return self.case_reviews(run_id)[case_id]

    def load_supplement(self, run_id, dispute_id):
        with self.connect() as db:
            row = db.execute('SELECT report,created FROM supplements WHERE run_id=? AND dispute_id=?',
                             (run_id,dispute_id)).fetchone()
        if row is None:
            return None
        return {'created': row['created'], **json.loads(row['report'])}

    def supplements(self, run_id):
        with self.connect() as db:
            rows = db.execute('SELECT dispute_id,report,created FROM supplements WHERE run_id=? ORDER BY dispute_id',
                              (run_id,)).fetchall()
        return {row['dispute_id']: {'created': row['created'], **json.loads(row['report'])} for row in rows}

    def save_supplement(self, run_id, dispute_id, report, now):
        with self.connect() as db:
            try:
                db.execute('INSERT INTO supplements(run_id,dispute_id,report,created) VALUES (?,?,?,?)',
                           (run_id,dispute_id,json.dumps(report,ensure_ascii=False),now))
            except sqlite3.IntegrityError:
                raise DomainIssue('SUPPLEMENT_CONTESTED')
        return self.load_supplement(run_id, dispute_id)
