import asyncio
import logging
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, time
from pathlib import Path
from typing import List, Optional


class Task:
    """Класс для представления задачи с временем выполнения."""

    __slots__ = ('time', 'description')

    def __init__(self, time_str: str, description: str):
        self.time = self._parse_time(time_str)
        self.description = description.strip()

    def _parse_time(self, time_str: str) -> time:
        """Парсит время из строки с использованием строгой валидации."""
        time_pattern = r'^(?:[01]?\d|2[0-3]):[0-5]\d$'
        if not re.match(time_pattern, time_str):
            raise ValueError(f"Некорректный формат времени: {time_str}")

        return datetime.strptime(time_str, '%H:%M').time()

    def should_notify(self) -> bool:
        """Проверяет, наступило ли время для уведомления."""
        now = datetime.now().time()
        return now >= self.time

    def __str__(self) -> str:
        return f"{self.time.strftime('%H:%M')} - {self.description}"

    def __repr__(self) -> str:
        return f"Task(time={self.time}, description='{self.description}')"

    def __eq__(self, other) -> bool:
        if not isinstance(other, Task):
            return False
        return self.time == other.time and self.description == other.description

    def __hash__(self) -> int:
        return hash((self.time, self.description))


class TaskManager:
    """Основной класс для управления задачами с улучшенной асинхронной обработкой."""

    def __init__(self, tasks_file: str = "tasks.txt"):
        self.tasks_file = Path(tasks_file)
        self.tasks: List[Task] = []
        self._setup_logging()
        self.last_modified: float = 0.0
        self._monitoring = False
        self._monitor_task: Optional[asyncio.Task] = None

    def _setup_logging(self) -> None:
        """Настраивает структурированное логирование."""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('task_manager.log', encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def parse_tasks_from_text(self, text: str) -> List[Task]:
        """Парсит задачи из текста с улучшенной обработкой ошибок."""
        tasks = []
        time_pattern = r'\b([01]?\d|2[0-3]):([0-5]\d)\b'

        for line_num, line in enumerate(text.split('\n'), 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            match = re.search(time_pattern, line)
            if match:
                time_str = match.group()
                try:
                    description = re.sub(time_pattern, '', line).strip(' -')
                    # Убираем множественные пробелы в описании
                    description = re.sub(r'\s+', ' ', description).strip()
                    if not description:
                        self.logger.warning(
                            f"Пустое описание задачи в строке {line_num}"
                        )
                        continue

                    task = Task(time_str, description)
                    tasks.append(task)
                    self.logger.info(f"Успешно распарсена задача: {task}")

                except ValueError as e:
                    self.logger.error(f"Ошибка в строке {line_num}: {e}")
            else:
                self.logger.warning(
                    f"Не удалось найти время в задаче: '{line}'"
                )

        return tasks

    def load_tasks(self) -> bool:
        """Загружает задачи из файла с улучшенной обработкой ошибок."""
        try:
            if not self.tasks_file.exists():
                self.logger.error(f"Файл {self.tasks_file} не существует")
                return False

            current_modified = self.tasks_file.stat().st_mtime
            if current_modified <= self.last_modified:
                return True  # Файл не изменялся, но это не ошибка

            self.last_modified = current_modified
            content = self.tasks_file.read_text(encoding='utf-8')

            if not content.strip():
                self.logger.warning("Файл с задачами пуст")
                self.tasks.clear()
                return True

            new_tasks = self.parse_tasks_from_text(content)
            # Для тестов загружаем все задачи без фильтрации по времени
            self.tasks = new_tasks

            self.logger.info(f"Загружено {len(self.tasks)} задач")
            return True

        except Exception as e:
            self.logger.error(f"Критическая ошибка при загрузке задач: {e}")
            return False

    async def check_and_notify(self) -> None:
        """Асинхронно проверяет задачи и отправляет уведомления."""
        tasks_to_remove = []

        for task in self.tasks[:]:
            if task.should_notify():
                await self._send_notification(task)
                tasks_to_remove.append(task)
                self.logger.info(f"Уведомление отправлено для задачи: {task}")

        # Удаляем выполненные задачи
        for task in tasks_to_remove:
            self.tasks.remove(task)

    async def _send_notification(self, task: Task) -> None:
        """Асинхронно отправляет уведомление о задаче."""
        # Звуковой сигнал
        print("\a", end='', flush=True)
        # Визуальное уведомление
        notification = (
            f"\n{'=' * 50}\nНАПОМИНАНИЕ: {task}\n{'=' * 50}\n"
        )
        print(notification)

    def display_loaded_tasks(self) -> None:
        """Отображает загруженные задачи."""
        display_loaded_tasks(self.tasks)

    @asynccontextmanager
    async def monitoring_context(self):
        """Контекстный менеджер для безопасного управления мониторингом."""
        self._monitoring = True
        self.logger.info("Запуск мониторинга задач")
        try:
            yield
        except Exception as e:
            self.logger.error(f"Ошибка в контексте мониторинга: {e}")
            raise
        finally:
            self._monitoring = False
            self.logger.info("Мониторинг задач остановлен")

    async def monitor_tasks(self) -> None:
        """Улучшенный цикл мониторинга задач."""
        async with self.monitoring_context():
            while self._monitoring:
                try:
                    # Проверяем изменения в файле
                    self.load_tasks()

                    # Проверяем задачи для уведомлений
                    await self.check_and_notify()

                    # Асинхронная задержка
                    await asyncio.sleep(1)

                except asyncio.CancelledError:
                    self.logger.info("Мониторинг задач был отменен")
                    raise  # Пробрасываем исключение дальше
                except Exception as e:
                    self.logger.error(
                        f"Неожиданная ошибка в цикле мониторинга: {e}"
                    )
                    await asyncio.sleep(5)

    def validate_task_input(self, task_input: str) -> bool:
        """Проверяет корректность введенной задачи."""
        return validate_task_input(task_input)


def get_user_task_input() -> str:
    """Получает и валидирует ввод задачи от пользователя."""
    print("\nФормат: HH:MM - описание задачи")
    print("Пример: 14:30 - Встреча с командой")

    while True:
        task_input = input("\nВведите вашу задачу: ").strip()

        if not task_input:
            print("Задача не может быть пустой. Попробуйте снова.")
            continue

        # Создаем временный объект TaskManager для валидации
        temp_manager = TaskManager()
        if temp_manager.validate_task_input(task_input):
            return task_input
        else:
            print("Некорректный формат задачи. Убедитесь, что:")
            print("- Время в формате HH:MM (например, 09:30 или 14:00)")
            print("- Есть описание задачи после времени")
            print("- Разделитель между временем и описанием: ' - ' или пробелы")
            print("Попробуйте снова.")


def display_loaded_tasks(tasks: List[Task]) -> None:
    """Отображает загруженные задачи в удобочитаемом формате."""
    if not tasks:
        print("Нет актуальных задач для обработки")
        return

    print("\nТекущие задачи:")
    for i, task in enumerate(tasks, 1):
        print(f"  {i}. {task}")
    print("-" * 50)


def display_all_tasks(tasks_file: Path) -> None:
    """Отображает все задачи из файла, включая прошедшие."""
    if not tasks_file.exists():
        print("Файл с задачами не существует")
        return

    content = tasks_file.read_text(encoding='utf-8')
    if not content.strip():
        print("Файл с задачами пуст")
        return

    temp_manager = TaskManager()
    tasks = temp_manager.parse_tasks_from_text(content)
    if not tasks:
        print("Нет задач в файле")
        return

    print("\nВсе задачи в файле:")
    for i, task in enumerate(tasks, 1):
        status = "✓" if task.should_notify() else " "
        print(f"  {i}. [{status}] {task}")
    print("-" * 50)


def validate_task_input(task_input: str) -> bool:
    """Проверяет корректность введенной задачи."""
    time_pattern = r'\b([01]?\d|2[0-3]):([0-5]\d)\b'
    match = re.search(time_pattern, task_input)
    if not match:
        return False

    time_str = match.group()
    description = re.sub(time_pattern, '', task_input).strip(' -')
    if not description:
        return False

    try:
        Task(time_str, description)
        return True
    except ValueError:
        return False


def add_task_to_file(tasks_file: Path, task_line: str) -> bool:
    """Добавляет задачу в файл."""
    try:
        with open(tasks_file, 'a', encoding='utf-8') as f:
            f.write(task_line + '\n')
        logging.getLogger(__name__).info(f"Задача добавлена в файл: {task_line}")
        return True
    except Exception as e:
        logging.getLogger(__name__).error(f"Ошибка при добавлении задачи: {e}")
        return False


def create_file_with_task(tasks_file: Path, task_line: str) -> bool:
    """Создает файл задач и добавляет первую задачу."""
    try:
        with open(tasks_file, 'w', encoding='utf-8') as f:
            f.write(task_line + '\n')
        logging.getLogger(__name__).info(f"Файл {tasks_file} создан с задачей: {task_line}")
        return True
    except Exception as e:
        logging.getLogger(__name__).error(f"Ошибка при создании файла: {e}")
        return False


async def interactive_menu(tasks_file: Path) -> None:
    """Интерактивное меню для управления задачами."""
    task_manager = TaskManager(tasks_file)

    while True:
        print("\n" + "=" * 50)
        print("МЕНЮ УПРАВЛЕНИЯ ЗАДАЧАМИ")
        print("=" * 50)
        print("1. Показать все задачи")
        print("2. Добавить новую задачу")
        print("3. Запустить мониторинг задач")
        print("4. Выйти из программы")

        choice = input("\nВыберите действие (1-4): ").strip()

        if choice == '1':
            display_all_tasks(tasks_file)
        elif choice == '2':
            add_task_interactive(tasks_file, task_manager)
        elif choice == '3':
            await start_monitoring(task_manager)
        elif choice == '4':
            print("Выход из программы. До свидания!")
            break
        else:
            print("Неверный выбор. Пожалуйста, введите число от 1 до 4.")


def add_task_interactive(tasks_file: Path, task_manager: TaskManager) -> None:
    """Интерактивное добавление задачи."""
    print("\nДобавление новой задачи")
    task_line = get_user_task_input()

    if add_task_to_file(tasks_file, task_line):
        print(f"\nЗадача успешно добавлена: {task_line}")
        # Перезагружаем задачи для отображения актуального списка
        task_manager.load_tasks()
    else:
        print("Ошибка при добавлении задачи.")


async def start_monitoring(task_manager: TaskManager) -> None:
    """Запускает мониторинг задач."""
    if not task_manager.load_tasks():
        print("Ошибка при загрузке задач.")
        return

    if not task_manager.tasks:
        print("Нет актуальных задач для мониторинга.")
        print("Добавьте задачи с будущим временем.")
        return

    display_loaded_tasks(task_manager.tasks)
    print("Мониторинг задач запущен. Для остановки нажмите Ctrl+C")

    try:
        await task_manager.monitor_tasks()
    except KeyboardInterrupt:
        task_manager.logger.info("Мониторинг остановлен пользователем")
        print("\nМониторинг остановлен. Возврат в меню.")
    except Exception as e:
        task_manager.logger.error(f"Неожиданная ошибка: {e}")
        print(f"\nПроизошла непредвиденная ошибка: {e}")


async def main():
    """Основная функция приложения."""
    tasks_file = Path("tasks.txt")

    # Проверяем существование файла
    if not tasks_file.exists():
        print(f"Файл {tasks_file} не найден.")

        choice = input("Хотите создать файл и добавить задачу? (да/нет): ").strip().lower()

        if choice in ['да', 'д', 'yes', 'y']:
            task_line = get_user_task_input()
            if create_file_with_task(tasks_file, task_line):
                print(f"\nФайл {tasks_file} успешно создан!")
                print(f"Добавлена задача: {task_line}")
                # После создания файла переходим в меню
                await interactive_menu(tasks_file)
            else:
                print("Ошибка при создании файла. Программа завершает работу.")
                return
        else:
            print("Программа завершает работу.")
            return
    else:
        # Файл существует, переходим в меню
        await interactive_menu(tasks_file)


if __name__ == "__main__":
    # Используем современный запуск asyncio
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nПриложение завершено.")