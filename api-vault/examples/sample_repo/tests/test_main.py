"""Tests for main API endpoints."""

import pytest
from fastapi.testclient import TestClient

from src.main import app, tasks

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_tasks():
    """Clear tasks before each test."""
    tasks.clear()


def test_root():
    """Test health check endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_task():
    """Test creating a task."""
    response = client.post(
        "/tasks",
        json={"title": "Test task", "description": "A test task"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test task"
    assert data["id"] is not None


def test_list_tasks():
    """Test listing tasks."""
    # Create a task first
    client.post("/tasks", json={"title": "Task 1"})
    client.post("/tasks", json={"title": "Task 2"})

    response = client.get("/tasks")
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_get_task():
    """Test getting a task by ID."""
    # Create a task
    create_response = client.post("/tasks", json={"title": "Get me"})
    task_id = create_response.json()["id"]

    response = client.get(f"/tasks/{task_id}")
    assert response.status_code == 200
    assert response.json()["title"] == "Get me"


def test_get_task_not_found():
    """Test getting a non-existent task."""
    response = client.get("/tasks/999")
    assert response.status_code == 404


def test_delete_task():
    """Test deleting a task."""
    # Create a task
    create_response = client.post("/tasks", json={"title": "Delete me"})
    task_id = create_response.json()["id"]

    response = client.delete(f"/tasks/{task_id}")
    assert response.status_code == 204

    # Verify it's gone
    get_response = client.get(f"/tasks/{task_id}")
    assert get_response.status_code == 404
