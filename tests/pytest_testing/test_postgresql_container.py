"""`@application_test(database=PostgreSQLContainer())` runs a test on PostgreSQL, built by the application's migrations.

One container serves every test of the process; without a running Docker these tests are skipped.
"""

import subprocess
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from snakeboot.boot.testing import TestApplication
from snakeboot.data import DataIntegrityViolationError
from snakeboot.sqlalchemy_data.schema_migrations import InvalidMigrationError
from snakeboot.sqlalchemy_data.testing import postgresql_database
from snakeboot.testing import (
    Autowired,
    PostgreSQLContainer,
    TestEnvironment,
    application_module_test,
    application_test,
)
from tests.pytest_testing.depot.deliveries.deliveries import DeliveryRecord, DeliveryRecords
from tests.pytest_testing.depot.depot_application import DepotApplication
from tests.pytest_testing.parcels.parcels import ParcelRecord, ParcelRecords, ParcelsApplication, SendParcel
from tests.pytest_testing.unfit.unfit_application import UnfitApplication


def docker_runs() -> bool:
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=30, check=False).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


pytestmark = pytest.mark.skipif(not docker_runs(), reason="a PostgreSQLContainer needs a running Docker")

POSTGRESQL = PostgreSQLContainer()

on_postgresql = application_test(application=ParcelsApplication, database=POSTGRESQL)


@on_postgresql
def test_the_schema_is_the_one_the_migrations_built(parcels: Autowired[ParcelRecords]) -> None:
    # The check of the status is in V1__create_parcel.sql only: the entity knows no such check.
    with pytest.raises(DataIntegrityViolationError):
        parcels.save(ParcelRecord(uuid4(), "ann", "LOST"))


@on_postgresql
class TestEveryTestGetsADatabaseOfItsOwn:
    send_parcel: Autowired[SendParcel]
    parcels: Autowired[ParcelRecords]

    def test_a_parcel_is_kept(self) -> None:
        self.send_parcel.execute("ann")

        assert self.parcels.count() == 1

    def test_the_parcel_of_the_test_above_is_gone(self) -> None:
        assert self.parcels.count() == 0


def test_migrations_that_lack_a_column_of_an_entity_stop_every_test_on_them() -> None:
    environment = TestEnvironment(database=POSTGRESQL)

    for _ in range(2):  # the second start fails on what the first found
        with pytest.raises(
            InvalidMigrationError, match=r"(?s)make_migration would still write:.*ALTER TABLE shelf ADD"
        ):
            TestApplication.start(UnfitApplication, environment=environment)


@application_module_test("tests.pytest_testing.depot.deliveries", application=DepotApplication, database=POSTGRESQL)
def test_a_slice_runs_every_migration_of_the_application(deliveries: Autowired[DeliveryRecords]) -> None:
    # snakeboot's own tables come with the shelves' migrations, which this slice leaves out; migrate runs them all.
    deliveries.save(DeliveryRecord(uuid4(), "ann"))

    assert deliveries.count() == 1


def test_closing_the_database_of_a_test_drops_its_copy() -> None:
    database = postgresql_database(POSTGRESQL.image, [ParcelRecord])
    url = database.engine.url

    database.close()

    server = create_engine(url.set(database="postgres"))
    with server.connect() as connection:
        copies = connection.execute(
            text("SELECT count(*) FROM pg_database WHERE datname = :name"), {"name": url.database}
        )
        assert copies.scalar() == 0
    server.dispose()
