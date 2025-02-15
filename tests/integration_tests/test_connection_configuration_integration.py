import pytest
import json

from pymongo import MongoClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from fidesops.models.client import ClientDetail
from fidesops.models.connectionconfig import ConnectionTestStatus
from fidesops.service.connectors import MongoDBConnector
from fidesops.service.connectors.sql_connector import MySQLConnector, MicrosoftSQLServerConnector
from fidesops.common_exceptions import ConnectionException
from fidesops.service.connectors import PostgreSQLConnector
from fidesops.service.connectors import get_connector
from fidesops.api.v1.scope_registry import (
    CONNECTION_CREATE_OR_UPDATE,
    CONNECTION_READ,
    STORAGE_READ,
)

from fidesops.api.v1.urn_registry import CONNECTIONS, V1_URL_PREFIX


class TestPostgresConnectionPutSecretsAPI:
    @pytest.fixture(scope="function")
    def url(self, oauth_client: ClientDetail, policy, connection_config) -> str:
        return f"{V1_URL_PREFIX}{CONNECTIONS}/{connection_config.key}/secret"

    @pytest.mark.integration
    def test_postgres_db_connection_incorrect_secrets(
        self,
        api_client: TestClient,
        db: Session,
        generate_auth_header,
        connection_config,
        url,
    ) -> None:
        auth_header = generate_auth_header(scopes=[CONNECTION_CREATE_OR_UPDATE])
        payload = {"host": "localhost", "port": "1234", "dbname": "my_test_db"}
        resp = api_client.put(
            url,
            headers=auth_header,
            json=payload,
        )
        assert resp.status_code == 200
        body = json.loads(resp.text)
        assert (
            body["msg"]
            == f"Secrets updated for ConnectionConfig with key: {connection_config.key}."
        )
        assert body["test_status"] == "failed"
        assert "Operational Error connecting to postgres db." == body["failure_reason"]
        db.refresh(connection_config)

        assert connection_config.secrets == {
            "host": "localhost",
            "port": 1234,
            "dbname": "my_test_db",
            "username": None,
            "password": None,
            "url": None,
        }
        assert connection_config.last_test_timestamp is not None
        assert connection_config.last_test_succeeded is False

    @pytest.mark.integration
    def test_postgres_db_connection_connect_with_components(
        self,
        url,
        api_client: TestClient,
        db: Session,
        generate_auth_header,
        connection_config,
    ) -> None:
        payload = {
            "host": "postgres_example",
            "dbname": "postgres_example",
            "username": "postgres",
            "password": "postgres",
        }

        auth_header = generate_auth_header(scopes=[CONNECTION_CREATE_OR_UPDATE])
        resp = api_client.put(
            url,
            headers=auth_header,
            json=payload,
        )
        assert resp.status_code == 200
        body = json.loads(resp.text)

        assert (
            body["msg"]
            == f"Secrets updated for ConnectionConfig with key: {connection_config.key}."
        )
        assert body["test_status"] == "succeeded"
        assert body["failure_reason"] is None
        db.refresh(connection_config)
        assert connection_config.secrets == {
            "host": "postgres_example",
            "port": None,
            "dbname": "postgres_example",
            "username": "postgres",
            "password": "postgres",
            "url": None,
        }
        assert connection_config.last_test_timestamp is not None
        assert connection_config.last_test_succeeded is True

    @pytest.mark.integration
    def test_postgres_db_connection_connect_with_url(
        self,
        url,
        api_client: TestClient,
        db: Session,
        generate_auth_header,
        connection_config,
    ) -> None:
        payload = {
            "url": "postgresql://postgres:postgres@postgres_example/postgres_example"
        }

        auth_header = generate_auth_header(scopes=[CONNECTION_CREATE_OR_UPDATE])
        resp = api_client.put(
            url,
            headers=auth_header,
            json=payload,
        )
        assert resp.status_code == 200
        body = json.loads(resp.text)

        assert (
            body["msg"]
            == f"Secrets updated for ConnectionConfig with key: {connection_config.key}."
        )
        assert body["failure_reason"] is None
        assert body["test_status"] == "succeeded"
        db.refresh(connection_config)
        assert connection_config.secrets == {
            "host": None,
            "port": None,
            "dbname": None,
            "username": None,
            "password": None,
            "url": payload["url"],
        }
        assert connection_config.last_test_timestamp is not None
        assert connection_config.last_test_succeeded is True


class TestPostgresConnectionTestSecretsAPI:
    @pytest.fixture(scope="function")
    def url(self, oauth_client: ClientDetail, policy, connection_config) -> str:
        return f"{V1_URL_PREFIX}{CONNECTIONS}/{connection_config.key}/test"

    @pytest.mark.integration
    def test_connection_configuration_test_not_authenticated(
        self,
        url,
        api_client: TestClient,
        db: Session,
        generate_auth_header,
        connection_config,
    ) -> None:
        assert connection_config.last_test_timestamp is None

        resp = api_client.get(url)
        assert resp.status_code == 401
        db.refresh(connection_config)
        assert connection_config.last_test_timestamp is None
        assert connection_config.last_test_succeeded is None

    @pytest.mark.integration
    def test_connection_configuration_test_incorrect_scopes(
        self,
        url,
        api_client: TestClient,
        db: Session,
        generate_auth_header,
        connection_config,
    ) -> None:
        assert connection_config.last_test_timestamp is None

        auth_header = generate_auth_header(scopes=[STORAGE_READ])
        resp = api_client.get(
            url,
            headers=auth_header,
        )
        assert resp.status_code == 403
        db.refresh(connection_config)
        assert connection_config.last_test_timestamp is None
        assert connection_config.last_test_succeeded is None

    @pytest.mark.integration
    def test_connection_configuration_test_failed_response(
        self,
        url,
        api_client: TestClient,
        db: Session,
        generate_auth_header,
        connection_config,
    ) -> None:
        assert connection_config.last_test_timestamp is None
        connection_config.secrets = {"host": "invalid_host"}
        connection_config.save(db)

        auth_header = generate_auth_header(scopes=[CONNECTION_READ])
        resp = api_client.get(
            url,
            headers=auth_header,
        )
        assert resp.status_code == 200
        body = json.loads(resp.text)

        db.refresh(connection_config)
        assert connection_config.last_test_timestamp is not None
        assert connection_config.last_test_succeeded is False
        assert body["test_status"] == "failed"
        assert "Operational Error connecting to postgres db." == body["failure_reason"]
        assert (
            body["msg"]
            == f"Test completed for ConnectionConfig with key: {connection_config.key}."
        )

    @pytest.mark.integration
    def test_connection_configuration_test(
        self,
        url,
        api_client: TestClient,
        db: Session,
        generate_auth_header,
        connection_config,
    ) -> None:
        assert connection_config.last_test_timestamp is None

        auth_header = generate_auth_header(scopes=[CONNECTION_READ])
        resp = api_client.get(
            url,
            headers=auth_header,
        )
        assert resp.status_code == 200
        body = json.loads(resp.text)

        assert (
            body["msg"]
            == f"Test completed for ConnectionConfig with key: {connection_config.key}."
        )
        assert body["failure_reason"] is None
        assert body["test_status"] == "succeeded"
        db.refresh(connection_config)
        assert connection_config.last_test_timestamp is not None
        assert connection_config.last_test_succeeded is True


class TestPostgresConnector:
    @pytest.mark.integration
    def test_postgres_db_connector(
        self,
        api_client: TestClient,
        db: Session,
        generate_auth_header,
        connection_config,
    ) -> None:
        connector = get_connector(connection_config)
        assert connector.__class__ == PostgreSQLConnector

        client = connector.client()
        assert client.__class__ == Engine
        assert connector.test_connection() == ConnectionTestStatus.succeeded

        connection_config.secrets = {"host": "bad_host"}
        connection_config.save(db)
        connector = get_connector(connection_config)
        with pytest.raises(ConnectionException):
            connector.test_connection()


class TestMySQLConnectionPutSecretsAPI:
    @pytest.fixture(scope="function")
    def url(self, oauth_client, policy, connection_config_mysql) -> str:
        return f"{V1_URL_PREFIX}{CONNECTIONS}/{connection_config_mysql.key}/secret"

    @pytest.mark.integration
    def test_mysql_db_connection_incorrect_secrets(
        self,
        api_client: TestClient,
        db: Session,
        generate_auth_header,
        connection_config_mysql,
        url,
    ) -> None:
        auth_header = generate_auth_header(scopes=[CONNECTION_CREATE_OR_UPDATE])
        payload = {"host": "mysql_example", "port": 1234, "dbname": "my_test_db"}
        resp = api_client.put(
            url,
            headers=auth_header,
            json=payload,
        )
        assert resp.status_code == 200
        body = json.loads(resp.text)
        assert (
            body["msg"]
            == f"Secrets updated for ConnectionConfig with key: {connection_config_mysql.key}."
        )
        assert body["test_status"] == "failed"
        assert "Operational Error connecting to mysql db." == body["failure_reason"]
        db.refresh(connection_config_mysql)

        assert connection_config_mysql.secrets == {
            "host": "mysql_example",
            "port": 1234,
            "dbname": "my_test_db",
            "username": None,
            "password": None,
            "url": None,
        }
        assert connection_config_mysql.last_test_timestamp is not None
        assert connection_config_mysql.last_test_succeeded is False

    @pytest.mark.integration
    def test_mysql_db_connection_connect_with_components(
        self,
        url,
        api_client: TestClient,
        db: Session,
        generate_auth_header,
        connection_config_mysql,
    ) -> None:
        payload = {
            "host": "mysql_example",
            "dbname": "mysql_example",
            "username": "mysql_user",
            "password": "mysql_pw",
        }

        auth_header = generate_auth_header(scopes=[CONNECTION_CREATE_OR_UPDATE])
        resp = api_client.put(
            url,
            headers=auth_header,
            json=payload,
        )
        assert resp.status_code == 200
        body = resp.json()

        assert (
            body["msg"]
            == f"Secrets updated for ConnectionConfig with key: {connection_config_mysql.key}."
        )
        assert body["test_status"] == "succeeded"
        assert body["failure_reason"] is None
        db.refresh(connection_config_mysql)
        assert connection_config_mysql.secrets == {
            "host": "mysql_example",
            "dbname": "mysql_example",
            "username": "mysql_user",
            "password": "mysql_pw",
            "url": None,
            "port": None,
        }
        assert connection_config_mysql.last_test_timestamp is not None
        assert connection_config_mysql.last_test_succeeded is True

    @pytest.mark.integration
    def test_mysql_db_connection_connect_with_url(
        self,
        url,
        api_client: TestClient,
        db: Session,
        generate_auth_header,
        connection_config_mysql,
    ) -> None:
        payload = {
            "url": "mysql+pymysql://mysql_user:mysql_pw@mysql_example/mysql_example"
        }

        auth_header = generate_auth_header(scopes=[CONNECTION_CREATE_OR_UPDATE])
        resp = api_client.put(
            url,
            headers=auth_header,
            json=payload,
        )
        assert resp.status_code == 200
        body = json.loads(resp.text)

        assert (
            body["msg"]
            == f"Secrets updated for ConnectionConfig with key: {connection_config_mysql.key}."
        )
        assert body["failure_reason"] is None
        assert body["test_status"] == "succeeded"
        db.refresh(connection_config_mysql)
        assert connection_config_mysql.secrets == {
            "host": None,
            "port": None,
            "dbname": None,
            "username": None,
            "password": None,
            "url": payload["url"],
        }
        assert connection_config_mysql.last_test_timestamp is not None
        assert connection_config_mysql.last_test_succeeded is True


class TestMySQLConnectionTestSecretsAPI:
    @pytest.fixture(scope="function")
    def url(self, oauth_client, policy, connection_config_mysql) -> str:
        return f"{V1_URL_PREFIX}{CONNECTIONS}/{connection_config_mysql.key}/test"

    @pytest.mark.integration
    def test_connection_configuration_test_not_authenticated(
        self,
        url,
        api_client: TestClient,
        db: Session,
        generate_auth_header,
        connection_config_mysql,
    ) -> None:
        assert connection_config_mysql.last_test_timestamp is None

        resp = api_client.get(url)
        assert resp.status_code == 401
        db.refresh(connection_config_mysql)
        assert connection_config_mysql.last_test_timestamp is None
        assert connection_config_mysql.last_test_succeeded is None

    @pytest.mark.integration
    def test_connection_configuration_test_incorrect_scopes(
        self,
        url,
        api_client: TestClient,
        db: Session,
        generate_auth_header,
        connection_config_mysql,
    ) -> None:
        assert connection_config_mysql.last_test_timestamp is None

        auth_header = generate_auth_header(scopes=[STORAGE_READ])
        resp = api_client.get(
            url,
            headers=auth_header,
        )
        assert resp.status_code == 403
        db.refresh(connection_config_mysql)
        assert connection_config_mysql.last_test_timestamp is None
        assert connection_config_mysql.last_test_succeeded is None

    @pytest.mark.integration
    def test_connection_configuration_test_failed_response(
        self,
        url,
        api_client: TestClient,
        db: Session,
        generate_auth_header,
        connection_config_mysql,
    ) -> None:
        assert connection_config_mysql.last_test_timestamp is None
        connection_config_mysql.secrets = {"host": "invalid_host"}
        connection_config_mysql.save(db)

        auth_header = generate_auth_header(scopes=[CONNECTION_READ])
        resp = api_client.get(
            url,
            headers=auth_header,
        )
        assert resp.status_code == 200
        body = json.loads(resp.text)

        db.refresh(connection_config_mysql)
        assert connection_config_mysql.last_test_timestamp is not None
        assert connection_config_mysql.last_test_succeeded is False
        assert body["test_status"] == "failed"
        assert "Operational Error connecting to mysql db." == body["failure_reason"]
        assert (
            body["msg"]
            == f"Test completed for ConnectionConfig with key: {connection_config_mysql.key}."
        )

    @pytest.mark.integration
    def test_connection_configuration_test(
        self,
        url,
        api_client: TestClient,
        db: Session,
        generate_auth_header,
        connection_config_mysql,
    ) -> None:
        assert connection_config_mysql.last_test_timestamp is None

        auth_header = generate_auth_header(scopes=[CONNECTION_READ])
        resp = api_client.get(
            url,
            headers=auth_header,
        )
        assert resp.status_code == 200
        body = json.loads(resp.text)

        assert (
            body["msg"]
            == f"Test completed for ConnectionConfig with key: {connection_config_mysql.key}."
        )
        assert body["failure_reason"] is None
        assert body["test_status"] == "succeeded"
        db.refresh(connection_config_mysql)
        assert connection_config_mysql.last_test_timestamp is not None
        assert connection_config_mysql.last_test_succeeded is True


class TestMySQLConnector:
    @pytest.mark.integration
    def test_mysql_db_connector(
        self,
        api_client: TestClient,
        db: Session,
        generate_auth_header,
        connection_config_mysql,
    ) -> None:
        connector = get_connector(connection_config_mysql)
        assert connector.__class__ == MySQLConnector

        client = connector.client()
        assert client.__class__ == Engine
        assert connector.test_connection() == ConnectionTestStatus.succeeded

        connection_config_mysql.secrets = {"host": "bad_host"}
        connection_config_mysql.save(db)
        connector = get_connector(connection_config_mysql)
        with pytest.raises(ConnectionException):
            connector.test_connection()


class TestMicrosoftSQLServerConnection:

    @pytest.fixture(scope="function")
    def url_put_secret(self, oauth_client, policy, connection_config_mssql) -> str:
        return f"{V1_URL_PREFIX}{CONNECTIONS}/{connection_config_mssql.key}/secret"

    @pytest.mark.integration
    def test_mssql_db_connection_incorrect_secrets(
            self,
            api_client: TestClient,
            db: Session,
            generate_auth_header,
            connection_config_mssql,
            url_put_secret,
    ) -> None:
        auth_header = generate_auth_header(scopes=[CONNECTION_CREATE_OR_UPDATE])
        payload = {
            "username": "sa",
            "password": "incorrect",
            "host": "mssql_example",
            "port": 1433,
            "dbname": "mssql_example",
            "url": None
        }
        resp = api_client.put(
            url_put_secret,
            headers=auth_header,
            json=payload,
        )
        assert resp.status_code == 200
        body = json.loads(resp.text)
        assert (
                body["msg"]
                == f"Secrets updated for ConnectionConfig with key: {connection_config_mssql.key}."
        )
        assert body["test_status"] == "failed"
        assert "Connection error." == body["failure_reason"]
        db.refresh(connection_config_mssql)

        assert connection_config_mssql.secrets == {
            "username": "sa",
            "password": "incorrect",
            "host": "mssql_example",
            "port": 1433,
            "dbname": "mssql_example",
            "url": None,
        }
        assert connection_config_mssql.last_test_timestamp is not None
        assert connection_config_mssql.last_test_succeeded is False

    @pytest.mark.integration
    def test_mssql_db_connection_connect_with_components(
            self,
            url_put_secret,
            api_client: TestClient,
            db: Session,
            generate_auth_header,
            connection_config_mssql,
    ) -> None:
        payload = {
            "username": "sa",
            "password": "Mssql_pw1",
            "host": "mssql_example",
            "port": 1433,
            "dbname": "mssql_example"
        }

        auth_header = generate_auth_header(scopes=[CONNECTION_CREATE_OR_UPDATE])
        resp = api_client.put(
            url_put_secret,
            headers=auth_header,
            json=payload,
        )
        assert resp.status_code == 200
        body = resp.json()

        assert (
                body["msg"]
                == f"Secrets updated for ConnectionConfig with key: {connection_config_mssql.key}."
        )
        assert body["test_status"] == "succeeded"
        assert body["failure_reason"] is None
        db.refresh(connection_config_mssql)
        assert connection_config_mssql.secrets == {
            "username": "sa",
            "password": "Mssql_pw1",
            "host": "mssql_example",
            "port": 1433,
            "dbname": "mssql_example",
            "url": None
        }
        assert connection_config_mssql.last_test_timestamp is not None
        assert connection_config_mssql.last_test_succeeded is True

    @pytest.mark.integration
    def test_mssql_db_connection_connect_with_url(
            self,
            url_put_secret,
            api_client: TestClient,
            db: Session,
            generate_auth_header,
            connection_config_mssql,
    ) -> None:
        payload = {
            "url": "mssql+pyodbc://sa:Mssql_pw1@mssql_example:1433/mssql_example?driver=ODBC+Driver+17+for+SQL+Server"
        }

        auth_header = generate_auth_header(scopes=[CONNECTION_CREATE_OR_UPDATE])
        resp = api_client.put(
            url_put_secret,
            headers=auth_header,
            json=payload,
        )
        assert resp.status_code == 200
        body = json.loads(resp.text)

        assert (
                body["msg"]
                == f"Secrets updated for ConnectionConfig with key: {connection_config_mssql.key}."
        )
        assert body["failure_reason"] is None
        assert body["test_status"] == "succeeded"
        db.refresh(connection_config_mssql)
        assert connection_config_mssql.secrets == {
            "username": None,
            "password": None,
            "host": None,
            "port": None,
            "dbname": None,
            "url": payload["url"],
        }
        assert connection_config_mssql.last_test_timestamp is not None
        assert connection_config_mssql.last_test_succeeded is True

    @pytest.fixture(scope="function")
    def url_test_secrets(self, oauth_client, policy, connection_config_mssql) -> str:
        return f"{V1_URL_PREFIX}{CONNECTIONS}/{connection_config_mssql.key}/test"

    @pytest.mark.integration
    def test_connection_configuration_test_not_authenticated(
            self,
            url_test_secrets,
            api_client: TestClient,
            db: Session,
            generate_auth_header,
            connection_config_mssql,
    ) -> None:
        assert connection_config_mssql.last_test_timestamp is None

        resp = api_client.get(url_test_secrets)
        assert resp.status_code == 401
        db.refresh(connection_config_mssql)
        assert connection_config_mssql.last_test_timestamp is None
        assert connection_config_mssql.last_test_succeeded is None

    @pytest.mark.integration
    def test_connection_configuration_test_incorrect_scopes(
            self,
            url_test_secrets,
            api_client: TestClient,
            db: Session,
            generate_auth_header,
            connection_config_mssql,
    ) -> None:
        assert connection_config_mssql.last_test_timestamp is None

        auth_header = generate_auth_header(scopes=[STORAGE_READ])
        resp = api_client.get(
            url_test_secrets,
            headers=auth_header,
        )
        assert resp.status_code == 403
        db.refresh(connection_config_mssql)
        assert connection_config_mssql.last_test_timestamp is None
        assert connection_config_mssql.last_test_succeeded is None

    @pytest.mark.integration
    def test_connection_configuration_test_failed_response(
            self,
            url_test_secrets,
            api_client: TestClient,
            db: Session,
            generate_auth_header,
            connection_config_mssql,
    ) -> None:
        assert connection_config_mssql.last_test_timestamp is None
        connection_config_mssql.secrets = {"host": "invalid_host"}
        connection_config_mssql.save(db)

        auth_header = generate_auth_header(scopes=[CONNECTION_READ])
        resp = api_client.get(
            url_test_secrets,
            headers=auth_header,
        )
        assert resp.status_code == 200
        body = json.loads(resp.text)

        db.refresh(connection_config_mssql)
        assert connection_config_mssql.last_test_timestamp is not None
        assert connection_config_mssql.last_test_succeeded is False
        assert body["test_status"] == "failed"
        assert "Connection error." == body["failure_reason"]
        assert (
                body["msg"]
                == f"Test completed for ConnectionConfig with key: {connection_config_mssql.key}."
        )

    @pytest.mark.integration
    def test_connection_configuration_test(
            self,
            url_test_secrets,
            api_client: TestClient,
            db: Session,
            generate_auth_header,
            connection_config_mssql,
    ) -> None:
        assert connection_config_mssql.last_test_timestamp is None

        auth_header = generate_auth_header(scopes=[CONNECTION_READ])
        resp = api_client.get(
            url_test_secrets,
            headers=auth_header,
        )
        assert resp.status_code == 200
        body = json.loads(resp.text)

        assert (
                body["msg"]
                == f"Test completed for ConnectionConfig with key: {connection_config_mssql.key}."
        )
        assert body["failure_reason"] is None
        assert body["test_status"] == "succeeded"
        db.refresh(connection_config_mssql)
        assert connection_config_mssql.last_test_timestamp is not None
        assert connection_config_mssql.last_test_succeeded is True

    @pytest.mark.integration
    def test_mssql_db_connector(
            self,
            api_client: TestClient,
            db: Session,
            generate_auth_header,
            connection_config_mssql,
    ) -> None:
        connector = get_connector(connection_config_mssql)
        assert connector.__class__ == MicrosoftSQLServerConnector

        client = connector.client()
        assert client.__class__ == Engine
        assert connector.test_connection() == ConnectionTestStatus.succeeded

        connection_config_mssql.secrets = {"host": "bad_host"}
        connection_config_mssql.save(db)
        connector = get_connector(connection_config_mssql)
        with pytest.raises(ConnectionException):
            connector.test_connection()


class TestMongoConnector:
    @pytest.mark.integration
    def test_mongo_db_connector(
        self,
        api_client: TestClient,
        db: Session,
        generate_auth_header,
        mongo_connection_config,
    ) -> None:
        connector = get_connector(mongo_connection_config)
        assert connector.__class__ == MongoDBConnector

        client = connector.client()
        assert client.__class__ == MongoClient
        assert connector.test_connection() == ConnectionTestStatus.succeeded

        mongo_connection_config.secrets = {"host": "bad_host"}
        mongo_connection_config.save(db)
        connector = get_connector(mongo_connection_config)
        with pytest.raises(ConnectionException):
            connector.test_connection()


class TestMongoConnectionPutSecretsAPI:
    @pytest.fixture(scope="function")
    def url(self, oauth_client: ClientDetail, policy, mongo_connection_config) -> str:
        return f"{V1_URL_PREFIX}{CONNECTIONS}/{mongo_connection_config.key}/secret"

    @pytest.mark.integration
    def test_mongo_db_connection_incorrect_secrets(
        self,
        url,
        api_client: TestClient,
        db: Session,
        generate_auth_header,
        mongo_connection_config,
    ) -> None:
        auth_header = generate_auth_header(scopes=[CONNECTION_CREATE_OR_UPDATE])
        payload = {"host": "incorrect_host", "port": "1234"}
        resp = api_client.put(
            url,
            headers=auth_header,
            json=payload,
        )
        assert resp.status_code == 200
        body = json.loads(resp.text)
        assert (
            body["msg"]
            == f"Secrets updated for ConnectionConfig with key: {mongo_connection_config.key}."
        )
        assert body["test_status"] == "failed"
        assert (
            "Server Selection Timeout Error connecting to MongoDB."
            == body["failure_reason"]
        )
        db.refresh(mongo_connection_config)

        assert mongo_connection_config.secrets == {
            "host": "incorrect_host",
            "port": 1234,
            "username": None,
            "password": None,
            "defaultauthdb": None,
            "url": None,
        }
        assert mongo_connection_config.last_test_timestamp is not None
        assert mongo_connection_config.last_test_succeeded is False

    @pytest.mark.integration
    def test_mongo_db_connection_connect_with_components(
        self,
        url,
        api_client: TestClient,
        db: Session,
        generate_auth_header,
        mongo_connection_config,
    ) -> None:
        payload = {
            "host": "mongodb_example",
            "defaultauthdb": "mongo_test",
            "username": "mongo_user",
            "password": "mongo_pass",
        }

        auth_header = generate_auth_header(scopes=[CONNECTION_CREATE_OR_UPDATE])
        resp = api_client.put(
            url,
            headers=auth_header,
            json=payload,
        )
        assert resp.status_code == 200
        body = json.loads(resp.text)

        assert (
            body["msg"]
            == f"Secrets updated for ConnectionConfig with key: {mongo_connection_config.key}."
        )
        assert body["test_status"] == "succeeded"
        assert body["failure_reason"] is None
        db.refresh(mongo_connection_config)
        assert mongo_connection_config.secrets == {
            "host": "mongodb_example",
            "defaultauthdb": "mongo_test",
            "username": "mongo_user",
            "password": "mongo_pass",
            "url": None,
            "port": None,
        }
        assert mongo_connection_config.last_test_timestamp is not None
        assert mongo_connection_config.last_test_succeeded is True

    @pytest.mark.integration
    def test_mongo_db_connection_connect_with_url(
        self,
        url,
        api_client: TestClient,
        db: Session,
        generate_auth_header,
        mongo_connection_config,
    ) -> None:
        payload = {"url": "mongodb://mongo_user:mongo_pass@mongodb_example/mongo_test"}

        auth_header = generate_auth_header(scopes=[CONNECTION_CREATE_OR_UPDATE])
        resp = api_client.put(
            url,
            headers=auth_header,
            json=payload,
        )
        assert resp.status_code == 200
        body = json.loads(resp.text)

        assert (
            body["msg"]
            == f"Secrets updated for ConnectionConfig with key: {mongo_connection_config.key}."
        )
        assert body["failure_reason"] is None
        assert body["test_status"] == "succeeded"
        db.refresh(mongo_connection_config)
        assert mongo_connection_config.secrets == {
            "host": None,
            "port": None,
            "defaultauthdb": None,
            "username": None,
            "password": None,
            "url": payload["url"],
        }

        assert mongo_connection_config.last_test_timestamp is not None
        assert mongo_connection_config.last_test_succeeded is True
