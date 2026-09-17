# Documentação

Este diretório receberá decisões de arquitetura, contratos de dados e guias operacionais conforme o projeto evoluir.

Por enquanto, a visão geral, o pipeline planejado e o roadmap estão documentados no [`README.md`](../README.md).

## Resiliência do catálogo MusicBrainz

O cliente MusicBrainz repete, no máximo, três tentativas para HTTP 429, 500,
502, 503 e 504, além de timeouts de conexão/leitura. Cada tentativa passa pelo
rate limiter. O backoff padrão é de 1 e 2 segundos; um `Retry-After` válido é
respeitado com teto de 5 segundos. Erros HTTP permanentes não são repetidos.

A paginação de release groups é tratada como um snapshot indivisível: se
qualquer página continuar indisponível após os retries, todos os release groups
MusicBrainz coletados naquela execução são descartados. O perfil do artista e
um catálogo válido do TheAudioDB ainda podem ser retornados. Isso evita publicar
uma discografia parcial como completa ou persistir páginas intermediárias.

Limitação conhecida do hotfix: o contrato público atual não possui metadata de
completude por catálogo. Por isso, a indisponibilidade da discografia é indicada
nos logs por artista e MBID, sem ampliar o schema; a lista MusicBrainz vazia não
distingue publicamente “sem lançamentos” de “catálogo temporariamente
indisponível”.
