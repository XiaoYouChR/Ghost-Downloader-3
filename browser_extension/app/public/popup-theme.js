(() => {
  const key = "gd4bThemePreference";
  const root = document.documentElement;
  const meta = document.querySelector('meta[name="color-scheme"]');
  const listeners = new Set();
  let hasNewPreference = false;

  function apply(value) {
    const preference = value === "light" || value === "dark" ? value : "system";
    root.dataset.theme = preference;
    meta.content = preference === "system" ? "light dark" : preference;
    for (const notify of listeners) {
      notify();
    }
  }

  function cachePreference(value) {
    apply(value);
    try {
      if (root.dataset.theme === "system") {
        localStorage.removeItem(key);
      } else {
        localStorage.setItem(key, value);
      }
    } catch {
      // Private browsing can deny synchronous storage.
    }
  }

  // Extension storage is asynchronous; its mirror supplies the first paint.
  try {
    apply(localStorage.getItem(key));
  } catch {
    apply("system");
  }

  chrome.storage.local.get(key).then(stored => {
    if (!hasNewPreference) {
      cachePreference(stored[key]);
    }
  }).catch(() => {});

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === "local" && key in changes) {
      hasNewPreference = true;
      cachePreference(changes[key].newValue);
    }
  });

  window.popupTheme = {
    getSnapshot: () => root.dataset.theme,
    subscribe(notify) {
      listeners.add(notify);
      return () => listeners.delete(notify);
    },
    setPreference(value) {
      hasNewPreference = true;
      cachePreference(value);
      return chrome.storage.local.set({[key]: value});
    },
  };
})();
