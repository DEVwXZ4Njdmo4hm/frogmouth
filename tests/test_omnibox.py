"""Verify that command parsing preserves case-sensitive arguments."""

from pathlib import Path

import pytest
from textual.app import App, ComposeResult

from frogmouth.widgets import Omnibox


class OmniboxApp(App[None]):
    """Capture address-bar messages without making network requests."""

    def __init__(self) -> None:
        super().__init__()
        self.forge_commands: list[Omnibox.ForgeCommand] = []
        self.directory_commands: list[Path] = []

    def compose(self) -> ComposeResult:
        yield Omnibox()

    def on_omnibox_git_hub_command(self, event: Omnibox.GitHubCommand) -> None:
        self.forge_commands.append(event)

    def on_omnibox_local_chdir_command(self, event: Omnibox.LocalChdirCommand) -> None:
        self.directory_commands.append(event.target)


@pytest.mark.parametrize("command", ["GH", "GitHub", "github"])
async def test_forge_command_preserves_argument_case(command: str) -> None:
    app = OmniboxApp()
    async with app.run_test() as pilot:
        omnibox = app.query_one(Omnibox)
        omnibox.value = f"{command} MixedOwner/MixedRepo:FeatureBranch Docs/README.md"
        await pilot.press("enter")

        assert len(app.forge_commands) == 1
        event = app.forge_commands[0]
        assert event.owner == "MixedOwner"
        assert event.repository == "MixedRepo"
        assert event.branch == "FeatureBranch"
        assert event.desired_file == "Docs/README.md"


async def test_chdir_command_preserves_argument_case(tmp_path: Path) -> None:
    directory = tmp_path / "CaseSensitive Directory"
    app = OmniboxApp()
    async with app.run_test() as pilot:
        app.query_one(Omnibox).value = f"CD {directory}"
        await pilot.press("enter")

        assert app.directory_commands == [directory]


async def test_empty_submission_does_not_open_a_directory() -> None:
    app = OmniboxApp()
    async with app.run_test() as pilot:
        app.query_one(Omnibox).value = "   "
        await pilot.press("enter")

        assert not app.directory_commands
        assert not app.forge_commands
