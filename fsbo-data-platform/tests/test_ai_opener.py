from fsbo.ai.opener import _fallback, _prompt
from fsbo.models import Listing


def test_fallback_no_api_key(monkeypatch):
    """When no anthropic key is set, _fallback returns a deterministic opener."""
    listing = Listing(
        source="craigslist",
        external_id="x",
        url="http://x",
        year=2020,
        make="Toyota",
        model="Tacoma",
    )
    msg = _fallback(listing)
    assert "2020 Toyota Tacoma" in msg
    assert "cash offer" in msg.lower()


def test_prompt_includes_key_context():
    listing = Listing(
        source="facebook_marketplace",
        external_id="x",
        url="http://x",
        year=2019,
        make="Honda",
        model="CR-V",
        mileage=45000,
        city="Orlando",
        state="FL",
        description="One owner, non-smoker, clean Carfax. 45k highway miles.",
    )
    prompt = _prompt(listing, "friendly")
    assert "2019 Honda CR-V" in prompt
    assert "Orlando" in prompt
    assert "45000" in prompt
    assert "one owner" in prompt.lower()
    assert "friendly" in prompt
