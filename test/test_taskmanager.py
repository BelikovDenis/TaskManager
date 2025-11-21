"""Модуль тестирования TaskManager."""
import asyncio
from datetime import time
from unittest.mock import AsyncMock, Mock, patch

import pytest

from TaskManager import (Task, TaskManager, add_task_to_file,
                         create_file_with_task, validate_task_input)


class TestTask:
    """Тесты для класса Task."""

    def test_task_creation_valid(self):
        """Тест создания задачи с валидными данными."""
        task = Task("14:30", "Тестовая задача")
        assert task.time == time(14, 30)
        assert task.description == "Тестовая задача"

    def test_task_creation_invalid_time(self):
        """Тест создания задачи с невалидным временем."""
        with pytest.raises(ValueError, match="Некорректный формат времени"):
            Task("25:00", "Невалидное время")

    def test_task_creation_edge_times(self):
        """Тест создания задачи с граничными значениями времени."""
        # Минимальное время
        task1 = Task("00:00", "Полночь")
        assert task1.time == time(0, 0)

        # Максимальное время
        task2 = Task("23:59", "Почти полночь")
        assert task2.time == time(23, 59)

    def test_task_string_representation(self):
        """Тест строкового представления задачи."""
        task = Task("09:15", "Утренний кофе")
        expected = "09:15 - Утренний кофе"
        assert str(task) == expected

    def test_task_equality(self):
        """Тест сравнения задач."""
        task1 = Task("10:00", "Одинаковая задача")
        task2 = Task("10:00", "Одинаковая задача")
        task3 = Task("11:00", "Другая задача")

        assert task1 == task2
        assert task1 != task3
        assert task1 != "not a task"

    def test_task_hash(self):
        """Тест хэширования задач."""
        task1 = Task("10:00", "Задача")
        task2 = Task("10:00", "Задача")

        assert hash(task1) == hash(task2)

    @patch('TaskManager.datetime')
    def test_should_notify_true(self, mock_datetime):
        """Тест should_notify когда время наступило."""
        # Мокаем текущее время
        mock_now = Mock()
        mock_now.time.return_value = time(10, 0)
        mock_datetime.now.return_value = mock_now

        # Создаем задачу с реальным временем, а не моком
        with patch('TaskManager.datetime') as mock_dt_for_task:
            mock_dt_for_task.strptime.return_value.time.return_value = (
                time(9, 0)
            )
            task = Task("09:00", "Прошедшая задача")

        assert task.should_notify() is True

    @patch('TaskManager.datetime')
    def test_should_notify_false(self, mock_datetime):
        """Тест should_notify когда время еще не наступило."""
        # Мокаем текущее время
        mock_now = Mock()
        mock_now.time.return_value = time(8, 0)
        mock_datetime.now.return_value = mock_now

        # Создаем задачу с реальным временем, а не моком
        with patch('TaskManager.datetime') as mock_dt_for_task:
            mock_dt_for_task.strptime.return_value.time.return_value = (
                time(9, 0)
            )
            task = Task("09:00", "Будущая задача")

        assert task.should_notify() is False


class TestTaskManager:
    """Тесты для класса TaskManager."""

    def test_init(self, temp_tasks_file):
        """Тест инициализации TaskManager."""
        manager = TaskManager(str(temp_tasks_file))
        assert manager.tasks_file == temp_tasks_file
        assert manager.tasks == []
        assert manager.last_modified == 0.0
        assert manager._monitoring is False

    def test_parse_tasks_from_text_valid(self, task_manager):
        """Тест парсинга валидного текста с задачами."""
        text = """09:00 - Утреннее совещание
                 # Это комментарий
                 12:30 Обед
                 15:45 - Встреча с клиентом"""

        tasks = task_manager.parse_tasks_from_text(text)

        assert len(tasks) == 3
        assert tasks[0].time == time(9, 0)
        assert tasks[0].description == "Утреннее совещание"
        assert tasks[1].time == time(12, 30)
        assert tasks[1].description == "Обед"

    def test_parse_tasks_from_text_invalid(self, task_manager):
        """Тест парсинга текста с невалидными задачами."""
        text = """invalid time - Задача
                  25:70 - Невалидное время
                  - Задача без времени"""

        tasks = task_manager.parse_tasks_from_text(text)
        assert len(tasks) == 0

    def test_parse_tasks_from_text_empty_description(self, task_manager):
        """Тест парсинга задач с пустым описанием."""
        text = "10:00 - "
        tasks = task_manager.parse_tasks_from_text(text)
        assert len(tasks) == 0

    def test_load_tasks_success(self, task_manager, temp_tasks_file):
        """Тест успешной загрузки задач из файла."""
        result = task_manager.load_tasks()

        assert result is True
        assert len(task_manager.tasks) == 3
        assert task_manager.last_modified > 0

    def test_load_tasks_file_not_exists(self, task_manager, empty_tasks_file):
        """Тест загрузки задач из несуществующего файла."""
        manager = TaskManager("nonexistent.txt")
        result = manager.load_tasks()
        assert result is False

    def test_load_tasks_empty_file(self, task_manager, empty_tasks_file):
        """Тест загрузки задач из пустого файла."""
        manager = TaskManager(str(empty_tasks_file))
        result = manager.load_tasks()
        assert result is True
        assert manager.tasks == []

    @pytest.mark.asyncio
    async def test_check_and_notify(self, task_manager, sample_tasks):
        """Тест проверки и отправки уведомлений."""
        task_manager.tasks = sample_tasks.copy()

        # Мокаем should_notify на уровне класса Task
        with patch.object(Task, 'should_notify') as mock_should_notify:
            mock_should_notify.side_effect = [True, False, False]
            with patch.object(
                task_manager, '_send_notification', AsyncMock()
            ) as mock_send:
                await task_manager.check_and_notify()

                # Проверяем что уведомление было отправлено для одной задачи
                mock_send.assert_called_once_with(sample_tasks[0])
                # Одна задача должна быть удалена
                assert len(task_manager.tasks) == 2

    @pytest.mark.asyncio
    async def test_send_notification(self, task_manager):
        """Тест отправки уведомления."""
        task = Task("10:00", "Тестовая задача")

        # Используем patch для перехвата вывода print
        with patch('builtins.print') as mock_print:
            await task_manager._send_notification(task)

            # Проверяем что print был вызван с правильными аргументами
            mock_print.assert_called()

    @pytest.mark.asyncio
    async def test_monitoring_context(self, task_manager):
        """Тест контекстного менеджера мониторинга."""
        async with task_manager.monitoring_context():
            assert task_manager._monitoring is True

        assert task_manager._monitoring is False

    @pytest.mark.asyncio
    async def test_monitor_tasks_normal_operation(self, task_manager):
        """Тест нормальной работы мониторинга задач."""
        task_manager._monitoring = True

        # Мокаем методы чтобы тест быстро завершился
        with patch.object(task_manager, 'load_tasks', return_value=True), \
             patch.object(task_manager, 'check_and_notify', AsyncMock()), \
             patch.object(task_manager, 'display_loaded_tasks'), \
             patch('asyncio.sleep', AsyncMock()):

            # Запускаем на короткое время
            task_manager._monitoring = True
            monitor_task = asyncio.create_task(task_manager.monitor_tasks())
            await asyncio.sleep(0.1)
            task_manager._monitoring = False
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_monitor_tasks_cancelled(self, task_manager):
        """Тест обработки CancelledError в мониторинге."""
        task_manager._monitoring = True

        with patch.object(
            task_manager, 'load_tasks', side_effect=asyncio.CancelledError
        ):
            with pytest.raises(asyncio.CancelledError):
                await task_manager.monitor_tasks()


class TestHelperFunctions:
    """Тесты вспомогательных функций."""

    def test_validate_task_input_valid(self):
        """Тест валидации корректного ввода задачи."""
        valid_inputs = [
            "10:00 - Тестовая задача",
            "10:00 Тестовая задача",
            "23:59 - Крайнее время"
        ]

        for task_input in valid_inputs:
            assert validate_task_input(task_input) is True

    def test_validate_task_input_invalid(self):
        """Тест валидации некорректного ввода задачи."""
        invalid_inputs = [
            "25:00 - Невалидное время",
            "10:70 - Невалидное время",
            "10:00 - ",
            " - Пустое описание",
            "просто текст"
        ]

        for task_input in invalid_inputs:
            assert validate_task_input(task_input) is False

    def test_add_task_to_file_success(self, temp_tasks_file):
        """Тест успешного добавления задачи в файл."""
        task_line = "16:00 - Новая задача"

        result = add_task_to_file(temp_tasks_file, task_line)

        assert result is True
        # Проверяем что задача действительно добавлена
        content = temp_tasks_file.read_text(encoding='utf-8')
        assert task_line in content

    def test_create_file_with_task_success(self, empty_tasks_file):
        """Тест успешного создания файла с задачей."""
        task_line = "16:00 - Новая задача"

        result = create_file_with_task(empty_tasks_file, task_line)

        assert result is True
        assert empty_tasks_file.exists()
        content = empty_tasks_file.read_text(encoding='utf-8')
        assert task_line in content


class TestIntegration:
    """Интеграционные тесты."""

    @pytest.mark.asyncio
    async def test_full_workflow(self, temp_tasks_file):
        """Тест полного рабочего процесса."""
        from TaskManager import TaskManager

        manager = TaskManager(str(temp_tasks_file))

        # Загружаем задачи
        result = manager.load_tasks()
        assert result is True
        initial_task_count = len(manager.tasks)

        # Добавляем новую задачу
        new_task = "17:00 - Новая интеграционная задача"
        add_task_to_file(temp_tasks_file, new_task)

        # Перезагружаем задачи
        result = manager.load_tasks()
        assert result is True
        assert len(manager.tasks) == initial_task_count + 1

    def test_display_functions(self, sample_tasks, capsys):
        """Тест функций отображения."""
        from TaskManager import display_loaded_tasks

        display_loaded_tasks(sample_tasks)
        captured = capsys.readouterr()

        assert "Текущие задачи:" in captured.out
        assert "09:00 - Утреннее совещание" in captured.out


class TestEdgeCases:
    """Тесты граничных случаев."""

    def test_task_with_special_characters(self, task_manager):
        """Тест задачи со специальными символами."""
        text = '10:00 - Задача с "кавычками" и спец. символами!'
        tasks = task_manager.parse_tasks_from_text(text)

        assert len(tasks) == 1
        assert tasks[0].description == (
            'Задача с "кавычками" и спец. символами!'
        )

    def test_multiple_spaces_in_input(self, task_manager):
        """Тест парсинга с множественными пробелами."""
        text = "10:00    -    Задача   с   множеством   пробелов"
        tasks = task_manager.parse_tasks_from_text(text)

        assert len(tasks) == 1
        assert tasks[0].description == "Задача с множеством пробелов"

    def test_file_permission_error(self, task_manager, temp_tasks_file):
        """Тест обработки ошибок разрешений файла."""
        # Создаем ситуацию с ошибкой разрешений
        with patch(
            'pathlib.Path.read_text', side_effect=PermissionError(
                "No permission"
            )
        ):
            result = task_manager.load_tasks()
            assert result is False
