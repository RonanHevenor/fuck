from thefuck.specific.archlinux import (
    get_pkgfile, get_pacman_file_search, get_pacman_packages,
    get_aur_packages, get_history_package, archlinux_env,
)
from thefuck.shells import shell


def _find_packages(script):
    """Try all available sources to find packages for a missing command.

    Priority order:
    1. Shell history (user previously installed something for this command)
    2. pkgfile (binary-to-package mapping)
    3. pacman -F (fallback file search without pkgfile)
    4. Pacman repo search (exact, prefix, substring, fuzzy)
    5. AUR search
    """
    return (get_history_package(script)
            or get_pkgfile(script)
            or get_pacman_file_search(script)
            or get_pacman_packages(script)
            or get_aur_packages(script))


def match(command):
    if 'command not found' not in command.output:
        return False
    return bool(_find_packages(command.script))


def get_new_command(command):
    packages = _find_packages(command.script)
    if not packages:
        return []

    formatme = shell.and_('{} -S {}', '{}')
    return [formatme.format(pacman, package, command.script)
            for package in packages]


priority = 3500
enabled_by_default, pacman = archlinux_env()
