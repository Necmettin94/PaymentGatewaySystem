from sqlalchemy import text

from app.infrastructure.database.session import engine


def test_isolation_level_is_repeatable_read():
    with engine.connect() as conn:
        result = conn.execute(text("SHOW transaction_isolation")).fetchone()
        isolation_level = result[0]

        assert (
            isolation_level.lower() == "repeatable read"
        ), f"Expected REPEATABLE READ isolation, got {isolation_level}"


def test_pessimistic_locking_syntax(db):
    from app.infrastructure.models.user import User

    user = User(
        email="lock_test@example.com",
        full_name="Lock Test",
        hashed_password="test",
    )
    db.add(user)
    db.commit()

    from sqlalchemy import select

    stmt = select(User).where(User.email == "lock_test@example.com").with_for_update()
    locked_user = db.execute(stmt).scalar_one()

    assert locked_user is not None
    assert locked_user.email == "lock_test@example.com"

    db.commit()
