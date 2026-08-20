# Справочник команд для администрирования кодовой базы

```bash
ssh mynamemyway@139.100.207.**
cd /home/mynamemyway/projects/antoshkin-pwa-card

# Код
git pull
nano .env
docker-compose down
docker-compose up -d --build

# Логи
docker-compose logs -f app
docker-compose logs nginx
docker-compose logs nginx | grep -E "phpunit|containers/json|allow_url_include"

# Запуск
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Скачать бэкап
scp mynamemyway@91.206.14.93:/home/mynamemyway/projects/antoshkin-pwa-card/backups/loyalty_20260425_163542.db ~/Downloads/

# Заглянуть в базу
docker-compose exec app python -c "import sqlite3; conn = sqlite3.connect('data/loyalty.db'); c = conn.cursor(); c.execute('SELECT phone, sms_code FROM users WHERE phone=\"`+7_ТЕЛЕФОН`\"'); print(c.fetchone()); conn.close()"

# Миграция локально
python scripts/migrate_add_check_call_fields.py

# Миграция в Docker
docker-compose exec app python scripts_migrate_add_check_call_fields.py
```
