package org.example.phonecontroller;

import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * Observes sampled source pixels only. Does not authorize or execute input.
 * Call observe once for each acquired ImageReader source image before closing it.
 * Coordinates are half-open screenshot bounds; buffer offsets start at position().
 */
public final class LocalRegionStability {
  public static final int REQUIRED_FRAMES = 10, GRID = 32, MAX_TARGETS = 64;
  public static final long MIN_STABLE_NS = 600_000_000L, MAX_GAP_NS = 250_000_000L;
  private static final int RING_SIZE = 32, MAX_DIMENSION = 16384;

  public static final class Target {
    public final String id, label, role;
    public final int left, top, right, bottom;
    public Target(String id, String label, String role, int left, int top, int right, int bottom) {
      this.id = id; this.label = label; this.role = role;
      this.left = left; this.top = top; this.right = right; this.bottom = bottom;
    }
  }

  public static final class Region {
    public final String id, label, role, hash;
    public final int left, top, right, bottom;
    public final int physicalLeft, physicalTop, physicalRight, physicalBottom, count;
    public final long stableMs;
    public final boolean ready;
    private Region(State state, int l, int t, int r, int b, long timestamp) {
      Target x = state.target;
      id = x.id; label = x.label; role = x.role;
      left = x.left; top = x.top; right = x.right; bottom = x.bottom;
      physicalLeft = l; physicalTop = t; physicalRight = r; physicalBottom = b;
      count = state.count; stableMs = (timestamp - state.firstNs) / 1_000_000L;
      ready = count >= REQUIRED_FRAMES && timestamp - state.firstNs >= MIN_STABLE_NS;
      hash = String.format(java.util.Locale.ROOT, "%016x", state.hash);
    }
  }

  public static final class Snapshot {
    public final String scope;
    public final long sourceSeq, sourceTimestampNs;
    public final int sourceWidth, sourceHeight;
    public final boolean valid;
    public final List<Region> regions;
    private Snapshot(String scope, long seq, long timestamp, int width, int height,
        boolean valid, List<Region> regions) {
      this.scope = scope; sourceSeq = seq; sourceTimestampNs = timestamp;
      sourceWidth = width; sourceHeight = height; this.valid = valid;
      this.regions = Collections.unmodifiableList(new ArrayList<>(regions));
    }
  }

  private static final class State {
    final Target target;
    int count;
    long firstNs, hash;
    State(Target target) { this.target = target; }
    void reset() { count = 0; firstNs = 0; hash = 0; }
    void sample(long value, long timestamp) {
      if (count == 0 || value != hash) { count = 1; firstNs = timestamp; }
      else if (count < Integer.MAX_VALUE) { count++; }
      hash = value;
    }
  }

  private String scope;
  private int shotWidth, shotHeight, width, height, pixelStride, rowStride;
  private long lastSeq = -1, lastTimestamp = -1;
  private final LinkedHashMap<String, State> targets = new LinkedHashMap<>();
  private final LinkedHashMap<Long, Snapshot> ring = new LinkedHashMap<>();

  /**
   * Configure the current capture-generation + task-barrier scope.
   * Repeated <=3 screenshot-pixel jitter preserves the ORIGINAL accepted ROI,
   * rather than following a drifting region. Other target changes reset current target states, preserving immutable source history.
   * Invalid configuration fails closed and throws IllegalArgumentException.
   */
  public synchronized void configure(String scope, int screenshotWidth, int screenshotHeight,
      List<Target> candidates) {
    try {
      if (scope == null || scope.isEmpty() || !dimension(screenshotWidth)
          || !dimension(screenshotHeight) || candidates == null || candidates.size() > MAX_TARGETS) {
        throw new IllegalArgumentException("invalid region configuration");
      }
      LinkedHashMap<String, State> next = new LinkedHashMap<>();
      boolean epoch = !scope.equals(this.scope) || screenshotWidth != shotWidth
          || screenshotHeight != shotHeight;
      for (Target t : candidates) {
        if (t == null || t.id == null || t.id.isEmpty() || t.label == null || t.role == null
            || t.left < 0 || t.top < 0 || t.right <= t.left || t.bottom <= t.top
            || t.right > screenshotWidth || t.bottom > screenshotHeight
            || next.containsKey(t.id)) {
          throw new IllegalArgumentException("invalid or duplicate target");
        }
        State old = epoch ? null : targets.get(t.id);
        if (old != null && equivalent(old.target, t)) next.put(t.id, old);
        else { next.put(t.id, new State(t)); }
      }
      if (epoch) {
        lastSeq = lastTimestamp = -1;
        width = height = pixelStride = rowStride = 0;
      }
      this.scope = scope; shotWidth = screenshotWidth; shotHeight = screenshotHeight;
      targets.clear(); targets.putAll(next);
      // Async OCR may still reference frames sampled before this configuration.
      // Only scope/geometry boundaries retire their immutable source facts.
      if (epoch) ring.clear();
    } catch (IllegalArgumentException error) {
      clear(); throw error;
    }
  }

  private static boolean dimension(int x) { return x > 0 && x <= MAX_DIMENSION; }

  private static boolean equivalent(Target a, Target b) {
    return a.label.equals(b.label) && a.role.equals(b.role)
        && Math.abs((long)a.left - b.left) <= 3 && Math.abs((long)a.top - b.top) <= 3
        && Math.abs((long)a.right - b.right) <= 3 && Math.abs((long)a.bottom - b.bottom) <= 3;
  }

  private void resetObservations() {
    for (State s : targets.values()) s.reset();
    ring.clear();
  }

  /**
   * Buffer must contain complete RGBA source pixels; alpha is intentionally ignored.
   * Invalid geometry/buffer/order returns valid=false and retires all ready history.
   * Exact duplicate sequence OR timestamp returns invalid without advancing counters.
   * Source high-water marks are never lowered by a stale/replayed source frame.
   */
  public synchronized Snapshot observe(String scope, long seq, long timestampNs,
      ByteBuffer rgba, int sourceWidth, int sourceHeight, int pixelStride, int rowStride) {
    if (!Objects.equals(this.scope, scope) || this.scope == null || seq < 0 || timestampNs < 0) {
      resetObservations();
      return invalid(scope, seq, timestampNs, sourceWidth, sourceHeight);
    }
    if (seq < lastSeq || timestampNs < lastTimestamp) {
      resetObservations();
      return invalid(scope, seq, timestampNs, sourceWidth, sourceHeight);
    }
    if (!validBuffer(rgba, sourceWidth, sourceHeight, pixelStride, rowStride)) {
      resetObservations();
      // A malformed real source image still advances its high-water mark.
      lastSeq = Math.max(lastSeq, seq); lastTimestamp = Math.max(lastTimestamp, timestampNs);
      return invalid(scope, seq, timestampNs, sourceWidth, sourceHeight);
    }
    if (seq == lastSeq || timestampNs == lastTimestamp) {
      return invalid(scope, seq, timestampNs, sourceWidth, sourceHeight);
    }
    boolean geometry = width != sourceWidth || height != sourceHeight
        || this.pixelStride != pixelStride || this.rowStride != rowStride;
    if (geometry || (lastTimestamp >= 0 && timestampNs - lastTimestamp > MAX_GAP_NS)) {
      resetObservations();
    }
    width = sourceWidth; height = sourceHeight;
    this.pixelStride = pixelStride; this.rowStride = rowStride;
    lastSeq = seq; lastTimestamp = timestampNs;
    ArrayList<Region> rows = new ArrayList<>(targets.size());
    try {
      for (State s : targets.values()) {
        Target t = s.target;
        int l = (int)((long)t.left * width / shotWidth);
        int top = (int)((long)t.top * height / shotHeight);
        int right = (int)(((long)t.right * width + shotWidth - 1) / shotWidth);
        int bottom = (int)(((long)t.bottom * height + shotHeight - 1) / shotHeight);
        long hash = sample(rgba, l, top, right, bottom, pixelStride, rowStride, 0xcbf29ce484222325L);
        hash = sample(rgba, Math.max(0, l - 3), Math.max(0, top - 3),
            Math.min(width, right + 3), Math.min(height, bottom + 3),
            pixelStride, rowStride, hash);
        s.sample(hash, timestampNs);
        rows.add(new Region(s, l, top, right, bottom, timestampNs));
      }
    } catch (IndexOutOfBoundsException | IllegalArgumentException error) {
      resetObservations();
      return invalid(scope, seq, timestampNs, sourceWidth, sourceHeight);
    }
    Snapshot answer = new Snapshot(scope, seq, timestampNs, sourceWidth, sourceHeight, true, rows);
    ring.put(timestampNs, answer);
    while (ring.size() > RING_SIZE) ring.remove(ring.keySet().iterator().next());
    return answer;
  }

  private static boolean validBuffer(ByteBuffer b, int w, int h, int ps, int rs) {
    if (b == null || !dimension(w) || !dimension(h) || ps < 4 || rs <= 0) return false;
    long rowBytes = (long)(w - 1) * ps + 4;
    long end = (long)b.position() + (long)(h - 1) * rs + rowBytes;
    return rowBytes <= rs && end <= b.limit();
  }

  private static long sample(ByteBuffer b, int left, int top, int right, int bottom,
      int ps, int rs, long hash) {
    int base = b.position(), w = right - left, h = bottom - top;
    for (int y = 0; y < GRID; y++) {
      int sy = top + (int)((long)(2 * y + 1) * h / (2 * GRID));
      for (int x = 0; x < GRID; x++) {
        int sx = left + (int)((long)(2 * x + 1) * w / (2 * GRID));
        int offset = (int)((long)base + (long)sy * rs + (long)sx * ps);
        hash = (hash ^ (b.get(offset) & 255)) * 0x100000001b3L;
        hash = (hash ^ (b.get(offset + 1) & 255)) * 0x100000001b3L;
        hash = (hash ^ (b.get(offset + 2) & 255)) * 0x100000001b3L;
      }
    }
    return hash;
  }

  private static Snapshot invalid(String scope, long seq, long timestamp, int w, int h) {
    return new Snapshot(scope, seq, timestamp, w, h, false, Collections.emptyList());
  }

  /** An exact-source, immutable historical report; absent after reset or ring eviction. */
  public synchronized Snapshot snapshotAt(long sourceTimestampNs) { return ring.get(sourceTimestampNs); }

  public synchronized void clear() {
    scope = null; targets.clear(); ring.clear();
    shotWidth = shotHeight = width = height = pixelStride = rowStride = 0;
    lastSeq = lastTimestamp = -1;
  }
}
