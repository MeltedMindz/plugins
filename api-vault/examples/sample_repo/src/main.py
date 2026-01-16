"""Main FastAPI application."""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(
    title="Sample Task API",
    description="A simple REST API for managing tasks",
    version="1.0.0",
)

# In-memory task storage
tasks: dict[int, dict] = {}
next_id = 1


class TaskCreate(BaseModel):
    """Request model for creating a task."""

    title: str
    description: str | None = None
    completed: bool = False


class Task(BaseModel):
    """Response model for a task."""

    id: int
    title: str
    description: str | None = None
    completed: bool = False


@app.get("/")
def root():
    """Health check endpoint."""
    return {"status": "ok", "message": "Task API is running"}


@app.get("/tasks", response_model=list[Task])
def list_tasks():
    """List all tasks."""
    return list(tasks.values())


@app.post("/tasks", response_model=Task, status_code=201)
def create_task(task: TaskCreate):
    """Create a new task."""
    global next_id
    new_task = {
        "id": next_id,
        "title": task.title,
        "description": task.description,
        "completed": task.completed,
    }
    tasks[next_id] = new_task
    next_id += 1
    return new_task


@app.get("/tasks/{task_id}", response_model=Task)
def get_task(task_id: int):
    """Get a task by ID."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks[task_id]


@app.put("/tasks/{task_id}", response_model=Task)
def update_task(task_id: int, task: TaskCreate):
    """Update a task."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    tasks[task_id].update({
        "title": task.title,
        "description": task.description,
        "completed": task.completed,
    })
    return tasks[task_id]


@app.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: int):
    """Delete a task."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    del tasks[task_id]
