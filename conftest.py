import pytest
import asyncio
from datetime import datetime, time
from pathlib import Path
import tempfile
import os


@pytest.fixture
def temp_tasks_file():
    """Создает временный файл для тестов."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write("09:00 - Утреннее совещание\n")
        f.write("12:30 - Обед\n")
        f.write("15:45 - Встреча с клиентом\n")
        temp_path = f.name

    yield Path(temp_path)

    # Удаляем временный файл после теста
    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def empty_tasks_file():
    """Создает пустой временный файл."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        temp_path = f.name

    yield Path(temp_path)

    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def sample_tasks():
    """Возвращает примеры задач для тестирования."""
    from TaskManager import Task
    return [
        Task("09:00", "Утреннее совещание"),
        Task("12:30", "Обед"),
        Task("15:45", "Встреча с клиентом")
    ]


@pytest.fixture
def task_manager(temp_tasks_file):
    """Создает экземпляр TaskManager с временным файлом."""
    from TaskManager import TaskManager
    return TaskManager(str(temp_tasks_file))


@pytest.fixture
def event_loop():
    """Фикстура для работы с asyncio."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
