# Frontend

Interface estática do SoundScope feita com HTML, CSS e JavaScript puros. Abra-a por um servidor HTTP local (não diretamente pelo protocolo `file://`):

```bash
python -m http.server 8080 --directory frontend
```

Depois, acesse `http://localhost:8080`. A URL pública da API e o timeout ficam nas constantes no início de `js/app.js`.

`Meu SoundScope` consulta a Spotify Web API diretamente no navegador. As últimas 20 reproduções usam `/v1/me/player/recently-played` e `user-read-recently-played`, com cache descartável de 45 segundos em `sessionStorage`; reconecte o Spotify para conceder o scope após esta atualização. O histórico nunca passa pelo backend do SoundScope.

`Minha Órbita` reutiliza, sem nova chamada HTTP, os dez Top Artists normalizados e armazenados por período pelo módulo de insights. A visualização browser-only está isolada em `js/spotify-orbit.js`; ranking controla somente hierarquia visual, e nenhum dado quantitativo é inferido.

## SoundScope Share V1

Em `Minha Órbita`, **Compartilhar minha órbita** reutiliza até os cinco primeiros artistas já normalizados e monta localmente um Canvas de 1080 × 1920. O navegador converte o Canvas em PNG e oferece o arquivo ao Web Share do dispositivo quando compatível; nos demais casos, faz o download de `soundscope-minha-orbita.png`.

O fluxo é inteiramente browser-only (`Minha Órbita → Canvas local → PNG → Web Share / Download`): não faz uma nova chamada à API do Spotify, não cria endpoint e não envia artistas, imagem, token ou qualquer dado pessoal ao backend.
