async def test_create_task_returns_202_and_queued(app_client):
    response = await app_client.post(
        "/api/v1/tasks",
        json={"problem_text": "two sum", "language": "en", "examples": []},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert "task_id" in body


async def test_get_task_reflects_live_status(app_client):
    create_response = await app_client.post(
        "/api/v1/tasks",
        json={"problem_text": "two sum", "language": "en", "examples": []},
    )
    task_id = create_response.json()["task_id"]

    get_response = await app_client.get(f"/api/v1/tasks/{task_id}")
    assert get_response.status_code == 200
    body = get_response.json()
    assert body["status"] in {
        "queued",
        "analyzing_problem",
        "completed",
        "failed",
    }
