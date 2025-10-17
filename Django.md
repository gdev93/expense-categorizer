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
    python manage.py runserver
   ```