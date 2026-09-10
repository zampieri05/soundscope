"""Execução manual da consulta de detalhes de artista no MusicBrainz."""

import argparse
import json

from src.services.musicbrainz.client import MusicBrainzError, get_artist_details


def main() -> None:
    """Consulta o MBID informado e imprime o JSON RAW no terminal."""
    parser = argparse.ArgumentParser(
        description="Consulta detalhes de um artista no MusicBrainz."
    )
    parser.add_argument("mbid", help="MBID retornado pela pesquisa de artista")
    args = parser.parse_args()

    try:
        data = get_artist_details(args.mbid)
    except (ValueError, MusicBrainzError) as error:
        parser.exit(status=1, message=f"Erro: {error}\n")

    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
