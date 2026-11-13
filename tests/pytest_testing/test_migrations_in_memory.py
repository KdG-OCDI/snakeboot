"""On SQLite in memory, a test's application runs on the schema its own migrations build, as Flyway does on H2.

The migrations are those `migrate` runs, and they run once per process; every test copies the result. First the
schema is compared with the entities, like `ddl-auto=validate`: what the migrations lack stops every test on them.
"""

from uuid import UUID, uuid4

import pytest

from snakeboot.boot.testing import TestApplication
from snakeboot.data import DataIntegrityViolationError
from snakeboot.sqlalchemy_data.schema_migrations import InvalidMigrationError
from snakeboot.testing import Autowired, application_module_test, application_test
from tests.pytest_testing.depot.deliveries.deliveries import DeliveryRecord, DeliveryRecords
from tests.pytest_testing.depot.depot_application import DepotApplication
from tests.pytest_testing.parcels.parcels import ParcelRecord, ParcelRecords, ParcelsApplication
from tests.pytest_testing.unfit.unfit_application import UnfitApplication

parcels_test = application_test(application=ParcelsApplication)


@parcels_test
def test_the_schema_is_the_one_the_migrations_built(parcels: Autowired[ParcelRecords]) -> None:
    # The check of the status is in V1__create_parcel.sql only: the entity knows no such check.
    with pytest.raises(DataIntegrityViolationError):
        parcels.save(ParcelRecord(uuid4(), "ann", "LOST"))


@parcels_test
def test_a_uuid_of_decimal_digits_only_stays_a_uuid(parcels: Autowired[ParcelRecords]) -> None:
    # V1 declares parcel_id UUID, a type name that SQLite reads as a number wherever a value looks like one.
    identifiers = [
        UUID(int=7),
        UUID("12345678-1234-1234-1234-123456789012"),
        UUID("12345678-1234-1234-1234-123456789013"),
    ]
    for identifier in identifiers:
        parcels.save(ParcelRecord(identifier, "ann", "SENT"))

    assert sorted(parcel.parcel_id for parcel in parcels.find_all()) == identifiers
    assert all(parcels.find_by_id(identifier) is not None for identifier in identifiers)


@parcels_test
class TestEveryTestGetsACopyOfItsOwn:
    parcels: Autowired[ParcelRecords]

    def test_a_parcel_is_kept(self) -> None:
        self.parcels.save(ParcelRecord(uuid4(), "ann", "SENT"))

        assert self.parcels.count() == 1

    def test_the_parcel_of_the_test_above_is_gone(self) -> None:
        assert self.parcels.count() == 0


def test_migrations_that_lack_a_column_of_an_entity_stop_every_test_on_them() -> None:
    for _ in range(2):  # the second start fails on what the first found
        with pytest.raises(
            InvalidMigrationError, match=r"(?s)make_migration would still write.*ALTER TABLE shelf ADD COLUMN label"
        ):
            TestApplication.start(UnfitApplication)


@application_module_test("tests.pytest_testing.depot.deliveries", application=DepotApplication)
def test_a_module_slice_runs_every_migration_of_the_application(deliveries: Autowired[DeliveryRecords]) -> None:
    # snakeboot's own tables come with the shelves' migrations, which this slice leaves out; migrate runs them all.
    deliveries.save(DeliveryRecord(uuid4(), "ann"))

    assert deliveries.count() == 1
