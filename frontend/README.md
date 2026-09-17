# Frontend

Interface estática do SoundScope feita com HTML, CSS e JavaScript puros. Abra-a por um servidor HTTP local (não diretamente pelo protocolo `file://`):

```bash
python -m http.server 8080 --directory frontend
```

Depois, acesse `http://localhost:8080`. A URL pública da API e o timeout ficam nas constantes no início de `js/app.js`.

`Meu SoundScope` consulta a Spotify Web API diretamente no navegador. As últimas 20 reproduções usam `/v1/me/player/recently-played` e `user-read-recently-played`, com cache descartável de 45 segundos em `sessionStorage`; reconecte o Spotify para conceder o scope após esta atualização. O histórico nunca passa pelo backend do SoundScope.
