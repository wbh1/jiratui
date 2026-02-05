# ABOUTME: Tests for the server-side assignee search feature.
# ABOUTME: Covers DC API param mapping and widget UserSearchRequested message.
from unittest.mock import Mock

import httpx
import pytest
import respx

from pydantic import SecretStr

from jiratui.api.api import JiraDataCenterAPI
from jiratui.config import ApplicationConfiguration
from jiratui.utils.test_utilities import get_url_pattern


@pytest.fixture
def dc_config():
    """Config with all attributes needed by JiraDataCenterAPI client init."""
    config = Mock(spec=ApplicationConfiguration)
    config.configure_mock(
        ssl=None,
        use_bearer_authentication=False,
        use_cert_authentication=False,
        cloud=False,
    )
    return config


@pytest.fixture
def dc_api(dc_config):
    return JiraDataCenterAPI('https://jira.example.com', 'user', 'pass', dc_config)


class TestDCUserAssignableSearch:
    """JiraDataCenterAPI.user_assignable_search must send 'username', not 'query'."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_query_is_sent_as_username_param(self, dc_api):
        route = respx.get(get_url_pattern('user/assignable/search'))
        route.mock(return_value=httpx.Response(200, json=[]))

        await dc_api.user_assignable_search(issue_key='ABC-1', query='adam')

        assert route.called
        request_params = dict(route.calls.last.request.url.params)
        assert 'username' in request_params
        assert request_params['username'] == 'adam'
        assert 'query' not in request_params

    @pytest.mark.asyncio
    @respx.mock
    async def test_no_username_param_when_query_is_none(self, dc_api):
        route = respx.get(get_url_pattern('user/assignable/search'))
        route.mock(return_value=httpx.Response(200, json=[]))

        await dc_api.user_assignable_search(issue_key='ABC-1')

        assert route.called
        request_params = dict(route.calls.last.request.url.params)
        assert 'username' not in request_params
        assert 'query' not in request_params


class TestUserSearchRequestedMessage:
    """All assignee selectors share the same UserSearchRequested message via inheritance."""

    def test_base_widget_message_carries_query(self):
        from jiratui.widgets.filters import AssigneeSearchInput

        msg = AssigneeSearchInput.UserSearchRequested('adam')
        assert msg.query == 'adam'

    def test_filter_widget_inherits_message(self):
        from jiratui.widgets.filters import AssigneeSearchInput, UserSelectionInput

        assert UserSelectionInput.UserSearchRequested is AssigneeSearchInput.UserSearchRequested

    def test_details_widget_inherits_message(self):
        from jiratui.widgets.filters import AssigneeSearchInput
        from jiratui.widgets.work_item_details.fields import IssueDetailsAssigneeSelection

        assert IssueDetailsAssigneeSelection.UserSearchRequested is AssigneeSearchInput.UserSearchRequested

    def test_create_widget_inherits_message(self):
        from jiratui.widgets.create_work_item.fields import CreateWorkItemAssigneeSelectionInput
        from jiratui.widgets.filters import AssigneeSearchInput

        assert CreateWorkItemAssigneeSelectionInput.UserSearchRequested is AssigneeSearchInput.UserSearchRequested
