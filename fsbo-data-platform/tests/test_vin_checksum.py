from fsbo.enrichment.vin_checksum import valid_vin


def test_valid_real_vin():
    # Known valid reference VIN
    assert valid_vin("1M8GDM9AXKP042788")


def test_invalid_length():
    assert not valid_vin("TOOSHORT")
    assert not valid_vin("TOOLONGVINSTRINGLOLOLO")


def test_rejects_illegal_letters():
    # I, O, Q are forbidden in VINs
    assert not valid_vin("1M8GDMIAXKP042788")
    assert not valid_vin("1M8GDMOAXKP042788")
    assert not valid_vin("1M8GDMQAXKP042788")


def test_invalid_checksum():
    # Flip one letter so check digit no longer matches
    assert not valid_vin("1M8GDM9AXKP042789")


def test_empty_or_none():
    assert not valid_vin(None)
    assert not valid_vin("")


def test_lowercase_ok():
    assert valid_vin("1m8gdm9axkp042788")
