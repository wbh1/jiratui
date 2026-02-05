from unittest.mock import MagicMock, Mock

from pydantic import SecretStr
import pytest

from jiratui.api_controller.controller import APIController
from jiratui.app import JiraApp
from jiratui.config import ApplicationConfiguration
from jiratui.models import WorkItemsSearchOrderBy
from jiratui.widgets.work_item_details.fields import IssueSummaryField
from jiratui.widgets.filters import AssigneeSearchInput


@pytest.fixture()
def app() -> JiraApp:
    config_mock = Mock(spec=ApplicationConfiguration)
    config_mock.configure_mock(
        jira_api_base_url='foo.bar',
        jira_api_username='foo',
        jira_api_token=SecretStr('bar'),
        jira_api_version=3,
        use_bearer_authentication=False,
        use_cert_authentication=False,
        cloud=True,
        ignore_users_without_email=True,
        default_project_key_or_id=None,
        active_sprint_on_startup=False,
        jira_account_id=None,
        jira_user_group_id='qwerty',
        tui_title=None,
        tui_custom_title=None,
        tui_title_include_jira_server_title=False,
        on_start_up_only_fetch_projects=False,
        log_file='',
        log_level='ERROR',
        theme=None,
        ssl=None,
        search_results_default_order=WorkItemsSearchOrderBy.CREATED_DESC,
        search_on_startup=False,
    )
    app = JiraApp(config_mock)
    app.api = APIController(config_mock)
    app._setup_logging = MagicMock()  # type:ignore[method-assign]
    return app


@pytest.mark.parametrize('widget_value, expected_value', [('a summary ', 'a summary'), ('', '')])
@pytest.mark.asyncio
async def test_issue_summary_field(widget_value, expected_value, app):
    async with app.run_test():
        widget = IssueSummaryField()
        widget.value = widget_value
        result = widget.validated_summary
        assert result == expected_value


@pytest.mark.asyncio
async def test_assignee_search_input_single_enter_selects_option(app):
    """Test that pressing Enter once selects an option and hides suggestions.

    This test demonstrates the double-enter bug: after selecting an option,
    the Input.Changed event fires and triggers a new search, causing the
    suggestions to re-appear.
    """
    from textual.widgets import Input, OptionList

    async with app.run_test() as pilot:
        widget = AssigneeSearchInput(id='test-assignee')
        await app.mount(widget)
        await pilot.pause()

        # Simulate search results
        options = [('Adam Smith', 'account-123'), ('Adam Jones', 'account-456')]
        widget.set_options(options)
        await pilot.pause()

        # Verify options are visible
        assert widget._options_visible

        # Simulate Enter key to select the first option
        option_list = widget.query_one(OptionList)
        option_list.highlighted = 0

        # Trigger the selection (this is what happens when Enter is pressed)
        widget._select_option(0)
        await pilot.pause()

        # After one selection, options should be hidden
        assert not widget._options_visible, "Options should be hidden after selection"
        assert widget.selection == 'account-123'

        # The input should contain the full name
        input_widget = widget.query_one(Input)
        assert input_widget.value == 'Adam Smith'

        # Wait a bit longer to ensure no delayed events cause options to re-appear
        await pilot.pause()
        await pilot.pause()

        # Options should STILL be hidden (this is where the bug manifests)
        assert not widget._options_visible, "Options should not re-appear after selection"
