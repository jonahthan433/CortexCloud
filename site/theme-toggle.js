/* CortexCloud theme toggle UI. Injects a System/Light/Dark segmented control
   into any element with [data-theme-toggle]. Uses existing .btn styling. */
(function () {
  var OPT = [
    { v: "system", label: "System", icon: "◐" },
    { v: "light",  label: "Light",  icon: "☀" },
    { v: "dark",   label: "Dark",   icon: "☾" }
  ];
  function mount(host) {
    host.setAttribute("role", "group");
    host.setAttribute("aria-label", "Color theme");
    host.innerHTML = OPT.map(function (o) {
      return '<button type="button" class="tt-opt" data-v="' + o.v + '" title="' + o.label + '" aria-label="' + o.label + '">' + o.icon + '</button>';
    }).join("");
    function sync() {
      var cur = window.ccTheme ? window.ccTheme.get() : "system";
      host.querySelectorAll(".tt-opt").forEach(function (b) {
        var on = b.getAttribute("data-v") === cur;
        b.classList.toggle("on", on);
        b.setAttribute("aria-pressed", on ? "true" : "false");
      });
    }
    host.addEventListener("click", function (e) {
      var b = e.target.closest(".tt-opt"); if (!b) return;
      window.ccTheme.set(b.getAttribute("data-v")); sync();
    });
    sync();
    window.addEventListener("cc-theme-change", sync);
  }
  function init() { document.querySelectorAll("[data-theme-toggle]").forEach(mount); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
