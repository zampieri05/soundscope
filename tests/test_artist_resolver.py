from src.services.artist_resolver import comparable_name, names_compatible, query_variants


def test_query_variants_adds_music_suffix():
    assert query_variants("FHOP") == ["FHOP", "FHOP Music"]


def test_query_variants_can_remove_music_suffix():
    assert query_variants("fhop music") == ["fhop music", "fhop"]


def test_names_compatible_accepts_music_suffix_alias():
    assert names_compatible("FHOP", "fhop music")


def test_names_compatible_rejects_unrelated_artist():
    assert not names_compatible("FHOP", "Hillsong Worship")


def test_comparable_name_normalizes_case_spacing_and_punctuation():
    assert comparable_name("  F.H.O.P  ") == "f h o p"
