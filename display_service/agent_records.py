"""Generic OCR-bound record identities and durable single-submit bookkeeping.

No actions, models or application-specific branches. The caller must supply
current authorized phone_ocr.frame_hint output and bind app/session to its live
lease. This module validates evidence, never creates permission to press Save.
All times use the caller clock (monotonic by default). A pending reservation is
never erased or retried, even after restart or a new date-window task.
"""
import hashlib
import json
import math
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path


class Pause(RuntimeError):
    pass


def _text(value):
    return isinstance(value,str) and 0 < len(value.strip()) <= 160 and all(ord(c)>=32 for c in value)


def _hash(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()


def _day(value):
    if not isinstance(value,str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}",value):
        raise ValueError("exact source date required")
    return date.fromisoformat(value)


@dataclass(frozen=True)
class OCRProof:
    values: tuple
    frame_id: str
    session: str
    observed_at: float
    raw_lines: tuple = ()



def _normalized(key,raw):
    if not isinstance(raw,str):return None
    text=raw.strip()
    if key in ("date","occurred_at"):
        text=re.sub(r"^(?:交易时间|创建时间|支付时间|记账时间|日期|时间)\s*[:：]?\s*","",text)
        m=re.fullmatch(r"(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?(?:[ T]\s*(\d{2}):(\d{2}):(\d{2}))?",text)
        if not m:return None
        try:day=date(*map(int,m.group(1,2,3))).isoformat()
        except ValueError:return None
        return day if key=="date" else day+"T"+":".join(m.group(4,5,6)) if m[4] else None
    if key=="amount":
        text=re.sub(r"^(?:交易金额|付款金额|收款金额|金额)\s*[:：]?\s*","",text)
        m=re.fullmatch(r"([+-]?)[￥¥]?\s*((?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,2})?)\s*(?:元|人民币|CNY)?",text)
        if not m:return None
        from decimal import Decimal
        return ("-" if m[1]=="-" else "")+format(Decimal(m[2]),".2f")
    if key=="currency":
        return "CNY" if text in ("人民币","元","CNY","￥") else text if re.fullmatch("[A-Z]{3}",text) else None
    prefixes={"order_id":r"(?:订单号|订单编号|交易单号|交易号|流水号)","merchant":r"(?:商户|商家|收款方|交易对方)","book_name":r"(?:账本名称|账本)","account":r"(?:账户|账号)"}
    if key in prefixes:return re.sub("^"+prefixes[key]+r"\s*[:：]\s*","",text)
    return text

def _field_matches(key,raw,value):
    return raw==value or _normalized(key,raw)==value

def _proof(*,values,rows,hint,frame_id,session,observed_at,now):
    if (not isinstance(values,dict) or not values or not isinstance(rows,dict) or set(rows)!=set(values)
            or not all(_text(v) for v in values.values()) or not _text(frame_id) or not _text(session)
            or type(observed_at) not in (int,float) or type(now) not in (int,float)
            or not math.isfinite(observed_at) or not math.isfinite(now) or not 0 <= now-observed_at <= 2.5):
        raise ValueError("fresh exact OCR evidence required")
    if not isinstance(hint,dict) or hint.get("source")!="phone-ocr" or not isinstance(hint.get("lines"),list):
        raise ValueError("authorized phone OCR required")
    lines=hint["lines"]
    for key,value in values.items():
        index=rows[key]
        if type(index) is not int or not 0 <= index < len(lines):
            raise ValueError("OCR row index")
        if not _field_matches(key,lines[index].get("text"),value) or sum(_field_matches(key,r.get("text"),value) for r in lines)!=1:
            raise ValueError("OCR value absent or not unique")
        b=lines[index].get("bounds")
        if not isinstance(b,list) or len(b)!=4 or any(type(v) is not int for v in b) or not 0 <= b[0] < b[2] <= hint.get("width",0) or not 0 <= b[1] < b[3] <= hint.get("height",0):
            raise ValueError("OCR row bounds")
    return OCRProof(tuple(sorted(values.items())),frame_id,session,float(observed_at),tuple((k,rows[k],lines[rows[k]]["text"]) for k in sorted(values)))


@dataclass(frozen=True)
class SourceRecord:
    source: str
    proof: OCRProof
    identity: str
    fingerprint: str


@dataclass(frozen=True)
class TargetBook:
    app: str
    proof: OCRProof
    identity: str
    fingerprint: str


@dataclass(frozen=True)
class SavedProof:
    record_identity: str
    record_fingerprint: str
    book_identity: str
    book_fingerprint: str
    proof: OCRProof


def record_from_ocr(*,source,**evidence):
    if not _text(source):raise ValueError("source application identity")
    proof=_proof(**evidence);v=dict(proof.values)
    required={"date","amount","merchant"}
    if not required <= set(v) or set(v)-required-{"order_id","occurred_at","currency"}:raise ValueError("record fields")
    _day(v["date"])
    if not re.fullmatch(r"-?(?:0|[1-9][0-9]{0,11})\.[0-9]{2}",v["amount"]) or "currency" in v and not re.fullmatch(r"[A-Z]{3}",v["currency"]):raise ValueError("exact amount and currency required")
    if "occurred_at" in v:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",v["occurred_at"]) or datetime.fromisoformat(v["occurred_at"]).date()!=_day(v["date"]):raise ValueError("source timestamp mismatch")
    if not v.get("order_id") and not v.get("occurred_at"):raise ValueError("ambiguous record; order ID or full timestamp required")
    discriminator=["order",v["order_id"]] if v.get("order_id") else ["time",v["occurred_at"],v["merchant"],v["amount"],v.get("currency")]
    return SourceRecord(source,proof,_hash([source,discriminator]),_hash([source,v]))


def book_from_ocr(*,app,**evidence):
    if not _text(app):raise ValueError("target application identity")
    proof=_proof(**evidence);v=dict(proof.values)
    if set(v) not in ({"book_id","book_name"},{"book_name","account"},{"book_name","unique_context"}):raise ValueError("visible unique book identity required")
    identity=[app,v["book_id"]] if "book_id" in v else [app,v]
    return TargetBook(app,proof,_hash(identity),_hash([app,v]))


def saved_from_ocr(record,book,*,app,**evidence):
    if not isinstance(record,SourceRecord) or not isinstance(book,TargetBook) or app!=book.app:raise ValueError("saved proof application mismatch")
    proof=_proof(**evidence);v=dict(proof.values)
    expected=dict(record.proof.values);expected.update(dict(book.proof.values))
    linked=("order_id" in v and v.get("order_id")==expected.get("order_id")) or {"date","amount","merchant"}<=set(v)
    if not linked or set(v)-set(expected)-{"status"} or any(v[k]!=expected[k] for k in v if k!="status") or v.get("status") not in ("已保存","已记账"):
        raise ValueError("explicit saved record and target book evidence required")
    if proof.session!=book.proof.session or proof.session!=record.proof.session:raise ValueError("saved proof session mismatch")
    return SavedProof(record.identity,record.fingerprint,book.identity,book.fingerprint,proof)


def scope_key(source,book,start,end):
    if not _text(source) or not isinstance(book,TargetBook) or _day(start)>_day(end):raise ValueError("record cursor scope")
    return _hash([source,book.identity,start,end])


class RecordJournal:
    def __init__(self,path,*,clock=time.monotonic):
        self.clock=clock;path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        try:
            fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
        except FileExistsError:pass
        self.db=sqlite3.connect(path,timeout=5)
        self.db.execute("PRAGMA journal_mode=WAL");self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS agent_records (identity TEXT NOT NULL,book TEXT NOT NULL,fingerprint TEXT NOT NULL,book_fp TEXT NOT NULL,scope TEXT NOT NULL,state TEXT NOT NULL CHECK(state IN ('pending','saved')),source_frame TEXT NOT NULL,session TEXT NOT NULL,reserved_at REAL NOT NULL,saved_frame TEXT,PRIMARY KEY(identity,book))")
        self.db.execute("CREATE TABLE IF NOT EXISTS agent_cursors (scope TEXT PRIMARY KEY,identity TEXT NOT NULL,book TEXT NOT NULL,processed INTEGER NOT NULL)")
        existing=self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='agent_cursor_items'").fetchone()
        self.db.execute("CREATE TABLE IF NOT EXISTS agent_cursor_items (scope TEXT NOT NULL,identity TEXT NOT NULL,book TEXT NOT NULL,PRIMARY KEY(scope,identity,book))")
        if not existing:
            self.db.execute("INSERT OR IGNORE INTO agent_cursor_items SELECT scope,identity,book FROM agent_records WHERE state='saved' AND scope IN (SELECT scope FROM agent_cursors)")
            self.db.execute("INSERT OR IGNORE INTO agent_cursor_items SELECT scope,identity,book FROM agent_cursors")
        self.db.commit()

    def _valid(self,scope,r,b):
        if not isinstance(scope,str) or not re.fullmatch("[a-f0-9]{64}",scope) or not isinstance(r,SourceRecord) or not isinstance(b,TargetBook):raise ValueError("journal identity")
        if r.proof.session!=b.proof.session:raise Pause("record_book_session_mismatch")

    def _row(self,r,b):
        row=self.db.execute("SELECT fingerprint,book_fp,state,source_frame,session,reserved_at FROM agent_records WHERE identity=? AND book=?",(r.identity,b.identity)).fetchone()
        if row and (row[0]!=r.fingerprint or row[1]!=b.fingerprint):raise Pause("source_or_book_changed_under_same_identity")
        return row

    def decision(self,scope,record,book):
        self._valid(scope,record,book);row=self._row(record,book)
        return "new" if row is None else "skip_saved" if row[2]=="saved" else "pending_reconcile"

    def reserve(self,scope,record,book):
        self._valid(scope,record,book)
        for proof in (book.proof,):
            if not 0 <= self.clock()-proof.observed_at <= 2.5:raise Pause("stale_record_or_target_book")
        self._row(record,book)
        try:
            with self.db:
                self.db.execute("INSERT INTO agent_records VALUES (?,?,?,?,?,'pending',?,?,?,NULL)",(record.identity,book.identity,record.fingerprint,book.fingerprint,scope,record.proof.frame_id,record.proof.session,self.clock()))
        except sqlite3.IntegrityError as error:raise Pause("save_already_submitted_reconcile_first") from error

    def verify_saved(self,scope,record,book,evidence):
        self._valid(scope,record,book)
        if not isinstance(evidence,SavedProof):raise ValueError("live saved OCR proof required; model boolean is not evidence")
        if (evidence.record_identity,evidence.record_fingerprint,evidence.book_identity,evidence.book_fingerprint)!=(record.identity,record.fingerprint,book.identity,book.fingerprint):raise Pause("saved_record_or_book_mismatch")
        proof=evidence.proof
        if proof.session!=record.proof.session or not 0 <= self.clock()-proof.observed_at <= 2.5:raise Pause("saved_evidence_stale_or_foreign")
        with self.db:
            # Serialize the read and insert/update with competing reservations.
            self.db.execute("BEGIN IMMEDIATE")
            row=self._row(record,book)
            if row and (proof.frame_id==row[3] or proof.observed_at<=row[5]):raise Pause("save_requires_post_reservation_new_frame")
            if row:
                self.db.execute("UPDATE agent_records SET state='saved',saved_frame=? WHERE identity=? AND book=?",(proof.frame_id,record.identity,book.identity))
            else:
                self.db.execute("INSERT INTO agent_records VALUES (?,?,?,?,?,'saved',?,?,?,?)",(record.identity,book.identity,record.fingerprint,book.fingerprint,scope,record.proof.frame_id,proof.session,proof.observed_at,proof.frame_id))

    def advance(self,scope,record,book):
        self._valid(scope,record,book)
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            row=self._row(record,book)
            if not row or row[2]!="saved":raise Pause("cursor_requires_verified_saved_record")
            if self.db.execute("SELECT 1 FROM agent_records WHERE scope=? AND state='pending' LIMIT 1",(scope,)).fetchone():raise Pause("cursor_blocked_by_pending_write")
            current=self.cursor(scope)
            added=self.db.execute("INSERT OR IGNORE INTO agent_cursor_items VALUES (?,?,?)",(scope,record.identity,book.identity)).rowcount
            count=self.db.execute("SELECT count(*) FROM agent_cursor_items WHERE scope=?",(scope,)).fetchone()[0]
            if not added and current:
                self.db.execute("UPDATE agent_cursors SET processed=? WHERE scope=?",(count,scope))
                return
            self.db.execute("INSERT INTO agent_cursors VALUES (?,?,?,?) ON CONFLICT(scope) DO UPDATE SET identity=excluded.identity,book=excluded.book,processed=excluded.processed",(scope,record.identity,book.identity,count))

    def cursor(self,scope):
        row=self.db.execute("SELECT identity,book,processed FROM agent_cursors WHERE scope=?",(scope,)).fetchone()
        return None if row is None else dict(identity=row[0],book=row[1],processed=row[2])

    def close(self):self.db.close()
