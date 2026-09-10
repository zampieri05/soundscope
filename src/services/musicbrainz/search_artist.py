"""Execução manual da pesquisa de artista no MusicBrainz."""

import argparse
import json

from src.services.musicbrainz.client import MusicBrainzError, search_artist


def main() -> None:
    """Pesquisa o argumento informado e imprime o JSON RAW no terminal."""
    parser = argparse.ArgumentParser(description="Pesquisa um artista no MusicBrainz.")
    parser.add_argument("artist_name", help="nome do artista, por exemplo: Metallica")
    args = parser.parse_args()

    try:
        data = search_artist(args.artist_name)
    except (ValueError, MusicBrainzError) as error:
        parser.exit(status=1, message=f"Erro: {error}\n")

    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
