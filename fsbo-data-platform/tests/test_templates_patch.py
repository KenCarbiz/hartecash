def _first_template_id(client, dealer="dealer-a"):
    r = client.get("/templates", headers={"X-Dealer-Id": dealer})
    assert r.status_code == 200
    return r.json()[0]["id"]


def test_patch_template_body(client):
    tid = _first_template_id(client)
    r = client.patch(
        f"/templates/{tid}",
        json={"body": "Hi, new body for {{make}} {{model}}."},
        headers={"X-Dealer-Id": "dealer-a"},
    )
    assert r.status_code == 200
    assert "new body" in r.json()["body"]


def test_patch_template_name_and_category(client):
    tid = _first_template_id(client)
    r = client.patch(
        f"/templates/{tid}",
        json={"name": "Renamed", "category": "custom"},
        headers={"X-Dealer-Id": "dealer-a"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Renamed"
    assert body["category"] == "custom"


def test_patch_template_dealer_isolation(client):
    # Seed dealer-a templates and grab one
    tid = _first_template_id(client, dealer="dealer-a")
    # dealer-b tries to patch -> 404
    r = client.patch(
        f"/templates/{tid}",
        json={"body": "hacked"},
        headers={"X-Dealer-Id": "dealer-b"},
    )
    assert r.status_code == 404


def test_patch_unknown_template(client):
    r = client.patch(
        "/templates/99999",
        json={"body": "x"},
        headers={"X-Dealer-Id": "dealer-a"},
    )
    assert r.status_code == 404
