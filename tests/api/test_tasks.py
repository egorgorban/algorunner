from uuid import uuid4


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


async def test_create_task_rejects_oversized_problem_text(app_client):
    response = await app_client.post(
        "/api/v1/tasks",
        json={"problem_text": "x" * 5001, "language": "en", "examples": []},
    )
    assert response.status_code == 422


async def test_create_task_rejects_too_many_examples(app_client):
    response = await app_client.post(
        "/api/v1/tasks",
        json={
            "problem_text": "two sum",
            "language": "en",
            "examples": [{"input": "1", "output": "1"} for _ in range(11)],
        },
    )
    assert response.status_code == 422


async def test_create_task_rejects_invalid_language(app_client):
    response = await app_client.post(
        "/api/v1/tasks",
        json={"problem_text": "two sum", "language": "fr", "examples": []},
    )
    assert response.status_code == 422


async def test_get_task_unknown_id_returns_404(app_client):
    response = await app_client.get(f"/api/v1/tasks/{uuid4()}")
    assert response.status_code == 404


async def test_create_task_rejects_oversized_body_with_413(app_client):
    # A body whose Content-Length exceeds MAX_BODY_BYTES (100,000) must be
    # rejected before Pydantic body-parsing runs — constructed purely for
    # byte-size testing purposes via an oversized problem_text string.
    response = await app_client.post(
        "/api/v1/tasks",
        json={"problem_text": "x" * 150_000, "language": "en", "examples": []},
    )
    assert response.status_code == 413
