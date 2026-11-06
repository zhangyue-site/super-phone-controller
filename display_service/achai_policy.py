"""Cloud-side date fence and durable single-submit journal, without UI actions.

The gateway must supply an exact observed source date and a namespaced receipt
identity hash (book + source order), never a screen coordinate as identity.
A pending row is not a successful save and must be reconciled after a restart.
"""
import os,re,sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

class Pause(RuntimeError):pass

def exact_day(value):
 if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):raise ValueError('Exact source date required')
 return date.fromisoformat(value)

@dataclass(frozen=True)
class DateWindow:
 start:str
 end:str
 def __post_init__(self):
  if exact_day(self.start)>exact_day(self.end):raise ValueError('Start date exceeds end date')
 def classify(self,observed_day):
  try:day=exact_day(observed_day)
  except (ValueError,TypeError) as error:raise Pause('unknown_source_date') from error
  if day>exact_day(self.end):return 'skip_newer'
  if day<exact_day(self.start):return 'pause_before_start'
  return 'eligible'

class SaveJournal:
 def __init__(self,path):
  path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
  try:
   fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd)
  except FileExistsError:pass
  self.db=sqlite3.connect(path,timeout=5)
  self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA synchronous=FULL')
  self.db.execute("CREATE TABLE IF NOT EXISTS submissions(identity TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('pending','saved')))");self.db.commit()
 @staticmethod
 def _valid(identity,fingerprint):
  if any(not isinstance(v,str) or not re.fullmatch('[0-9a-f]{64}',v) for v in (identity,fingerprint)):raise Pause('invalid_receipt_identity')
 def state(self,identity,fingerprint):
  self._valid(identity,fingerprint)
  row=self.db.execute('SELECT fingerprint,state FROM submissions WHERE identity=?',(identity,)).fetchone()
  if row and row[0]!=fingerprint:raise Pause('source_changed_under_same_order')
  return row[1] if row else None
 def reserve(self,identity,fingerprint):
  self._valid(identity,fingerprint)
  # UNIQUE identity is the atomic fence across workers/processes. It is committed
  # before the gateway is allowed to press Save, and never automatically deleted.
  try:
   with self.db:self.db.execute("INSERT INTO submissions VALUES (?,?,'pending')",(identity,fingerprint))
  except sqlite3.IntegrityError as error:raise Pause('save_already_submitted_reconcile_first') from error
 def verify(self,identity,fingerprint,*,verified):
  if verified is not True:raise Pause('save_result_uncertain')
  state=self.state(identity,fingerprint)
  if state not in ('pending','saved'):raise Pause('save_was_not_reserved')
  with self.db:
   self.db.execute("UPDATE submissions SET state='saved' WHERE identity=? AND fingerprint=?",(identity,fingerprint))
 def close(self):self.db.close()
