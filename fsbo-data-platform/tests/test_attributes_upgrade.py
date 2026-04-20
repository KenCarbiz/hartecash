from fsbo.enrichment.attributes import extract
from fsbo.sources.base import NormalizedListing


def _l(desc: str) -> NormalizedListing:
    return NormalizedListing(source="t", external_id="x", url="http://x", description=desc)


def test_life_event_moving():
    a = extract(_l("Moving out of state, need to sell quickly"))
    assert a.life_event == "moving"


def test_life_event_divorce():
    a = extract(_l("Going through divorce, car must go"))
    assert a.life_event == "divorce"


def test_life_event_job_transfer():
    a = extract(_l("New job in Denver, company relocating me next month"))
    assert a.life_event == "job_transfer"


def test_life_event_need_cash():
    a = extract(_l("Medical bills piling up, need cash"))
    assert a.life_event == "need_cash"


def test_life_event_going_electric():
    a = extract(_l("Bought a Tesla, switching to EV"))
    assert a.life_event == "going_electric"


def test_life_event_must_sell():
    a = extract(_l("Must sell this week, make me an offer"))
    assert a.life_event == "must_sell"


def test_registration_expiring():
    a = extract(_l("Tags expire next month, need to register or sell"))
    assert a.registration_expiring is True


def test_no_life_event_stays_none():
    a = extract(_l("2018 Civic, great car, serious inquiries only"))
    assert a.life_event is None


def test_life_event_dict_serialization():
    a = extract(_l("Moving out of state. Tags expire soon."))
    d = a.as_dict()
    assert d["life_event"] == "moving"
    assert d["registration_expiring"] is True
