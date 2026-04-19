# 🏘️ Mezha
**Live Demo:** [apex-logic.online](https://apex-logic.online)

Mezha - веб-застосунок на FastAPI для автоматизованого аудиту земельних і майнових реєстрів територіальних громад.

Система:
- імпортує реєстри (CSV/XLSX),
- знаходить невідповідності,
- формує аномалії (`RED`/`GREEN`),
- проводить їх через рольовий workflow: `ADMIN -> VOLUNTEER -> INSPECTOR`.

## 🎯 Ключові можливості

- Імпорт земельного та майнового реєстрів (`/data/upload-registers`).
- Запуск аудиту з генерацією аномалій (`/data/run-audit`).
- Робота з кейсами в ролях: адміністратор, волонтер, інспектор.
- Фото-звіти волонтерів з прив'язкою до аномалії.
- Журнал дій (`/api/audit-logs`) для прозорого контролю.

## 👥 Ролі доступу

- `ADMIN`:
  - завантажує реєстри;
  - запускає аудит;
  - приймає первинне рішення по `PENDING_ADMIN`;
  - бачить статистику та журнал аудиту.
- `VOLUNTEER`:
  - переглядає пул польових задач;
  - бере задачу в роботу;
  - надсилає фото + коментар.
- `INSPECTOR`:
  - перевіряє звіти волонтерів;
  - фінально підтверджує або відхиляє кейс.

## 🚦 Статуси аномалії

1. `PENDING_ADMIN` - створена системою, очікує рішення адміністратора.
2. `NEW` - підтверджена адміністратором, доступна в пулі волонтерів.
3. `IN_WORK` - взята волонтером у роботу.
4. `PENDING_INSPECTOR` - волонтер надіслав звіт, очікує перевірки.
5. `RESOLVED` - інспектор підтвердив кейс.
6. `DISMISSED` - кейс відхилено.

## 🔐 Демо-користувачі

При першому запуску бекенда виконується `scripts/seed.py`, який створює базові акаунти.

> Увага: змініть ці паролі перед продакшен-розгортанням.

| Користувач | Пароль | Роль |
| --- | --- | --- |
| `admin_otg` | `admin123` | `ADMIN` |
| `inspector_ivan` | `ins123` | `INSPECTOR` |
| `inspector_olena` | `ins456` | `INSPECTOR` |
| `volunteer_marta` | `vol123` | `VOLUNTEER` |
| `volunteer_oleg` | `vol456` | `VOLUNTEER` |

## 🚀 Швидкий старт (Docker)

Рекомендований спосіб запуску: підіймає PostgreSQL, застосовує міграції, запускає seed і стартує API.

```bash
cp .env.example .env
docker compose up --build
```

Після старту:
- UI: `http://localhost:8000/`
- Swagger: `http://localhost:8000/docs`

## 💻 Локальний запуск (без Docker)

1) Підготуйте PostgreSQL і створіть БД (наприклад, `assetvision`).

2) Створіть `.env` на базі прикладу та вкажіть коректний `DATABASE_URL`.

3) Встановіть залежності:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

4) Застосуйте міграції та створіть демо-користувачів:

```bash
alembic upgrade head
python scripts/seed.py
```

5) Запустіть застосунок:

```bash
uvicorn app.main:app --reload
```

## ⚙️ Конфігурація (`.env`)

Мінімально необхідно:
- `DATABASE_URL` - підключення до PostgreSQL.
- `SECRET_KEY` - ключ для access JWT.
- `REFRESH_SECRET_KEY` - ключ для refresh JWT.

Корисні додаткові змінні:
- `OPENAI_API_KEY` - для AI-збагачення в аудиті.
- `MEDIA_ROOT` - директорія збереження фото-звітів.
- `PROJECT_NAME` - назва застосунку у документації API.

Приклад конфігурації: `.env.example`.

## 📡 API (коротка карта)

Усі захищені ендпоїнти потребують авторизації. Підтримуються Bearer-токен і `access_token` cookie (HTMX flow).

### UI

| Метод | Шлях | Доступ |
| --- | --- | --- |
| `GET` | `/` | публічний |
| `GET` | `/login` | публічний |
| `GET` | `/admin` | `ADMIN` |
| `GET` | `/volunteer` | `VOLUNTEER` |
| `GET` | `/inspector` | `INSPECTOR` |

### Авторизація (`/api/auth`)

| Метод | Шлях | Опис |
| --- | --- | --- |
| `POST` | `/api/auth/login` | логін (JSON/Form), видає токени, ставить `access_token` cookie |
| `POST` | `/api/auth/refresh` | оновлює access/refresh пару за `refresh_token` |
| `POST` | `/api/auth/logout` | очищає cookie, повертає редірект для HTMX |

### Імпорт та аудит (`ADMIN`)

| Метод | Шлях | Опис |
| --- | --- | --- |
| `POST` | `/data/upload-registers` | приймає `land_file` + `real_estate_file` |
| `POST` | `/data/run-audit` | запускає аудит і створення аномалій |
| `GET` | `/api/audit-logs` | журнал дій |

### Аномалії (`/api/anomalies`)

| Метод | Шлях | Доступ | Опис |
| --- | --- | --- | --- |
| `GET` | `/api/anomalies` | `ADMIN` | список усіх аномалій |
| `GET` | `/api/anomalies/stats` | `ADMIN` | статистика по статусах |
| `GET` | `/api/anomalies/pending-admin` | `ADMIN` | черга `PENDING_ADMIN` |
| `POST` | `/api/anomalies/{anomaly_id}/admin-decision` | `ADMIN` | первинне рішення |
| `GET` | `/api/anomalies/pool` | `VOLUNTEER` | пул доступних задач |
| `POST` | `/api/anomalies/{anomaly_id}/take` | `VOLUNTEER` | взяти задачу в роботу |
| `POST` | `/api/anomalies/{anomaly_id}/volunteer-report` | `VOLUNTEER` | надіслати фото-звіт |
| `GET` | `/api/anomalies/pending-validation` | `INSPECTOR` | черга на перевірку |
| `POST` | `/api/anomalies/{anomaly_id}/report` | `INSPECTOR` | фінальне рішення інспектора |

## 🛠 Технологічний стек

- Backend: FastAPI, Uvicorn, Python
- Database: PostgreSQL, SQLAlchemy 2 (async), asyncpg, Alembic
- Frontend: Jinja2, HTMX, Alpine.js, Tailwind CSS
- Data processing: Pandas, OpenPyXL
- Security: python-jose, passlib/bcrypt