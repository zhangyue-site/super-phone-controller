"""Short-lived command-only pairing, anchored to a live board-proven session."""
import hashlib
import re
import secrets
import threading
import time

TOKEN = re.compile(r"[A-Za-z0-9_-]{43}\Z")


class Pairings:
    def __init__(self, parent_device, clock=time.monotonic):
        self.parent_device = parent_device
        self.clock = clock
        self.lock = threading.RLock()
        self.codes = {}
        self.tickets = {}

    def _prune(self):
        now = self.clock()
        for entries in (self.codes, self.tickets):
            for token, item in list(entries.items()):
                if item[0] <= now:
                    del entries[token]

    def issue(self, parent):
        device = self.parent_device(parent)
        with self.lock:
            self._prune()
            for token, item in list(self.codes.items()):
                if item[1] == device:
                    del self.codes[token]
            if len(self.codes) >= 256:
                raise ValueError("绑定请求过多，请稍后重试")
            code = secrets.token_urlsafe(32)
            self.codes[code] = (self.clock() + 120, device, parent)
        return {"code": code, "expiresIn": 120, "device": device}

    def redeem(self, code):
        if not isinstance(code, str) or not TOKEN.fullmatch(code):
            raise PermissionError("invalid pairing")
        with self.lock:
            self._prune()
            item = self.codes.pop(code, None)
            if item is None or self.parent_device(item[2]) != item[1]:
                raise PermissionError("expired pairing")
            if len(self.tickets) >= 256:
                raise ValueError("控制连接过多，请稍后重试")
            ticket = secrets.token_urlsafe(32)
            self.tickets[ticket] = (self.clock() + 300, item[1], item[2])
        return {"ticket": ticket, "expiresIn": 300, "device": item[1], "scope": "phone-commands"}

    def owner(self, ticket):
        if not isinstance(ticket, str) or not TOKEN.fullmatch(ticket):
            raise PermissionError("invalid pairing")
        with self.lock:
            self._prune()
            item = self.tickets.get(ticket)
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

    def renew(self, ticket):
        identity = self.owner(ticket)
        with self.lock:
            item = self.tickets.get(ticket)
            if item is None:
                raise PermissionError("expired pairing")
            self.tickets[ticket] = (self.clock() + 300, item[1], item[2])
        return {"expiresIn": 300, "scope": "phone-commands", "device": identity[3]}

    def revoke(self, parent):
        device = self.parent_device(parent)
        with self.lock:
            for entries in (self.codes, self.tickets):
                for token, item in list(entries.items()):
                    if item[1] == device:
                        del entries[token]
        return device
