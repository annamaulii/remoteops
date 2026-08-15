from sqlalchemy import inspect

from remoteops.database import engine


def test_organizations_table_has_expected_columns() -> None:
    inspector = inspect(engine)
    columns = inspector.get_columns("organizations")

    assert {column["name"] for column in columns} == {"id", "name", "created_at"}
    assert inspector.get_pk_constraint("organizations")["constrained_columns"] == [
        "id"
    ]
    assert {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("organizations")
    } == {("name",)}
