# Travel Agency Backend

Backend API для турагентства с интеграцией TourVisor API. Предоставляет функционал поиска туров, управления заявками, кэширования популярных направлений и real-time обновлений через WebSocket.

## Основные возможности

### 🔍 Поиск туров
- Асинхронный поиск туров через TourVisor API
- Real-time обновления статуса поиска через WebSocket
- Кэширование популярных направлений
- Продолжение поиска для получения дополнительных результатов

### 🎯 Случайные туры
- Автоматическое обновление случайных туров каждые сутки
- Разнообразие направлений (Египет, Турция, Таиланд и др.)
- Кэширование для быстрого отклика

### 🏨 Работа с отелями
- Поиск туров по названию отеля
- Детальная информация об отелях
- Sitemap для SEO оптимизации

### 📧 Система заявок
- Прием заявок на консультацию и рассрочку
- Автоматическая отправка на email
- Сохранение в Redis с TTL

### 📊 Справочники
- Города вылета, страны, курорты
- Типы питания, категории отелей
- Туроператоры и услуги

## Архитектура

```
app/
├── api/v1/          # API endpoints
├── core/            # Бизнес-логика
├── models/          # Pydantic модели
├── services/        # Сервисный слой
├── tasks/           # Фоновые задачи
└── utils/           # Утилиты
```

## Быстрый старт

### 1. Клонирование репозитория
```bash
git clone <repository-url>
cd travel_agency_backend
```

### 2. Настройка окружения
```bash
cp .env.example .env
# Отредактируйте .env файл с вашими настройками
```

### 3. Запуск с Docker
```bash
docker-compose up -d
```

### 4. Запуск без Docker
```bash
# Установка зависимостей
pip install -r requirements.txt

# Запуск Redis
redis-server

# Запуск приложения
uvicorn app.main:app --reload
```

## Конфигурация

### Обязательные переменные окружения

```bash
# TourVisor API
TOURVISOR_AUTH_LOGIN=your_login
TOURVISOR_AUTH_PASS=your_password

# Email настройки
SMTP_HOST=smtp.yandex.ru
SMTP_USERNAME=your_email@yandex.ru
SMTP_PASSWORD=your_password
EMAIL_TO=alexandratur@yandex.ru

# Redis
REDIS_URL=redis://localhost:6379
```

## API Endpoints

### Поиск туров
- `POST /api/v1/tours/search` - Запуск поиска
- `GET /api/v1/tours/search/{request_id}/status` - Статус поиска
- `GET /api/v1/tours/search/{request_id}/results` - Результаты поиска
- `POST /api/v1/tours/search/{request_id}/continue` - Продолжение поиска

### Случайные туры и направления
- `POST /api/v1/tours/random` - Случайные туры
- `GET /api/v1/tours/directions` - Направления с ценами

### Заявки
- `POST /api/v1/applications/submit` - Отправка заявки
- `GET /api/v1/applications/{id}` - Получение заявки
- `GET /api/v1/applications/` - Список заявок

### Sitemap
- `GET /sitemap?type=hotels` - Sitemap отелей
- `GET /sitemap?type=countries` - Sitemap стран
- `GET /sitemap?type=regions` - Sitemap курортов

### WebSocket
- `WS /ws/tours/{request_id}` - Real-time обновления поиска

## Фоновые задачи

### Прогрев кэша
- Автоматическое кэширование популярных туров
- Обновление каждые 6 часов
- Кэширование справочников

### Обновление случайных туров
- Ежедневное обновление в 00:00
- Разнообразие направлений
- Валидация данных туров

## Кэширование

### Redis структура
```
hot_tours:city_{city_id}                    # Горящие туры по городу
hot_tours:city_{city}_country_{country}     # Горящие туры по направлению
popular_search:{params_hash}                # Популярные поиски
reference:{type}                            # Справочники
random_tours                                # Случайные туры
application:{id}                            # Заявки
sitemap_{type}                             # Sitemap данные
```

### TTL настройки
- Горящие туры: 24 часа
- Справочники: 24 часа
- Популярные поиски: 24 часа
- Заявки: 30 дней
- Sitemap: 6 часов

## Мониторинг и логирование

### Логи
- Структурированное логирование
- Разные уровни для разработки/продакшена
- Логирование ошибок API TourVisor

### Метрики
- Время ответа API
- Количество поисковых запросов
- Статистика кэша

## Развертывание

### Docker (рекомендуется)
```bash
# Продакшен
docker-compose -f docker-compose.yml up -d

# Разработка с Redis Commander
docker-compose --profile dev up -d
```

### Без Docker
```bash
# Установка зависимостей
pip install -r requirements.txt

# Настройка переменных окружения
export TOURVISOR_AUTH_LOGIN=your_login
export TOURVISOR_AUTH_PASS=your_password
# ... остальные переменные

# Запуск
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Интеграция с фронтендом

### WebSocket подключение
```javascript
const ws = new WebSocket(`ws://localhost:8000/ws/tours/${requestId}`);
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'status') {
        // Обновление статуса поиска
    } else if (data.type === 'results') {
        // Получены результаты
    }
};
```

### API вызовы
```javascript
// Запуск поиска
const response = await fetch('/api/v1/tours/search', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(searchParams)
});
const {request_id} = await response.json();

// Подключение WebSocket для отслеживания
const ws = new WebSocket(`ws://localhost:8000/ws/tours/${request_id}`);
```

## Безопасность

- Валидация всех входных данных через Pydantic
- Rate limiting для API endpoints
- Безопасное хранение credentials в переменных окружения
- CORS настройки для фронтенда

## Производительность

- Асинхронная обработка запросов
- Redis кэширование с оптимальными TTL
- Пагинация результатов поиска
- Фоновые задачи для тяжелых операций

## Поддержка и разработка

### Запуск тестов
```bash
pytest
```

### Добавление новых endpoints
1. Создайте модели в `app/models/`
2. Добавьте бизнес-логику в `app/services/`
3. Создайте API endpoint в `app/api/v1/`
4. Обновите документацию

### Мониторинг производительности
```bash
# Мониторинг Redis
redis-cli monitor

# Логи приложения
docker-compose logs -f web

# Метрики через Redis Commander
http://localhost:8081
```

## Troubleshooting

### Частые проблемы

**Ошибки подключения к TourVisor API**
- Проверьте логин/пароль в `.env`
- Убедитесь, что IP разрешен в TourVisor
- Проверьте лимиты запросов

**Проблемы с Redis**
```bash
# Проверка соединения
redis-cli ping

# Очистка кэша
redis-cli flushall

# Проверка использования памяти
redis-cli info memory
```

**WebSocket не подключается**
- Проверьте CORS настройки
- Убедитесь, что request_id существует
- Проверьте логи на ошибки

### Отладка

```bash
# Включение debug режима
export DEBUG=true

# Детальные логи Redis
export REDIS_LOG_LEVEL=debug

# Логирование всех HTTP запросов
export LOG_LEVEL=debug
```

## Расширения и улучшения

### Планируемые функции
- [ ] Система уведомлений через Telegram Bot
- [ ] Аналитика и статистика поисков
- [ ] Интеграция с CRM системами
- [ ] Автоматическое тестирование API
- [ ] Prometheus метрики
- [ ] Backup стратегия для Redis

### Возможные оптимизации
- Использование Redis Cluster для масштабирования
- Добавление CDN для статических файлов
- Имплементация Circuit Breaker для TourVisor API
- Добавление rate limiting с Redis
- Использование Apache Kafka для событий

## Контакты и поддержка

При возникновении вопросов или проблем:
- Создайте Issue в репозитории
- Проверьте логи приложения
- Убедитесь в корректности конфигурации

# Установка на Windows

## Вариант 1: Быстрая установка (рекомендуется)

### 1. Установка Python 3.11
Скачайте Python 3.11 (не 3.13!) с официального сайта:
https://www.python.org/downloads/release/python-3118/

**Важно:** Убедитесь, что отметили "Add Python to PATH" при установке.

### 2. Установка Redis
Используйте один из способов:

**Через WSL (рекомендуется):**
```bash
# Установите WSL2 если еще не установлен
wsl --install

# В WSL терминале:
sudo apt update
sudo apt install redis-server
sudo service redis-server start
```

**Через Docker Desktop:**
```bash
docker run -d -p 6379:6379 --name redis redis:alpine
```

**Или скачайте Redis для Windows:**
https://github.com/microsoftarchive/redis/releases

### 3. Клонирование и настройка проекта
```bash
git clone <repository-url>
cd travel_agency_backend

# Создайте виртуальное окружение
python -m venv venv

# Активируйте виртуальное окружение
venv\Scripts\activate

# Установите зависимости для Windows
pip install -r requirements-windows.txt

# Скопируйте и настройте переменные окружения
copy .env.example .env
# Отредактируйте .env файл в текстовом редакторе
```

### 4. Настройка .env файла
```bash
# TourVisor API
TOURVISOR_AUTH_LOGIN=your_login
TOURVISOR_AUTH_PASS=your_password

# Redis (если используете WSL)
REDIS_URL=redis://localhost:6379

# Email настройки
SMTP_HOST=smtp.yandex.ru
SMTP_PORT=587
SMTP_USERNAME=your_email@yandex.ru
SMTP_PASSWORD=your_app_password
EMAIL_FROM=your_email@yandex.ru
EMAIL_TO=alexandratur@yandex.ru

# Остальные настройки
DEBUG=True
ALLOWED_HOSTS=["*"]
```

### 5. Запуск приложения
```bash
# Убедитесь, что Redis запущен
# Если используете WSL: wsl -e sudo service redis-server start
# Если используете Docker: docker start redis

# Запустите приложение
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Вариант 2: Docker (если есть Docker Desktop)

### 1. Установка Docker Desktop
Скачайте и установите Docker Desktop для Windows:
https://docs.docker.com/desktop/install/windows-install/

### 2. Запуск проекта
```bash
git clone <repository-url>
cd travel_agency_backend

# Скопируйте .env файл
copy .env.example .env
# Отредактируйте .env

# Запуск через Docker
docker-compose up -d
```

## Вариант 3: Если нужна новая версия Pydantic

### 1. Установка Microsoft C++ Build Tools
Скачайте и установите:
https://visualstudio.microsoft.com/visual-cpp-build-tools/

Выберите "C++ build tools" и убедитесь, что установлены:
- MSVC v143 compiler toolset
- Windows 10/11 SDK

### 2. Установка Rust (для pydantic-core)
```bash
# Скачайте rustup с https://rustup.rs/
# Или используйте:
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Перезапустите терминал и проверьте:
rustc --version
cargo --version
```

### 3. Установка зависимостей
```bash
pip install -r requirements.txt
```

## Проверка установки

### 1. Проверка Redis
```bash
# В новом терминале
redis-cli ping
# Должно вернуть: PONG
```

### 2. Проверка приложения
Откройте браузер и перейдите на:
- http://localhost:8000 - основная страница
- http://localhost:8000/docs - Swagger документация
- http://localhost:8000/health - проверка здоровья

### 3. Тестирование API
```bash
# Тест получения справочников
curl http://localhost:8000/api/v1/references/departure

# Тест health check
curl http://localhost:8000/health
```

## Возможные проблемы и решения

### Redis не запускается
```bash
# Проверьте, запущен ли процесс
tasklist | findstr redis

# Если используете WSL
wsl -e ps aux | grep redis

# Перезапустите Redis
wsl -e sudo service redis-server restart
```

### Ошибки с Pydantic
```bash
# Используйте requirements-windows.txt вместо requirements.txt
pip uninstall pydantic pydantic-core
pip install -r requirements-windows.txt
```

### Ошибки с aiohttp
```bash
# Установите Microsoft Visual C++ 14.0 или новее
# Или используйте предкомпилированную версию:
pip install --only-binary=all aiohttp
```

### Проблемы с портами
```bash
# Проверьте, какие порты заняты
netstat -an | findstr :8000
netstat -an | findstr :6379

# Измените порт в команде запуска
uvicorn app.main:app --reload --port 8001
```

## Разработка на Windows

### Рекомендуемые инструменты:
- **IDE:** PyCharm, VS Code
- **Терминал:** Windows Terminal, Git Bash
- **Redis GUI:** RedisInsight, Another Redis Desktop Manager

### Настройка VS Code:
```json
// .vscode/settings.json
{
    "python.defaultInterpreterPath": "./venv/Scripts/python.exe",
    "python.linting.enabled": true,
    "python.linting.pylintEnabled": true
}
```

### Полезные команды:
```bash
# Активация виртуального окружения
venv\Scripts\activate

# Деактивация
deactivate

# Обновление зависимостей
pip install --upgrade -r requirements-windows.txt

# Очистка кэша pip
pip cache purge
```

## Производительность на Windows

### Оптимизация:
1. Используйте SSD диск
2. Выделите достаточно RAM для Redis
3. Настройте Windows Defender исключения для папки проекта
4. Используйте WSL2 для Redis (быстрее чем Windows порт)

### Мониторинг:
```bash
# Просмотр процессов Python
tasklist | findstr python

# Мониторинг памяти Redis
redis-cli info memory
```

Если возникают проблемы, создайте Issue с указанием:
- Версия Windows
- Версия Python 
- Текст ошибки
- Шаги воспроизведения


## Лицензия

Проект разработан для внутреннего использования турагентства.

---

**Версия:** 1.0.0  
**Последнее обновление:** 2025  
**Python:** 3.11+  
**FastAPI:** 0.104+# tours
