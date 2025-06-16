import re
from typing import Dict

class Transliterator:
    """Класс для транслитерации русских названий в URL-friendly формат"""
    
    CYRILLIC_TO_LATIN: Dict[str, str] = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
        'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
        
        'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'Yo',
        'Ж': 'Zh', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
        'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
        'Ф': 'F', 'Х': 'Kh', 'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Shch',
        'Ъ': '', 'Ы': 'Y', 'Ь': '', 'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya'
    }
    
    @classmethod
    def to_url_slug(cls, text: str) -> str:
        """
        Преобразует текст в URL slug
        
        Правила:
        - Все буквы маленькие
        - Кириллица -> латиница
        - Только дефисы в качестве разделителей
        - Не может быть несколько дефисов подряд
        - Убираются ведущие и завершающие дефисы
        """
        if not text:
            return ""
        
        # Преобразуем в нижний регистр
        text = text.lower()
        
        # Транслитерируем кириллицу
        result = ""
        for char in text:
            if char in cls.CYRILLIC_TO_LATIN:
                result += cls.CYRILLIC_TO_LATIN[char]
            else:
                result += char
        
        # Заменяем все небуквенно-цифровые символы на дефисы
        result = re.sub(r'[^a-zA-Z0-9]', '-', result)
        
        # Убираем множественные дефисы
        result = re.sub(r'-+', '-', result)
        
        # Убираем дефисы в начале и конце
        result = result.strip('-')
        
        return result
    
    @classmethod
    def to_hotel_url(cls, hotel_name: str, hotel_id: str = None) -> str:
        """
        Создает URL для отеля на основе его названия
        
        Args:
            hotel_name: Название отеля
            hotel_id: ID отеля (опционально, для уникальности)
        
        Returns:
            URL slug для отеля
        """
        slug = cls.to_url_slug(hotel_name)
        
        # Если название слишком длинное, обрезаем
        if len(slug) > 100:
            slug = slug[:100].rstrip('-')
        
        # Добавляем ID для уникальности, если передан
        if hotel_id:
            slug = f"{slug}-{hotel_id}"
        
        return slug

# Создаем экземпляр транслитератора
transliterator = Transliterator()