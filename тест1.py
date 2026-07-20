from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

app = FastAPI(
    title="Task Manager API",
    description="API для управления задачами с возможностью создания и получения задач по идентификатору"
)

class TaskCreate(BaseModel):
    title: str = Field(
        ...,
        min_length=6,
        max_length=100,
        description="Название задачи. Обязательное поле, должно содержать от 3 до 100 символов."
    )
    description: Optional[str] = Field(
        None,
        description="Детальное описание задачи. Необязательное поле, может содержать дополнительную информацию о задаче."
    )
    priority: int = Field(
        ...,
        ge=1,
        le=5,
        description=(
            "Приоритет задачи. Обязательное поле. Допустимые значения: от 1 (низкий приоритет) до 5 (высокий приоритет). "
            "Рекомендуется использовать: 1 - низкий, 2 - ниже среднего, 3 - средний, 4 - выше среднего, 5 - высокий."
        )
    )

class Task(TaskCreate):
    id: int = Field(..., description="Уникальный идентификатор задачи, присваиваемый системой при создании")

tasks: dict[int, Task] = {}
next_id = 1

@app.post(
    "/tasks",
    response_model=Task,
    status_code=201,
    summary="Создать новую задачу",
    description=(
        "Создает новую задачу с указанным названием, описанием (опционально) и приоритетом. "
        "Задача сохраняется в памяти и получает уникальный идентификатор. "
        "Приоритет должен быть в диапазоне от 1 (низкий) до 5 (высокий)."
    ),
    responses={
        201: {
            "description": "Задача успешно создана",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/Task"}
                }
            }
        },
        422: {
            "description": "Ошибка валидации входных данных (неверный формат, отсутствуют обязательные поля, значения вне допустимых диапазонов)"
        }
    }
)
async def create_task(task: TaskCreate):
    global next_id
    task_data = task.dict()
    task_with_id = Task(id=next_id, **task_data)
    tasks[next_id] = task_with_id
    next_id += 1
    return task_with_id

@app.get(
    "/tasks/{task_id}",
    response_model=Task,
    summary="Получить задачу по идентификатору",
    description=(
        "Возвращает details задачи по указанному уникальному идентификатору. "
        "Если задача с указанным ID отсутствует, возвращается код 404."
    ),
    responses={
        200: {
            "description": "Задача успешно найдена и возвращена",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/Task"}
                }
            }
        },
        404: {
            "description": "Задача с указанным идентификатором не найдена"
        },
        422: {
            "description": "Ошибка валидации (например, ID не является целым числом)"
        }
    }
)
async def get_task(task_id: int):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return tasks[task_id]
