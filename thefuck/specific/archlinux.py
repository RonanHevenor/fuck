""" This file provide some utility functions for Arch Linux specific rules."""
import re
import subprocess
from difflib import get_close_matches as difflib_get_close_matches
from .. import utils


# Known package renames/replacements that pacman doesn't track
_KNOWN_RENAMES = {
    'neofetch': 'fastfetch',
    'wireshark-gtk': 'wireshark-qt',
    'ttf-liberation': 'ttf-liberation-mono-nerd',
    'pkg-config': 'pkgconf',
    'libcanberra-pulse': 'libcanberra',
    'ffmpeg2theora': 'ffmpeg',
    'mysql': 'mariadb',
    'libreoffice-still': 'libreoffice-fresh',
}


def _parse_command(command):
    """Extract the binary name from a command string, stripping sudo."""
    command = command.strip()
    if command.startswith('sudo '):
        command = command[5:]
    return command.split(" ")[0]


def _get_history_command(parts):
    """Extract the command name from a history segment."""
    if not parts:
        return ''
    if parts[0] == 'sudo' and len(parts) > 1:
        return parts[1]
    return parts[0]


def _parse_history_install(line):
    """Extract the installed package and the command it was followed by."""
    try:
        from thefuck.shells import shell
        segments = [
            shell.split_command(segment)
            for segment in re.split(r'\s*(?:&&|\|\||;)\s*', line)
            if segment.strip()
        ]
    except Exception:
        return None, None

    if not segments:
        return None, None

    install = segments[0]
    if install[:2] == ['sudo', 'pacman']:
        start = 2
    elif install[0] in ('pacman', 'yay', 'pikaur', 'yaourt'):
        start = 1
    else:
        return None, None

    try:
        install_index = install.index('-S', start)
    except ValueError:
        return None, None

    package = None
    for token in install[install_index + 1:]:
        if token.startswith('-'):
            continue
        package = token
        break

    if not package:
        return None, None

    for segment in segments[1:]:
        invoked = _get_history_command(segment)
        if invoked:
            return package, invoked

    return package, None


@utils.memoize
def _get_all_pacman_packages():
    """Cache the full list of package names from official repos."""
    try:
        output = subprocess.check_output(
            ['pacman', '-Ssq'],
            universal_newlines=True, stderr=utils.DEVNULL
        ).strip()
        return output.splitlines() if output else []
    except subprocess.CalledProcessError:
        return []


@utils.memoize
def get_pkgfile(command):
    """ Gets the packages that provide the given command using `pkgfile`.

    If the command is of the form `sudo foo`, searches for the `foo` command
    instead.
    """
    try:
        cmd = _parse_command(command)

        packages = subprocess.check_output(
            ['pkgfile', '-b', '-v', cmd],
            universal_newlines=True, stderr=utils.DEVNULL
        ).splitlines()

        return [package.split()[0] for package in packages]
    except subprocess.CalledProcessError as err:
        if err.returncode == 1 and err.output == "":
            return []
        else:
            raise err


@utils.memoize
def get_pacman_file_search(command):
    """Use `pacman -F` as a fallback when pkgfile is not installed.

    Searches the pacman file database for which package provides a binary.
    Requires `pacman -Fy` to have been run at least once (as root).
    """
    cmd = _parse_command(command)
    if not cmd:
        return []

    try:
        output = subprocess.check_output(
            ['pacman', '-Fq', cmd],
            universal_newlines=True, stderr=utils.DEVNULL
        ).strip()
        if output:
            return list(dict.fromkeys(output.splitlines()))[:5]
    except subprocess.CalledProcessError:
        pass
    return []


@utils.memoize
def get_pacman_packages(command):
    """Search pacman repos for packages matching the command name.

    Tries in order: exact match, prefix match, substring match, fuzzy match.
    """
    cmd = _parse_command(command)
    if not cmd:
        return []

    results = []

    # 1. Exact match
    try:
        exact = subprocess.check_output(
            ['pacman', '-Ssq', '^{}$'.format(re.escape(cmd))],
            universal_newlines=True, stderr=utils.DEVNULL
        ).strip().splitlines()
        if exact:
            return exact
    except subprocess.CalledProcessError:
        pass

    # 2. Known renames
    if cmd in _KNOWN_RENAMES:
        renamed = _KNOWN_RENAMES[cmd]
        try:
            check = subprocess.check_output(
                ['pacman', '-Ssq', '^{}$'.format(re.escape(renamed))],
                universal_newlines=True, stderr=utils.DEVNULL
            ).strip().splitlines()
            if check:
                results.extend(check)
        except subprocess.CalledProcessError:
            pass

    # 3. Prefix match — packages whose name starts with the typed command
    try:
        prefix = subprocess.check_output(
            ['pacman', '-Ssq', '^{}'.format(re.escape(cmd))],
            universal_newlines=True, stderr=utils.DEVNULL
        ).strip().splitlines()
        for p in prefix:
            if p.startswith(cmd) and p not in results:
                results.append(p)
    except subprocess.CalledProcessError:
        pass

    # 4. Substring match — packages whose name contains the typed command
    if len(results) < 5:
        try:
            matches = subprocess.check_output(
                ['pacman', '-Ssq', re.escape(cmd)],
                universal_newlines=True, stderr=utils.DEVNULL
            ).strip().splitlines()
            for m in matches:
                if cmd in m and m not in results:
                    results.append(m)
        except subprocess.CalledProcessError:
            pass

    # 5. Fuzzy/typo matching — use difflib against all package names
    if not results:
        all_packages = _get_all_pacman_packages()
        if all_packages:
            fuzzy = difflib_get_close_matches(cmd, all_packages, n=5, cutoff=0.7)
            results.extend(fuzzy)

    return results[:5]


@utils.memoize
def get_aur_packages(command):
    """Search AUR for packages matching the command name.

    Only used when official repos have no results. Requires yay or pikaur.
    """
    cmd = _parse_command(command)
    if not cmd:
        return []

    aur_helper = None
    if utils.which('yay'):
        aur_helper = 'yay'
    elif utils.which('pikaur'):
        aur_helper = 'pikaur'

    if not aur_helper:
        return []

    # Exact match in AUR
    try:
        exact = subprocess.check_output(
            [aur_helper, '-Ssq', '^{}$'.format(re.escape(cmd))],
            universal_newlines=True, stderr=utils.DEVNULL
        ).strip().splitlines()
        if exact:
            return exact[:3]
    except subprocess.CalledProcessError:
        pass

    # Prefix match in AUR
    try:
        prefix = subprocess.check_output(
            [aur_helper, '-Ssq', '^{}'.format(re.escape(cmd))],
            universal_newlines=True, stderr=utils.DEVNULL
        ).strip().splitlines()
        if prefix:
            return prefix[:3]
    except subprocess.CalledProcessError:
        pass

    return []


@utils.memoize
def get_history_package(command):
    """Check shell history for a previous install of the same command.

    If the user previously ran `yay -S foo && cmd` or `pacman -S foo`,
    suggest reinstalling that package.
    """
    cmd = _parse_command(command)
    if not cmd:
        return []

    try:
        from thefuck.shells import shell
        history = shell.get_history()
    except Exception:
        return []

    packages = []
    for line in reversed(history):
        pkg, invoked = _parse_history_install(line)
        if not pkg:
            continue

        # A chained install explicitly ties the package to the invoked command.
        # For standalone installs, only keep exact package-name matches.
        if (invoked == cmd or (invoked is None and pkg == cmd)) and pkg not in packages:
            packages.append(pkg)
        if len(packages) >= 3:
            break

    return packages


def archlinux_env():
    if utils.which('yay'):
        pacman = 'yay'
    elif utils.which('pikaur'):
        pacman = 'pikaur'
    elif utils.which('yaourt'):
        pacman = 'yaourt'
    elif utils.which('pacman'):
        pacman = 'sudo pacman'
    else:
        return False, None

    enabled_by_default = utils.which('pkgfile')

    return enabled_by_default, pacman
