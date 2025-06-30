#!/usr/bin/env python3
"""
Быстрый тест Gmail аутентификации
"""

import smtplib
from email.mime.text import MIMEText
from datetime import datetime

def test_gmail_auth():
    """Тест только аутентификации без отправки письма"""
    
    # Ваши настройки
    smtp_host = "smtp.gmail.com"
    smtp_port = 587
    smtp_username = "advice.notifications@gmail.com"
    
    print("🔐 ТЕСТ GMAIL АУТЕНТИФИКАЦИИ")
    print("=" * 50)
    print(f"📧 Email: {smtp_username}")
    
    # Запрашиваем пароль
    import getpass
    print("\n🔑 Введите пароль приложения Gmail:")
    print("   (16 символов, можно с пробелами или без)")
    smtp_password = getpass.getpass("Пароль: ")
    
    if not smtp_password:
        print("❌ Пароль не введен!")
        return False
    
    # Убираем пробелы из пароля
    smtp_password = smtp_password.replace(" ", "")
    print(f"📏 Длина пароля: {len(smtp_password)} символов")
    
    if len(smtp_password) != 16:
        print("⚠️ Предупреждение: пароль приложения Gmail должен быть 16 символов")
    
    try:
        print("\n🔌 Подключение к Gmail...")
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            print("🔒 Включение TLS...")
            server.starttls()
            
            print("🔑 Попытка входа...")
            server.login(smtp_username, smtp_password)
            
            print("✅ АУТЕНТИФИКАЦИЯ УСПЕШНА!")
            print("🎉 Пароль приложения работает!")
            
            # Показываем правильный пароль для .env
            print(f"\n📝 Добавьте в .env файл:")
            print(f"SMTP_PASSWORD={smtp_password}")
            
            return True
            
    except smtplib.SMTPAuthenticationError as e:
        print("❌ ОШИБКА АУТЕНТИФИКАЦИИ!")
        print(f"🔍 Детали: {e}")
        print("\n💡 ВОЗМОЖНЫЕ ПРИЧИНЫ:")
        print("1. Неправильный пароль приложения")
        print("2. Двухфакторная аутентификация отключена")
        print("3. Пароль приложения просрочен")
        print("\n🛠️ РЕШЕНИЕ:")
        print("1. Перейдите: https://myaccount.google.com/apppasswords")
        print("2. Удалите старые пароли приложений")
        print("3. Создайте новый пароль для 'Почта'")
        print("4. Скопируйте точно как показано (16 символов)")
        return False
        
    except smtplib.SMTPConnectError as e:
        print("❌ ОШИБКА ПОДКЛЮЧЕНИЯ!")
        print(f"🔍 Детали: {e}")
        print("💡 Проверьте интернет соединение")
        return False
        
    except Exception as e:
        print("❌ НЕОЖИДАННАЯ ОШИБКА!")
        print(f"🔍 Детали: {e}")
        return False

def test_with_current_password():
    """Тест с текущим паролем из .env"""
    print("\n🔍 ТЕСТ С ТЕКУЩИМ ПАРОЛЕМ")
    print("=" * 40)
    
    current_password = "tven oyop yxgf tltf"
    clean_password = current_password.replace(" ", "")
    
    print(f"🔑 Текущий пароль: {current_password}")
    print(f"🧹 Очищенный пароль: {clean_password}")
    print(f"📏 Длина: {len(clean_password)} символов")
    
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login("advice.notifications@gmail.com", clean_password)
            
        print("✅ Текущий пароль работает!")
        return True
        
    except smtplib.SMTPAuthenticationError:
        print("❌ Текущий пароль не работает!")
        print("💡 Нужно создать новый пароль приложения")
        return False
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

def show_gmail_setup_guide():
    """Показать инструкцию по созданию пароля приложения"""
    print("\n📚 ПОШАГОВАЯ ИНСТРУКЦИЯ")
    print("=" * 50)
    print()
    print("1️⃣ Откройте в браузере:")
    print("   https://myaccount.google.com/apppasswords")
    print()
    print("2️⃣ Войдите в аккаунт:")
    print("   advice.notifications@gmail.com")
    print()
    print("3️⃣ Если видите старые пароли приложений:")
    print("   • Удалите их (кнопка 'Удалить')")
    print()
    print("4️⃣ Создайте новый пароль:")
    print("   • Нажмите 'Создать пароль приложения'")
    print("   • Выберите 'Почта'")
    print("   • Выберите 'Другое устройство'")
    print("   • Введите: 'Турагентство API'")
    print()
    print("5️⃣ Скопируйте пароль:")
    print("   • Google покажет 16-значный пароль")
    print("   • Скопируйте ТОЧНО как показано")
    print("   • Например: abcdefghijklmnop")
    print()
    print("6️⃣ Обновите .env файл:")
    print("   SMTP_PASSWORD=ваш_новый_пароль")
    print()
    print("7️⃣ Перезапустите сервер:")
    print("   uvicorn app.main:app --reload")

def main():
    """Основная функция"""
    print("🧪 ДИАГНОСТИКА GMAIL АУТЕНТИФИКАЦИИ")
    print("=" * 60)
    
    # Тест 1: Текущий пароль
    current_works = test_with_current_password()
    
    if current_works:
        print("\n🎉 Текущий пароль работает!")
        print("💡 Возможно проблема была в кодировке комментариев")
        print("🚀 Попробуйте отправить заявку снова")
    else:
        # Тест 2: Новый пароль
        print("\n" + "="*60)
        auth_success = test_gmail_auth()
        
        if not auth_success:
            show_gmail_setup_guide()

if __name__ == "__main__":
    main()