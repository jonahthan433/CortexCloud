/* CortexCloud theme controller — System (default) / Light / Dark.
   - No-flash: runs in <head>, sets <html data-theme> before first paint.
   - System reacts live to OS changes (no reload).
   - Light/Dark persist in localStorage across sessions.
   - Emits window.ccTheme {get,set} for the toggle UI. */
(function () {
  var KEY = "cc-theme";
  var root = document.documentElement;
  var mq = window.matchMedia("(prefers-color-scheme: dark)");
  var light = window.matchMedia("(prefers-color-scheme: light)");
  var meta = document.querySelector('meta[name="theme-color"]');

  function stored() {
    try { var v = localStorage.getItem(KEY); return (v === "light" || v === "dark") ? v : null; }
    catch (e) { return null; }
  }
  // System = the site's native DARK, unless the OS explicitly prefers light.
  // no-preference (headless, older systems) stays dark — it was never light.
  function resolved(pref) { return pref === "light" || pref === "dark" ? pref : (light.matches ? "light" : "dark"); }
  function chrome(theme) { if (meta) meta.setAttribute("content", theme === "dark" ? "#0a0a0a" : "#f6f7f9"); }

  function apply(pref, persist) {
    var theme = resolved(pref);
    root.setAttribute("data-theme", theme);
    root.setAttribute("data-theme-pref", pref || "system");
    chrome(theme);
    if (persist) { try { pref ? localStorage.setItem(KEY, pref) : localStorage.removeItem(KEY); } catch (e) {} }
    // notify the toggle UI so programmatic set() stays in sync
    try { window.dispatchEvent(new CustomEvent("cc-theme-change", { detail: { pref: pref || "system", theme: theme } })); } catch (e) {}
  }

  // 1. Paint the correct theme immediately (no flash).
  apply(stored(), false);

  // 2. System mode: follow OS changes live (listen to both directions).
  function onOSChange() { if (!stored()) apply(null, false); }
  mq.addEventListener ? mq.addEventListener("change", onOSChange) : mq.addListener(onOSChange);
  light.addEventListener ? light.addEventListener("change", onOSChange) : light.addListener(onOSChange);

  // 3. Public API for the toggle.
  window.ccTheme = {
    get: function () { return stored() || "system"; },
    resolved: function () { return root.getAttribute("data-theme"); },
    set: function (pref) { apply(pref, true); }
  };
})();
