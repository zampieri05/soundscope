from src.pipeline.transformers.lastfm import transform_lastfm_artist
from src.services.artist_resolver import names_compatible


def test_transform_lastfm_artist():
    raw = {"artist": {
        "name": "Fhop Music",
        "url": "https://www.last.fm/music/Fhop+Music",
        "mbid": "",
        "tags": {"tag": [{"name": "gospel"}, {"name": "brazil"}, {"name": "worship"}]},
        "bio": {"summary": "Brazilian worship artist"},
        "image": [],
    }}
    artist = transform_lastfm_artist(raw)
    assert artist.source == "lastfm"
    assert artist.name == "Fhop Music"
    assert artist.genre == "gospel, brazil, worship"
    assert artist.source_artist_id == "https://www.last.fm/music/Fhop+Music"
    assert names_compatible("FHOP", artist.name)
