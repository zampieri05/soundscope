"""Execução manual da extração de álbuns do TheAudioDB."""

import argparse
import json

from src.services.theaudiodb.client import TheAudioDBError, search_albums


def main() -> None:
    """Consulta o identificador informado e imprime o JSON RAW no terminal."""
    parser = argparse.ArgumentParser(
        description="Consulta os álbuns de um artista no TheAudioDB."
    )
    parser.add_argument(
        "artist_id",
        help="idArtist retornado pela pesquisa de artista, por exemplo: 111279",
    )
    args = parser.parse_args()

    try:
        data = search_albums(args.artist_id)
    except (ValueError, TheAudioDBError) as error:
        parser.exit(status=1, message=f"Erro: {error}\n")

    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
