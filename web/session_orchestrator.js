(function () {
  const STORAGE_KEY = "second_brain.active_session";
  const DEFAULT_STATE = Object.freeze({
    activeCaseId: null,
    activeRunId: null,
    activeAnnotationId: null,
    activeLocale: null,
    activeCategory: null,
    activeCaseStatus: null,
    activeRubrics: [],
    activeCandidates: [],
    activeGoldenSource: null,
    activeScoring: null,
    lastUpdatedAt: null,
  });

  const subscribers = new Set();

  function clone(value) {
    if (value === undefined) {
      return undefined;
    }
    try {
      return JSON.parse(JSON.stringify(value));
    } catch {
      return value;
    }
  }

  function normalize(candidate = {}) {
    return {
      ...DEFAULT_STATE,
      ...candidate,
      activeRubrics: Array.isArray(candidate.activeRubrics) ? candidate.activeRubrics : [],
      activeCandidates: Array.isArray(candidate.activeCandidates) ? candidate.activeCandidates : [],
      lastUpdatedAt: candidate.lastUpdatedAt || null,
    };
  }

  function read() {
    try {
      const raw = window.sessionStorage.getItem(STORAGE_KEY);
      return normalize(raw ? JSON.parse(raw) : {});
    } catch (error) {
      console.warn("[Session] hydrate failed", error);
      return normalize({});
    }
  }

  let current = read();

  function persist(next, eventName) {
    current = normalize(next);
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(current));
    console.info(`[Session] ${eventName}`, clone(current));
    for (const subscriber of subscribers) {
      try {
        subscriber(clone(current));
      } catch (error) {
        console.warn("[Session] subscriber failed", error);
      }
    }
    return clone(current);
  }

  window.Session = {
    get() {
      return clone(current);
    },
    set(next = {}) {
      return persist({ ...DEFAULT_STATE, ...next, lastUpdatedAt: new Date().toISOString() }, "sync");
    },
    patch(partial = {}) {
      return persist({ ...current, ...partial, lastUpdatedAt: new Date().toISOString() }, "patch");
    },
    clear() {
      return persist({ ...DEFAULT_STATE, lastUpdatedAt: new Date().toISOString() }, "clear");
    },
    hydrate() {
      current = read();
      console.info("[Session] hydrate", clone(current));
      return clone(current);
    },
    subscribe(callback) {
      if (typeof callback !== "function") {
        return () => {};
      }
      subscribers.add(callback);
      callback(clone(current));
      return () => subscribers.delete(callback);
    },
  };

  window.Session.hydrate();
})();
