def test_bump_and_today(client):
    r = client.post(
        "/activity/bump",
        json={"user_id": "alice", "messages_sent": 5},
        headers={"X-Dealer-Id": "dealer-1"},
    )
    assert r.status_code == 200
    assert r.json()["messages_sent"] == 5

    # Bump again — should accumulate
    r = client.post(
        "/activity/bump",
        json={"user_id": "alice", "messages_sent": 3, "calls_made": 2},
        headers={"X-Dealer-Id": "dealer-1"},
    )
    body = r.json()
    assert body["messages_sent"] == 8
    assert body["calls_made"] == 2


def test_summary_computes_goal_pct(client):
    client.post(
        "/activity/bump",
        json={"user_id": "alice", "messages_sent": 30},  # default goal 60 -> 50%
        headers={"X-Dealer-Id": "dealer-1"},
    )
    r = client.get("/activity/summary?user_id=alice", headers={"X-Dealer-Id": "dealer-1"})
    body = r.json()
    assert body["today"]["messages_sent"] == 30
    assert body["goal_pct"] == 50
    assert body["streak_days"] == 0  # no prior days
    assert body["week_totals"]["messages_sent"] == 30


def test_activity_isolation_by_dealer(client):
    client.post(
        "/activity/bump",
        json={"user_id": "alice", "messages_sent": 10},
        headers={"X-Dealer-Id": "dealer-a"},
    )
    r = client.get("/activity/today?user_id=alice", headers={"X-Dealer-Id": "dealer-b"})
    # dealer-b should have a fresh 0 row, not see dealer-a's data
    assert r.json()["messages_sent"] == 0
