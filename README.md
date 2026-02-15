### Server startup
1) Create a virtualenv
2) install requirements
    ```bash
    python -m pip install -r requirements.txt
    ```
3) spin up the test db:
    ```bash
   docker compose up -d
   ```
4) start django:
    ```bash
    python manage.py makemigrations
    python manage.py migrate
    python manage.py runserver
    ```

### Development
To use in-memory Celery (no Redis required), set the following environment variables:
```bash
export CELERY_TASK_ALWAYS_EAGER=True
export CELERY_BROKER_URL=memory://
export CELERY_RESULT_BACKEND=cache+memory://
```