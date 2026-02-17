"""Tests for application/user_service.py — User CRUD operations."""

import pytest

from src.application.user_service import create_user, get_user, update_user
from src.domain.exceptions import TaxPilotError
from src.domain.schemas import UserCreate, UserUpdate


class TestCreateUser:
    """Tests for create_user()."""

    async def test_creates_user_with_display_name(self, db_session):
        data = UserCreate(display_name="Test User")
        user = await create_user(db_session, data)

        assert user.id is not None
        assert user.display_name == "Test User"
        assert user.locale_preference is None
        assert user.created_at is not None

    async def test_creates_user_without_display_name(self, db_session):
        data = UserCreate(display_name=None)
        user = await create_user(db_session, data)

        assert user.id is not None
        assert user.display_name is None
        assert user.locale_preference is None


class TestGetUser:
    """Tests for get_user()."""

    async def test_returns_existing_user(self, db_session):
        # Create a user first
        data = UserCreate(display_name="Existing User")
        created_user = await create_user(db_session, data)
        await db_session.commit()

        # Retrieve the user
        user = await get_user(db_session, created_user.id)

        assert user.id == created_user.id
        assert user.display_name == "Existing User"

    async def test_raises_not_found_for_nonexistent_user(self, db_session):
        with pytest.raises(TaxPilotError) as exc_info:
            await get_user(db_session, "nonexistent-uuid")

        assert exc_info.value.status_code == 404
        assert exc_info.value.error_code == "USER_NOT_FOUND"


class TestUpdateUser:
    """Tests for update_user()."""

    async def test_updates_display_name_only(self, db_session):
        # Create a user first
        data = UserCreate(display_name="Original Name")
        created_user = await create_user(db_session, data)
        await db_session.commit()

        # Update display name
        update_data = UserUpdate(display_name="Updated Name", locale_preference=None)
        updated_user = await update_user(db_session, created_user.id, update_data)

        assert updated_user.display_name == "Updated Name"
        assert updated_user.locale_preference is None

    async def test_updates_locale_preference_only(self, db_session):
        # Create a user first
        data = UserCreate(display_name="Test User")
        created_user = await create_user(db_session, data)
        await db_session.commit()

        # Update locale preference
        update_data = UserUpdate(display_name=None, locale_preference="en")
        updated_user = await update_user(db_session, created_user.id, update_data)

        assert updated_user.display_name == "Test User"
        assert updated_user.locale_preference == "en"

    async def test_updates_both_fields(self, db_session):
        # Create a user first
        data = UserCreate(display_name="Original Name")
        created_user = await create_user(db_session, data)
        await db_session.commit()

        # Update both fields
        update_data = UserUpdate(display_name="New Name", locale_preference="ja")
        updated_user = await update_user(db_session, created_user.id, update_data)

        assert updated_user.display_name == "New Name"
        assert updated_user.locale_preference == "ja"

    @pytest.mark.parametrize(
        "locale",
        ["ja", "en", "zh-TW", "zh-CN"],
    )
    async def test_accepts_valid_locales(self, db_session, locale):
        # Create a user first
        data = UserCreate(display_name="Test User")
        created_user = await create_user(db_session, data)
        await db_session.commit()

        # Update with valid locale
        update_data = UserUpdate(locale_preference=locale)
        updated_user = await update_user(db_session, created_user.id, update_data)

        assert updated_user.locale_preference == locale

    async def test_rejects_invalid_locale(self, db_session):
        # Create a user first
        data = UserCreate(display_name="Test User")
        created_user = await create_user(db_session, data)
        await db_session.commit()

        # Attempt to update with invalid locale
        update_data = UserUpdate(locale_preference="fr")

        with pytest.raises(TaxPilotError) as exc_info:
            await update_user(db_session, created_user.id, update_data)

        assert exc_info.value.status_code == 400
        assert exc_info.value.error_code == "INVALID_LOCALE"
        assert "fr" in exc_info.value.detail

    async def test_no_op_update_preserves_existing_data(self, db_session):
        # Create a user with initial data
        data = UserCreate(display_name="Original")
        created_user = await create_user(db_session, data)
        await db_session.commit()

        # Update with empty body (all None) — should be a no-op
        update_data = UserUpdate()
        updated_user = await update_user(db_session, created_user.id, update_data)

        assert updated_user.display_name == "Original"
        assert updated_user.locale_preference is None

    async def test_raises_not_found_for_nonexistent_user(self, db_session):
        update_data = UserUpdate(display_name="New Name")

        with pytest.raises(TaxPilotError) as exc_info:
            await update_user(db_session, "nonexistent-uuid", update_data)

        assert exc_info.value.status_code == 404
        assert exc_info.value.error_code == "USER_NOT_FOUND"
