"use strict";
window.SoundScopeAppleMusic = (() => {
  let configured = false;
  async function configure(developerToken) {
    if (!developerToken || !window.MusicKit) throw new Error("APPLE_MUSIC_NOT_CONFIGURED");
    await MusicKit.configure({ developerToken, app: { name: "SoundScope", build: "2.1" } });
    configured = true;
    return MusicKit.getInstance();
  }
  async function authorize() {
    if (!configured) throw new Error("APPLE_MUSIC_NOT_CONFIGURED");
    const music = MusicKit.getInstance();
    const musicUserToken = await music.authorize();
    return { authorized: Boolean(musicUserToken) };
  }
  async function recentlyPlayed(limit = 20) {
    if (!configured) throw new Error("APPLE_MUSIC_NOT_CONFIGURED");
    const response = await MusicKit.getInstance().api.music("/v1/me/recent/played/tracks?limit=" + Math.min(30, limit));
    return response?.data?.data || response?.data || [];
  }
  async function heavyRotation(limit = 20) {
    if (!configured) throw new Error("APPLE_MUSIC_NOT_CONFIGURED");
    const response = await MusicKit.getInstance().api.music("/v1/me/history/heavy-rotation?limit=" + Math.min(30, limit));
    return response?.data?.data || response?.data || [];
  }
  return { configure, authorize, recentlyPlayed, heavyRotation };
})();