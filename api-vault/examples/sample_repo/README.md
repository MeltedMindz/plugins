# Sample Task API

A simple REST API for managing tasks.

## Quick Start

```bash
pip install -r requirements.txt
uvicorn src.main:app --reload
```

## API Endpoints

- `GET /tasks` - List all tasks
- `POST /tasks` - Create a task
- `GET /tasks/{id}` - Get task by ID
- `DELETE /tasks/{id}` - Delete a task
