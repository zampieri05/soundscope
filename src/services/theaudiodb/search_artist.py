"""Execução manual da primeira extração do SoundScope."""

import argparse
import json

from src.services.theaudiodb.client import TheAudioDBError, search_artist


def main() -> None:
    """Pesquisa o argumento informado e imprime o JSON RAW no terminal."""
    parser = argparse.ArgumentParser(description="Pesquisa um artista no TheAudioDB.")
    parser.add_argument("artist_name", help="nome do artista, por exemplo: Metallica")
    args = parser.parse_args()

    try:
        data = search_artist(args.artist_name)
    except (ValueError, TheAudioDBError) as error:
        parser.exit(status=1, message=f"Erro: {error}\n")

    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
