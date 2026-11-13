"""Short-lived command-only pairing, anchored to a live board-proven session."""
import hashlib
import re
import secrets
import threading
import time
import sqlite3
import os
from pathlib import Path

TOKEN = re.compile(r"[A-Za-z0-9_-]{43}\Z")


class Pairings:
    def __init__(self, parent_device, clock=time.monotonic, path=None):
        self.parent_device = parent_device
        self.clock = clock
        self.lock = threading.RLock()
        self.codes = {}
        self.tickets = {}
        self.parents = {}
        self.attempts = {}
        if path is not None:
            path = Path(path);path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.db = sqlite3.connect(str(path) if path else ':memory:', check_same_thread=False, timeout=10)
        if path is not None:os.chmod(path,0o600)
        self.db.execute('CREATE TABLE IF NOT EXISTS pairings (device TEXT PRIMARY KEY, code TEXT UNIQUE NOT NULL, generation INTEGER NOT NULL DEFAULT 0)')
        columns={r[1] for r in self.db.execute('PRAGMA table_info(pairings)')}
        if 'generation' not in columns:self.db.execute('ALTER TABLE pairings ADD COLUMN generation INTEGER NOT NULL DEFAULT 0')
        self.db.execute('CREATE TABLE IF NOT EXISTS bindings (token_hash TEXT PRIMARY KEY, device TEXT NOT NULL, generation INTEGER NOT NULL)')
        self.db.commit()

    def _prune(self):
        now = self.clock()
        for entries in (self.codes, self.tickets):
            for token, item in list(entries.items()):
                if item[0] <= now:
                    del entries[token]

    def attach(self,parent):
        """Associate a current board-proven session without issuing credentials."""
        with self.lock:
            device=self.parent_device(parent)
            self.parents[device]=parent
        return device

    def issue(self, parent, rotate=False):
        device = self.parent_device(parent)
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                row=self.db.execute('SELECT code FROM pairings WHERE device=?',(device,)).fetchone()
                old=row[0] if row else None
                if old is None or rotate:
                    used={r[0] for r in self.db.execute('SELECT code FROM pairings')}
                    available=[f'{n:04d}' for n in range(10000) if f'{n:04d}' not in used and f'{n:04d}' != old]
                    if not available:raise ValueError('绑定请求过多，请稍后重试')
                    code=secrets.choice(available)
                    self.db.execute('INSERT INTO pairings(device,code) VALUES (?,?) ON CONFLICT(device) DO UPDATE SET code=excluded.code,generation=pairings.generation+1',(device,code))
                else:code=old
                if rotate:self.db.execute('DELETE FROM bindings WHERE device=?',(device,))
                self.db.commit()
            except Exception:
                self.db.rollback();raise
            if rotate:self._revoke_device(device)
            self.parents[device]=parent
        return {'code':code,'expiresIn':None,'device':device,'persistent':True}

    def issue_legacy(self,parent):
        device=self.parent_device(parent)
        self.issue(parent)
        with self.lock:
            self._prune()
            for token,item in list(self.codes.items()):
                if item[1]==device:del self.codes[token]
            if len(self.codes)>=256:raise ValueError('绑定请求过多，请稍后重试')
            code=secrets.token_urlsafe(32)
            generation=self.db.execute('SELECT generation FROM pairings WHERE device=?',(device,)).fetchone()[0]
            self.codes[code]=(self.clock()+120,device,parent,generation)
        return {'code':code,'expiresIn':120,'device':device}

    def rotate(self,parent):
        return self.issue(parent,rotate=True)

    def redeem(self, code, client='unknown'):
        with self.lock:
            self._prune()
            now=self.clock()
            self.attempts={k:v for k,v in self.attempts.items() if now-v[0]<60}
            for key,limit in (('__global__',100),(str(client),10)):
                start,count=self.attempts.get(key,(now,0))
                if now-start>=60:start,count=now,0
                if count>=limit:raise PermissionError('pairing throttled')
            for key in {'__global__',str(client)}:
                start,count=self.attempts.get(key,(now,0))
                self.attempts[key]=(now,1) if now-start>=60 else (start,count+1)
            item=None
            pin=isinstance(code,str) and re.fullmatch(r'[0-9]{4}',code)
            if pin:
                row=self.db.execute('SELECT device,generation FROM pairings WHERE code=?',(code,)).fetchone()
                if row:item=(0,row[0],self.parents.get(row[0]),row[1])
            elif isinstance(code,str) and TOKEN.fullmatch(code):
                item=self.codes.pop(code,None)
            if item is None or len(item)!=4 or item[2] is None or self.parent_device(item[2])!=item[1]:
                raise PermissionError('expired pairing')
            if len(self.tickets)>=256:raise ValueError('控制连接过多，请稍后重试')
            self.db.execute('BEGIN IMMEDIATE')
            try:
                row=self.db.execute('SELECT code,generation FROM pairings WHERE device=?',(item[1],)).fetchone()
                if row is None or row[1]!=item[3] or (pin and row[0]!=code):raise PermissionError('revoked pairing')
                generation=item[3]
                if self.db.execute('SELECT count(*) FROM bindings WHERE device=? AND generation=?',(item[1],generation)).fetchone()[0]>=256:
                    raise ValueError('控制连接过多，请先解除旧绑定')
                ticket=secrets.token_urlsafe(32);binding=secrets.token_urlsafe(32)
                self.db.execute('DELETE FROM bindings WHERE device=? AND generation<>?',(item[1],generation))
                self.db.execute('INSERT INTO bindings VALUES (?,?,?)',(hashlib.sha256(binding.encode()).hexdigest(),item[1],generation))
                self.db.commit()
            except Exception:
                self.db.rollback();raise
            self.tickets[ticket]=(now+300,item[1],item[2],generation)
        return {'ticket':ticket,'expiresIn':300,'device':item[1],'scope':'phone-commands','bindingToken':binding}

    def restore(self,binding):
        if not isinstance(binding,str) or not TOKEN.fullmatch(binding):raise PermissionError('invalid binding')
        with self.lock:
            self._prune()
            token_hash=hashlib.sha256(binding.encode()).hexdigest()
            query='SELECT b.device,b.generation FROM bindings b JOIN pairings p ON p.device=b.device AND p.generation=b.generation WHERE b.token_hash=?'
            row=self.db.execute(query,(token_hash,)).fetchone()
            if row is None:raise PermissionError('revoked binding')
            device,generation=row
            parent=self.parents.get(device)
            if parent is None or self.parent_device(parent)!=device:raise PermissionError('inactive target')
            if len(self.tickets)>=256:raise ValueError('控制连接过多，请稍后重试')
            self.db.execute('BEGIN IMMEDIATE')
            try:
                if self.db.execute(query,(token_hash,)).fetchone()!=row:raise PermissionError('revoked binding')
                ticket=secrets.token_urlsafe(32)
                self.tickets[ticket]=(self.clock()+300,device,parent,generation)
                self.db.commit()
            except Exception:
                self.db.rollback();raise
        return {'ticket':ticket,'expiresIn':300,'device':device,'scope':'phone-commands','bindingToken':binding}

    def owner(self, ticket):
        if not isinstance(ticket, str) or not TOKEN.fullmatch(ticket):
            raise PermissionError("invalid pairing")
        with self.lock:
            self._prune()
            item = self.tickets.get(ticket)
            if item is not None and len(item)>3 and item[3] is not None:
                row=self.db.execute('SELECT generation FROM pairings WHERE device=?',(item[1],)).fetchone()
                if row is None or row[0]!=item[3]:raise PermissionError('revoked pairing')
            if item is None or self.parent_device(item[2]) != item[1]:
                raise PermissionError("expired pairing")
        principal = hashlib.sha256(ticket.encode()).hexdigest()
        return ("android-app", principal, principal, item[1])

    def allowed(self, identity):
        with self.lock:
            self._prune()
            tokens = list(self.tickets)
        for token in tokens:
            if hashlib.sha256(token.encode()).hexdigest() != identity[1]:
                continue
            try:
                return self.owner(token) == tuple(identity)
            except PermissionError:
                return False
        return False

    def renew(self,ticket):
        with self.lock:
            identity=self.owner(ticket)
            item=self.tickets.get(ticket)
            self.db.execute('BEGIN IMMEDIATE')
            try:
                row=self.db.execute('SELECT generation FROM pairings WHERE device=?',(item[1],)).fetchone()
                if len(item)!=4 or row is None or row[0]!=item[3]:raise PermissionError('revoked pairing')
                self.tickets[ticket]=(self.clock()+300,*item[1:])
                self.db.commit()
            except Exception:
                self.db.rollback();raise
        return {'expiresIn':300,'scope':'phone-commands','device':identity[3]}

    def _revoke_device(self,device):
        for entries in (self.codes,self.tickets):
            for token,item in list(entries.items()):
                if item[1]==device:del entries[token]

    def revoke(self,parent):
        device=self.parent_device(parent)
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                self.db.execute('UPDATE pairings SET generation=generation+1 WHERE device=?',(device,))
                self.db.execute('DELETE FROM bindings WHERE device=?',(device,))
                self.db.commit()
            except Exception:
                self.db.rollback();raise
            self._revoke_device(device)
        return device
