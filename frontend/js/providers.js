"use strict";
(() => {
  const $ = (s) => document.querySelector(s);
  const toggle = $("#provider-switcher"), panel = $("#provider-panel"), close = $("#provider-close");
  const spotifyAction = $("#provider-spotify-action"), appleAction = $("#apple-music-connect");
  const message = $("#provider-message");
  if (!toggle || !panel) return;
  const setOpen = (open) => { panel.classList.toggle("is-hidden", !open); toggle.setAttribute("aria-expanded", String(open)); };
  toggle.addEventListener("click", () => setOpen(panel.classList.contains("is-hidden")));
  close?.addEventListener("click", () => setOpen(false));
  spotifyAction?.addEventListener("click", () => { setOpen(false); $("#spotify-connect")?.click(); });
  appleAction?.addEventListener("click", async () => {
    message.textContent = "Preparando Apple Music…";
    try {
      const result = await window.SoundScopeAppleMusic?.authorize();
      message.textContent = result?.authorized ? "Apple Music conectado." : "Apple Music ainda precisa ser configurado.";
      if (result?.authorized) $("#provider-apple-state").textContent = "Conectado";
    } catch (error) {
      message.textContent = error.message === "APPLE_MUSIC_NOT_CONFIGURED" ? "Falta configurar a credencial MusicKit do SoundScope." : "Não foi possível conectar ao Apple Music.";
    }
  });
})();