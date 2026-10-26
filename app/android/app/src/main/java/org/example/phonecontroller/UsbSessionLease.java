package org.example.phonecontroller;

import java.util.UUID;

/** Connection consent expires at detach, even for an immediate same-board attach. */
public final class UsbSessionLease {
    private long generation;
    private String serial;
    private String session;
    public synchronized long generation() { return generation; }
    public synchronized String attach(String value) {
        if (!value.equals(serial) || session == null) {
            serial = value;
            session = value + ":" + generation + ":" + UUID.randomUUID();
        }
        return session;
    }
    public synchronized String detach() {
        String previous = session;
        generation++;
        serial = null;
        session = null;
        return previous;
    }
    public synchronized boolean matches(String value) {
        return value != null && value.equals(session);
    }
}
