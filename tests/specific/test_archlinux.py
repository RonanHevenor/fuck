import pytest

from thefuck.specific.archlinux import get_history_package


@pytest.mark.usefixtures('no_memoize')
@pytest.mark.parametrize('history, command, expected', [
    (['yay -S libimobiledevice'], 'bim', []),
    (['yay -S vim'], 'vim', ['vim']),
    (['yay -S --needed vim && vim'], 'vim', ['vim']),
    (['yay -S libimobiledevice && bim'], 'bim', ['libimobiledevice'])])
def test_get_history_package(monkeypatch, history, command, expected):
    monkeypatch.setattr('thefuck.shells.shell.get_history', lambda: history)
    assert get_history_package(command) == expected
