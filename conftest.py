import logging
import os
import socket

import pytest
from django.conf import settings as django_settings
from testcontainers.core.wait_strategies import LogMessageWaitStrategy
from testcontainers.postgres import PostgresContainer

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
    django_settings.SECRET_KEY = "notasecret"

def is_port_open(host, port, timeout=2):
    """
    Check if a specific TCP port is open on a host.
    Returns True if open, False otherwise.
    """
    # Create a TCP socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        # Attempt to connect to the host and port
        result = s.connect_ex((host, port))
        # connect_ex returns 0 if the connection was successful
        return result == 0

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
    if not is_port_open("localhost", 8080):
        logging.info("No ryuk instance found")
        yield None
        return

    with PostgresContainer("pgvector/pgvector:pg15") as postgres:
        postgres.start()
        postgres.waiting_for(LogMessageWaitStrategy("database system is ready to accept connections"))
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