#!/usr/bin/env python3
"""
Скрипт для тестирования API заявок
"""

import requests
import json
from datetime import datetime

# Конфигурация
BASE_URL = "http://localhost:8000"
API_URL = f"{BASE_URL}/api/v1/applications"

def test_create_application():
    """Тест создания заявки"""
    test_data = {
        "type": "на консультацию",
        "name": "Тестовый Клиент",
        "phone": "+7 (900) 123-45-67",
        "email": "test@example.com",
        "nearest_office": "Москва, Тверская 1",
        "communication_time": "с 10:00 до 18:00",
        "description": "Тестовая заявка на поиск тура в Турцию"
    }
    
    print("🚀 Отправка тестовой заявки...")
    print(f"Данные: {json.dumps(test_data, ensure_ascii=False, indent=2)}")
    
    try:
        response = requests.post(
            f"{API_URL}/submit",
            json=test_data,
            headers={"Content-Type": "application/json"}
        )
        
        print(f"\n📊 Статус ответа: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Заявка успешно создана!")
            print(f"📝 Ответ: {json.dumps(result, ensure_ascii=False, indent=2)}")
            
            # Возвращаем ID для дальнейших тестов
            return result.get("application_id")
        else:
            print("❌ Ошибка при создании заявки!")
            print(f"📝 Ответ: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Ошибка при отправке запроса: {e}")
        return None

def test_get_application(app_id):
    """Тест получения заявки по ID"""
    if not app_id:
        print("⚠️ Нет ID заявки для тестирования")
        return
    
    print(f"\n🔍 Получение заявки {app_id}...")
    
    try:
        response = requests.get(f"{API_URL}/{app_id}")
        
        print(f"📊 Статус ответа: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Заявка успешно получена!")
            print(f"📝 Данные: {json.dumps(result, ensure_ascii=False, indent=2)}")
        else:
            print("❌ Ошибка при получении заявки!")
            print(f"📝 Ответ: {response.text}")
            
    except Exception as e:
        print(f"❌ Ошибка при получении заявки: {e}")

def test_get_all_applications():
    """Тест получения списка всех заявок"""
    print(f"\n📋 Получение списка всех заявок...")
    
    try:
        response = requests.get(f"{API_URL}/")
        
        print(f"📊 Статус ответа: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Получено {len(result)} заявок")
            
            if result:
                print("📝 Последние заявки:")
                for app in result[:3]:  # Показываем только первые 3
                    print(f"  - {app['id']}: {app['name']} ({app['type']}) - {app['created_at']}")
            else:
                print("📝 Заявок пока нет")
        else:
            print("❌ Ошибка при получении списка заявок!")
            print(f"📝 Ответ: {response.text}")
            
    except Exception as e:
        print(f"❌ Ошибка при получении списка заявок: {e}")

def test_update_status(app_id):
    """Тест обновления статуса заявки"""
    if not app_id:
        print("⚠️ Нет ID заявки для тестирования")
        return
    
    print(f"\n🔄 Обновление статуса заявки {app_id}...")
    
    try:
        response = requests.patch(
            f"{API_URL}/{app_id}/status",
            params={"status": "processed"}
        )
        
        print(f"📊 Статус ответа: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Статус успешно обновлен!")
            print(f"📝 Ответ: {json.dumps(result, ensure_ascii=False, indent=2)}")
        else:
            print("❌ Ошибка при обновлении статуса!")
            print(f"📝 Ответ: {response.text}")
            
    except Exception as e:
        print(f"❌ Ошибка при обновлении статуса: {e}")

def main():
    """Основная функция тестирования"""
    print("🧪 ТЕСТИРОВАНИЕ API ЗАЯВОК")
    print("=" * 50)
    
    # Тест 1: Создание заявки
    app_id = test_create_application()
    
    # Тест 2: Получение заявки по ID
    test_get_application(app_id)
    
    # Тест 3: Получение всех заявок
    test_get_all_applications()
    
    # Тест 4: Обновление статуса
    test_update_status(app_id)
    
    print("\n🏁 ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
    print("=" * 50)

if __name__ == "__main__":
    main()