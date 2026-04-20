import httpx
import pytest
import respx

from fsbo.enrichment.vin import decode_vin


@pytest.mark.asyncio
async def test_decode_vin_success():
    vin = "1HGBH41JXMN109186"
    mock_response = {
        "Results": [
            {
                "ModelYear": "2020",
                "Make": "HONDA",
                "Model": "Accord",
                "Trim": "Sport",
                "BodyClass": "Sedan/Saloon",
                "ErrorCode": "0",
                "ErrorText": "",
            }
        ]
    }
    with respx.mock(assert_all_called=True) as mock:
        mock.get(f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}").mock(
            return_value=httpx.Response(200, json=mock_response)
        )
        result = await decode_vin(vin)

    assert result is not None
    assert result.year == 2020
    assert result.make == "HONDA"
    assert result.model == "Accord"
    assert result.trim == "Sport"


@pytest.mark.asyncio
async def test_decode_vin_bad_length():
    assert await decode_vin("TOOSHORT") is None
    assert await decode_vin("") is None


@pytest.mark.asyncio
async def test_decode_vin_http_failure():
    vin = "1HGBH41JXMN109186"
    with respx.mock() as mock:
        mock.get(f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}").mock(
            return_value=httpx.Response(500)
        )
        result = await decode_vin(vin)
    assert result is None
