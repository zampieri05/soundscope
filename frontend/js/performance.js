"use strict";

/* SoundScope 2.1 input performance guard */
(() => {
  const input = document.querySelector("#artist-input");
  if (!input) return;

  const root = document.documentElement;
  const start = () => root.classList.add("is-typing");
  const stop = () => root.classList.remove("is-typing");

  input.addEventListener("focus", start, { passive: true });
  input.addEventListener("blur", stop, { passive: true });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stop();
    else if (document.activeElement === input) start();
  });
})();
