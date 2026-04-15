"""
Пользовательские исключения для приложения
"""


class ApplicationError(Exception):
    """Базовое исключение приложения"""
    pass


class FileLoadError(ApplicationError):
    """Ошибка загрузки файла"""
    
    def __init__(self, file_path: str, reason: str):
        self.file_path = file_path
        self.reason = reason
        super().__init__(f"Не удалось загрузить файл '{file_path}': {reason}")


class ComparisonError(ApplicationError):
    """Ошибка при сравнении файлов"""
    pass


class ValidationError(ApplicationError):
    """Ошибка валидации данных"""
    
    def __init__(self, errors: list):
        self.errors = errors
        super().__init__(f"Ошибки валидации: {'; '.join(errors)}")


class UnsupportedFormatError(ApplicationError):
    """Неподдерживаемый формат файла"""
    
    def __init__(self, format_name: str, supported_formats: list):
        self.format_name = format_name
        self.supported_formats = supported_formats
        super().__init__(
            f"Формат '{format_name}' не поддерживается. "
            f"Поддерживаемые форматы: {', '.join(supported_formats)}"
        )


class ConfigurationError(ApplicationError):
    """Ошибка конфигурации"""
    pass