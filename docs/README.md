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

## Cache de resultados processados de artistas

A busca de artista usa o próprio S3 privado como read-through cache. Uma chave
exata é obtida com NFKC, remoção/compactação de espaços e `casefold`; o texto
normalizado é convertido em SHA-256, sem fuzzy matching. O pequeno índice fica
em `cache/artist-search/v1/<sha256>.json` e referencia o documento já existente
em `processed/enriched/artists/...`. O TTL lógico padrão é de 24 horas (86.400
segundos) e pode ser alterado com `SOUNDSCOPE_ARTIST_CACHE_TTL_SECONDS`.

Em um **HIT**, somente o índice e o processed são lidos. O documento é validado
e desserializado nos mesmos modelos usados pelo pipeline; nenhuma API externa e
nenhuma escrita RAW, processed ou DynamoDB é executada. Em **MISS** ou **STALE**,
o pipeline existente roda sem alterações e publica o índice apenas depois de
terminar e persistir o processed com sucesso. Ausência, JSON inválido,
referência quebrada, incompatibilidade de schema ou erro S3 são falhas abertas:
ficam registrados apenas de forma técnica e a busca segue pelo pipeline normal.

O índice guarda versão, referência processed, instante UTC e somente a metadata
operacional necessária para reconstruir a resposta. Não armazena biografia,
payload RAW, credenciais, tokens ou chaves de API. O processed continua sendo a
fonte do perfil completo e o mesmo `EnrichedArtist` alimenta a serialização em
HIT e MISS; portanto, o contrato HTTP não ganha um segundo formato.
