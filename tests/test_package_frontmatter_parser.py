from tools.package_localized_country import _metadata


def test_metadata_accepts_indented_scalar_continuation():
    result = _metadata("---\nexcerpt: first part\n  second part\nasset: xauusd\n---\nbody\n")
    assert result["excerpt"] == "first part second part"

