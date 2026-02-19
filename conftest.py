import os
import pytest
from testcontainers.postgres import PostgresContainer
from django.conf import settings as django_settings

if "DOCKER_HOST" not in os.environ:
    user = os.environ.get("USER")
    if user:
        socket_path = f"unix:///Users/{user}/.docker/run/docker.sock"
        if os.path.exists(socket_path.replace("unix://", "")):
            os.environ["DOCKER_HOST"] = socket_path


@pytest.fixture(scope='session', autouse=True)
def configure_test_settings():
    django_settings.STORAGES = {
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }

@pytest.fixture(scope="session", autouse=True)
def postgres_container(request):
    if os.environ.get("USE_TESTCONTAINERS", "true").lower() == "false":
        yield None
        return

    # Check if any collected test needs the database
    # This avoids starting the container for standalone tests that don't use Django DB
    needs_db = any(item.get_closest_marker("django_db") for item in request.session.items)
    
    if not needs_db:
        yield None
        return

    postgres = PostgresContainer("pgvector/pgvector:pg15")
    postgres.start()
    
    os.environ["DB_HOST"] = str(postgres.get_container_host_ip())
    os.environ["DB_PORT"] = str(postgres.get_exposed_port(5432))
    os.environ["DB_USER"] = str(postgres.username)
    os.environ["DB_PASSWORD"] = str(postgres.password)
    os.environ["DB_NAME"] = str(postgres.dbname)
    
    from django.conf import settings
    settings.DATABASES['default']['HOST'] = os.environ["DB_HOST"]
    settings.DATABASES['default']['PORT'] = os.environ["DB_PORT"]
    settings.DATABASES['default']['USER'] = os.environ["DB_USER"]
    settings.DATABASES['default']['PASSWORD'] = os.environ["DB_PASSWORD"]
    settings.DATABASES['default']['NAME'] = os.environ["DB_NAME"]
    
    yield postgres
    
    postgres.stop()
