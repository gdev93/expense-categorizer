import os
import pytest
from testcontainers.postgres import PostgresContainer

# Set DOCKER_HOST if not already set, to ensure testcontainers can find the Docker socket on MacOS
if "DOCKER_HOST" not in os.environ:
    user = os.environ.get("USER")
    if user:
        socket_path = f"unix:///Users/{user}/.docker/run/docker.sock"
        if os.path.exists(socket_path.replace("unix://", "")):
            os.environ["DOCKER_HOST"] = socket_path

@pytest.fixture(scope="session", autouse=True)
def postgres_container():
    if os.environ.get("USE_TESTCONTAINERS", "true").lower() == "false":
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
