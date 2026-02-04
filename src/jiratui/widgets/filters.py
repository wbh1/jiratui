from textual import events, on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.reactive import Reactive, reactive
from textual.widgets import Checkbox, Input, OptionList, Select

from jiratui.constants import ASSIGNEE_SEARCH_DEBOUNCE_SECONDS, FULL_TEXT_SEARCH_DEFAULT_MINIMUM_TERM_LENGTH
from jiratui.widgets.base import DateInput
from jiratui.widgets.jql import JQLEditorScreen


class ProjectSelectionInput(Select):
    HELP = 'See Projects List section in the help'

    projects: Reactive[dict | None] = reactive(None, always_update=True)
    """A dictionary with 2 keys: projects: list and selection: str | None"""

    def __init__(self, projects: list):
        super().__init__(
            options=projects,
            prompt='Select a project',
            name='project',
            id='jira-project-selector',
            type_to_search=True,
            compact=True,
            classes='jira-selector',
        )
        self.border_title = 'Project'
        self.border_subtitle = '(p)'

    @property
    def help_anchor(self) -> str:
        return '#projects-list'

    def watch_projects(self, projects: dict | None = None) -> None:
        self.clear()
        if projects and (items := projects.get('projects', []) or []):
            options = [(f'({project.key}) {project.name}', project.key) for project in items]
            self.set_options(options)
            if selection := projects.get('selection'):
                for option in options:
                    if option[1] == selection:
                        self.value = option[1]
                        break


class IssueTypeSelectionInput(Select):
    HELP = 'See Search by Work Item Type section in the help'

    def __init__(self, types: list):
        super().__init__(
            options=types,
            prompt='Select issue type',
            name='issue_types',
            id='jira-issue-types-selector',
            type_to_search=True,
            compact=True,
            classes='jira-selector',
        )
        self.border_title = 'Issue Type'
        self.border_subtitle = '(t)'

    @property
    def help_anchor(self) -> str:
        return '#search-by-work-item-type'


class IssueStatusSelectionInput(Select):
    HELP = 'See Search by Status section in the help'
    WIDGET_ID = 'jira-issue-status-selector'

    statuses: Reactive[list[tuple[str, str]] | None] = reactive(None, always_update=True)

    def __init__(self, statuses: list):
        super().__init__(
            options=statuses,
            prompt='Select a status',
            name='issue_status',
            id=self.WIDGET_ID,
            type_to_search=True,
            compact=True,
            classes='jira-selector',
        )
        self.border_title = 'Status'
        self.border_subtitle = '(s)'

    @property
    def help_anchor(self) -> str:
        return '#search-by-status'

    async def watch_statuses(self, statuses: list[tuple[str, str]] | None = None) -> None:
        self.clear()
        await self.recompose()
        self.set_options(statuses or [])


class AssigneeSearchInput(Vertical):
    """Search-and-select autocomplete for assignees.

    An Input for typing a search query sits above an OptionList that appears
    when results arrive.  Arrow keys and Enter drive the OptionList while the
    Input keeps focus; Escape dismisses the list.
    """

    can_focus = True

    class UserSearchRequested(Message):
        """Posted when the user has typed enough characters to trigger a server-side search."""

        def __init__(self, query: str):
            self.query = query
            super().__init__()

    def __init__(self, id: str, **kwargs):
        super().__init__(id=id, **kwargs)
        self.styles.height = 'auto'
        self._selection: str | None = None
        self._options: list[tuple[str, str]] = []
        self._search_timer = None
        self._programmatic_update = False
        self._options_visible = False

    def compose(self) -> ComposeResult:
        yield Input(placeholder='Search assignees...', compact=True)
        yield OptionList()

    def on_mount(self) -> None:
        self.query_one(OptionList).styles.display = 'none'
        self.query_one(OptionList).styles.max_height = 6

    def on_focus(self) -> None:
        """Redirect focus to the inner Input so keyboard events land there."""
        self.query_one(Input).focus()

    # ------------------------------------------------------------------
    # public interface
    # ------------------------------------------------------------------

    @property
    def selection(self) -> str | None:
        """The account_id of the currently selected user, or None."""
        return self._selection

    def set_options(self, options: list[tuple[str, str]]) -> None:
        """Replace the option list with *options* and show it."""
        self._options = options
        option_list = self.query_one(OptionList)
        option_list.set_options([name for name, _ in options])
        if options:
            option_list.highlighted = 0
            self._show_options()
        else:
            self._hide_options()

    def set_value(self, account_id: str) -> None:
        """Pre-select the user whose account_id matches."""
        for name, aid in self._options:
            if aid == account_id:
                self._selection = account_id
                self._write_input(name)
                self._hide_options()
                return

    def clear(self) -> None:
        """Reset selection and hide the option list."""
        self._selection = None
        self._options = []
        self._write_input('')
        self._hide_options()

    # ------------------------------------------------------------------
    # event handlers
    # ------------------------------------------------------------------

    @on(Input.Changed)
    def _on_input_changed(self, event: Input.Changed) -> None:
        """Debounce typing and post a search request when the query is long enough."""
        if self._programmatic_update:
            return
        if self._search_timer:
            self._search_timer.stop()
            self._search_timer = None
        # New typing always clears a previous selection
        self._selection = None
        query = (event.value or '').strip()
        if len(query) >= FULL_TEXT_SEARCH_DEFAULT_MINIMUM_TERM_LENGTH:
            self._search_timer = self.set_timer(
                ASSIGNEE_SEARCH_DEBOUNCE_SECONDS,
                lambda: self.post_message(self.UserSearchRequested(query)),
            )
        else:
            self._hide_options()

    @on(Input.Submitted)
    def _on_input_submitted(self, event: Input.Submitted) -> None:
        """Enter selects the highlighted option when the list is visible."""
        if self._options_visible and self.query_one(OptionList).highlighted is not None:
            event.stop()
            self._select_option(self.query_one(OptionList).highlighted)

    def on_key(self, event: events.Key) -> None:
        """Arrow keys and Escape drive the option list without moving focus."""
        if not self._options_visible:
            return
        option_list = self.query_one(OptionList)
        if event.key == 'down':
            event.stop()
            event.prevent_default()
            highlighted = option_list.highlighted
            if highlighted is not None and highlighted < option_list.option_count - 1:
                option_list.highlighted = highlighted + 1
            elif highlighted is None and option_list.option_count > 0:
                option_list.highlighted = 0
        elif event.key == 'up':
            event.stop()
            event.prevent_default()
            highlighted = option_list.highlighted
            if highlighted is not None and highlighted > 0:
                option_list.highlighted = highlighted - 1
        elif event.key == 'escape':
            event.stop()
            event.prevent_default()
            self._hide_options()

    # ------------------------------------------------------------------
    # private helpers
    # ------------------------------------------------------------------

    def _show_options(self) -> None:
        self.query_one(OptionList).styles.display = 'block'
        self._options_visible = True

    def _hide_options(self) -> None:
        self.query_one(OptionList).styles.display = 'none'
        self._options_visible = False

    def _write_input(self, text: str) -> None:
        """Set Input value without triggering the debounce handler."""
        self._programmatic_update = True
        self.query_one(Input).value = text
        self._programmatic_update = False

    def _select_option(self, index: int) -> None:
        """Finalise selection of the option at *index*."""
        if index < len(self._options):
            name, account_id = self._options[index]
            self._selection = account_id
            self._write_input(name)
            self._hide_options()


class UserSelectionInput(AssigneeSearchInput):
    """The assignee search widget used in the main filter bar."""

    HELP = 'See Search by Assignee section in the help'
    users: Reactive[dict | None] = reactive(None, always_update=True)
    """A dictionary with 2 keys: users (list of JiraUser) and selection (str | None)."""

    def __init__(self):
        super().__init__(id='jira-users-selector', classes='jira-selector')
        self.border_title = 'Assignee'
        self.border_subtitle = '(a)'

    @property
    def help_anchor(self) -> str:
        return '#search-by-assignee'

    def watch_users(self, users: dict | None = None) -> None:
        """Populate internal options from the fetched user list; pre-select if requested."""
        if users and (items := users.get('users', []) or []):
            self._options = [(item.display_name, item.account_id) for item in items]
            if selection := users.get('selection'):
                self.set_value(selection)


class WorkItemInputWidget(Input):
    HELP = 'See Search by Work Item Key section in the help'

    def __init__(self, value: str | None = None):
        super().__init__(
            id='input_issue_key',
            classes='work-item-key',
            type='text',
            placeholder='e.g. ABC-1234',
            tooltip='Search work items by key',
            value=value,
        )
        self.border_title = 'Work Item Key'
        self.border_subtitle = '(k)'

    @property
    def help_anchor(self) -> str:
        return '#search-by-work-item-key'

    @on(Input.Changed)
    def clean_value(self, event: Input.Changed) -> None:
        if event.value is not None:
            self.value = event.value.strip()


class IssueSearchCreatedFromWidget(DateInput):
    HELP = 'See Search by Created From Date section in the help'
    LABEL = 'Created From'
    TOOLTIP = 'Search issues created after this date (inclusive)'
    ID = 'input_date_from'
    BORDER_SUBTITLE = '(f)'

    @property
    def help_anchor(self) -> str:
        return '#search-by-created-from-date'


class IssueSearchCreatedUntilWidget(DateInput):
    HELP = 'See Search by Created Until Date section in the help'
    LABEL = 'Created Until'
    TOOLTIP = 'Search issues created until this date (inclusive)'
    ID = 'input_date_until'
    BORDER_SUBTITLE = '(u)'

    @property
    def help_anchor(self) -> str:
        return '#search-by-created-until-date'


class OrderByWidget(Select):
    def __init__(self, options: list, initial_value: str | None = None):
        super().__init__(
            options=options,
            prompt='Sort By',
            id='issue-search-order-by-selector',
            type_to_search=False,
            compact=True,
            classes='jira-selector',
            value=initial_value,
        )
        self.border_title = 'Sort'
        self.border_subtitle = '(o)'


class ActiveSprintCheckbox(Checkbox):
    HELP = 'See Search by Active Sprint section in the help'

    def __init__(self, value: bool = False):
        super().__init__(
            id='active-sprint-checkbox',
            label='Active Sprint',
            value=value,
            classes='active-sprint-checkbox',
        )
        self.border_subtitle = '(v)'

    @property
    def help_anchor(self) -> str:
        return '#search-by-active-sprint'


class JQLSearchWidget(Input):
    HELP = 'See Searching Using JQL Expressions section in the help'

    BINDINGS = [
        (
            'ctrl+e',
            'open_jql_editor',
            'JQL Editor',
        )
    ]

    expression: Reactive[str | None] = reactive(None)

    def __init__(self):
        super().__init__(
            id='input_search_term',
            placeholder='Type in a JQL expression to search issues...',
            tooltip='Search issues using JQL (Jira Query Language)',
            type='text',
        )
        self.border_title = 'JQL Query'
        self.border_subtitle = '(j)'

    @property
    def help_anchor(self) -> str:
        return '#searching-using-jql-expressions'

    def watch_expression(self, value: str | None = None) -> None:
        if value and value not in self.value:  # type:ignore[has-type]
            if self.value:  # type:ignore[has-type]
                self.value = f'{self.value} AND {self._clean_value(value)}'  # type:ignore[has-type]
            else:
                self.value = self._clean_value(value)

    async def action_open_jql_editor(self) -> None:
        await self.app.push_screen(JQLEditorScreen(self.value), callback=self.update_input_value)

    def update_input_value(self, value: str) -> None:
        self.value = self._clean_value(value)

    @staticmethod
    def _clean_value(value: str) -> str | None:
        if value:
            return (
                value.replace('\n', ' ')
                .replace('\t', ' ')
                .replace('True', 'true')
                .replace('False', 'false')
            )
        return value
