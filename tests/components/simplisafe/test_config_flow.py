"""Define tests for the SimpliSafe config flow."""
from unittest.mock import AsyncMock, patch

from simplipy.errors import (
    InvalidCredentialsError,
    PendingAuthorizationError,
    SimplipyError,
)

from homeassistant import data_entry_flow
from homeassistant.components.simplisafe import DOMAIN
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_USER
from homeassistant.const import CONF_CODE, CONF_PASSWORD, CONF_USERNAME

from tests.common import MockConfigEntry


async def test_duplicate_error(hass):
    """Test that errors are shown when duplicates are added."""
    conf = {
        CONF_USERNAME: "user@email.com",
        CONF_PASSWORD: "password",
        CONF_CODE: "1234",
    }

    MockConfigEntry(
        domain=DOMAIN,
        unique_id="user@email.com",
        data={
            CONF_USERNAME: "user@email.com",
            CONF_PASSWORD: "password",
            CONF_CODE: "1234",
        },
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data=conf
    )

    assert result["type"] == data_entry_flow.RESULT_TYPE_ABORT
    assert result["reason"] == "already_configured"


async def test_invalid_credentials(hass):
    """Test that invalid credentials throws an error."""
    conf = {CONF_USERNAME: "user@email.com", CONF_PASSWORD: "password"}

    with patch(
        "homeassistant.components.simplisafe.config_flow.get_api",
        new=AsyncMock(side_effect=InvalidCredentialsError),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}, data=conf
        )
        assert result["errors"] == {"base": "invalid_auth"}


async def test_options_flow(hass):
    """Test config flow options."""
    conf = {CONF_USERNAME: "user@email.com", CONF_PASSWORD: "password"}

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="abcde12345",
        data=conf,
        options={CONF_CODE: "1234"},
    )
    entry.add_to_hass(hass)

    with patch(
        "homeassistant.components.simplisafe.async_setup_entry", return_value=True
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        result = await hass.config_entries.options.async_init(entry.entry_id)

        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "init"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"], user_input={CONF_CODE: "4321"}
        )

        assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
        assert entry.options == {CONF_CODE: "4321"}


async def test_show_form(hass):
    """Test that the form is served with no input."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["step_id"] == "user"


async def test_step_reauth(hass):
    """Test that the reauth step works."""
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="user@email.com",
        data={
            CONF_USERNAME: "user@email.com",
            CONF_PASSWORD: "password",
            CONF_CODE: "1234",
        },
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_REAUTH},
        data={CONF_CODE: "1234", CONF_USERNAME: "user@email.com"},
    )
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"])
    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["step_id"] == "reauth_confirm"

    with patch(
        "homeassistant.components.simplisafe.async_setup_entry", return_value=True
    ), patch("homeassistant.components.simplisafe.config_flow.get_api"), patch(
        "homeassistant.config_entries.ConfigEntries.async_reload"
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={CONF_PASSWORD: "password"}
        )
        assert result["type"] == data_entry_flow.RESULT_TYPE_ABORT
        assert result["reason"] == "reauth_successful"

    assert len(hass.config_entries.async_entries()) == 1


async def test_step_user(hass):
    """Test that the user step works (without MFA)."""
    conf = {
        CONF_USERNAME: "user@email.com",
        CONF_PASSWORD: "password",
        CONF_CODE: "1234",
    }

    with patch(
        "homeassistant.components.simplisafe.async_setup_entry", return_value=True
    ), patch(
        "homeassistant.components.simplisafe.config_flow.get_api", new=AsyncMock()
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}, data=conf
        )

        assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
        assert result["title"] == "user@email.com"
        assert result["data"] == {
            CONF_USERNAME: "user@email.com",
            CONF_PASSWORD: "password",
            CONF_CODE: "1234",
        }


async def test_step_user_mfa(hass):
    """Test that the user step works when MFA is in the middle."""
    conf = {
        CONF_USERNAME: "user@email.com",
        CONF_PASSWORD: "password",
        CONF_CODE: "1234",
    }

    with patch(
        "homeassistant.components.simplisafe.config_flow.get_api",
        new=AsyncMock(side_effect=PendingAuthorizationError),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}, data=conf
        )
        assert result["step_id"] == "mfa"

    with patch(
        "homeassistant.components.simplisafe.config_flow.get_api",
        new=AsyncMock(side_effect=PendingAuthorizationError),
    ):
        # Simulate the user pressing the MFA submit button without having clicked
        # the link in the MFA email:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={}
        )
        assert result["step_id"] == "mfa"

    with patch(
        "homeassistant.components.simplisafe.async_setup_entry", return_value=True
    ), patch(
        "homeassistant.components.simplisafe.config_flow.get_api", new=AsyncMock()
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={}
        )

        assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
        assert result["title"] == "user@email.com"
        assert result["data"] == {
            CONF_USERNAME: "user@email.com",
            CONF_PASSWORD: "password",
            CONF_CODE: "1234",
        }


async def test_unknown_error(hass):
    """Test that an unknown error raises the correct error."""
    conf = {CONF_USERNAME: "user@email.com", CONF_PASSWORD: "password"}

    with patch(
        "homeassistant.components.simplisafe.config_flow.get_api",
        new=AsyncMock(side_effect=SimplipyError),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}, data=conf
        )
        assert result["errors"] == {"base": "unknown"}
