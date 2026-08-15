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


def test_users_table_has_expected_columns() -> None:
    inspector = inspect(engine)
    columns = inspector.get_columns("users")

    assert {column["name"] for column in columns} == {
        "id",
        "email",
        "password_hash",
        "created_at",
    }
    assert inspector.get_pk_constraint("users")["constrained_columns"] == ["id"]
    assert {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("users")
    } == {("email",)}


def test_organization_memberships_table_has_expected_columns() -> None:
    inspector = inspect(engine)
    columns = inspector.get_columns("organization_memberships")

    assert {column["name"] for column in columns} == {
        "organization_id",
        "user_id",
        "role",
        "created_at",
    }
    assert set(
        inspector.get_pk_constraint("organization_memberships")[
            "constrained_columns"
        ]
    ) == {"organization_id", "user_id"}
    assert {
        constraint["name"]
        for constraint in inspector.get_check_constraints(
            "organization_memberships"
        )
    } == {"valid_organization_role"}
