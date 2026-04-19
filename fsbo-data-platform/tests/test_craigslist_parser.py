from fsbo.sources.craigslist import CraigslistSource


def test_extract_year():
    assert CraigslistSource._extract_year("2018 Ford F-150 for sale") == 2018
    assert CraigslistSource._extract_year("No year here") is None
    assert CraigslistSource._extract_year("1989 Civic") == 1989


def test_extract_price():
    assert CraigslistSource._extract_price("$12,500") == 12500
    assert CraigslistSource._extract_price("price: $ 8500") == 8500
    assert CraigslistSource._extract_price("no price") is None


def test_extract_mileage():
    assert CraigslistSource._extract_mileage("120,000 miles") == 120000
    assert CraigslistSource._extract_mileage("45000 mi") == 45000
    assert CraigslistSource._extract_mileage("no miles") is None


def test_extract_vin():
    assert CraigslistSource._extract_vin("VIN: 1HGBH41JXMN109186") == "1HGBH41JXMN109186"
    assert CraigslistSource._extract_vin("no vin") is None


def test_extract_id():
    url = "https://tampa.craigslist.org/hil/cto/d/tampa-ford-f150/7712345678.html"
    assert CraigslistSource._extract_id(url) == "7712345678"
