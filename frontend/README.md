# Frontend

Interface estática do SoundScope feita com HTML, CSS e JavaScript puros. Abra-a por um servidor HTTP local (não diretamente pelo protocolo `file://`):

```bash
python -m http.server 8080 --directory frontend
```

Depois, acesse `http://localhost:8080`. A URL pública da API e o timeout ficam nas constantes no início de `js/app.js`.
