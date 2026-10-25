"""
Builds "Chess Overlay.exe" from chess_overlay.py.  Run it with "Build EXE.bat".

It makes a private Python environment in the "build" folder (so nothing gets
installed into your main Python), installs PyInstaller + numpy + mss there,
and packs everything into one .exe next to this file. Takes 1-3 minutes.
"""

import os
import shutil
import subprocess
import sys
import venv

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build")
NAME = "Chess Overlay"
IS_WINDOWS = sys.platform == "win32"
PACKAGES = ["pyinstaller", "numpy", "mss"]


def say(text):
    print(text, flush=True)


def run(cmd):
    say("  > " + " ".join('"%s"' % c if " " in c else c for c in cmd))
    subprocess.check_call(cmd)


def fail(text):
    say("\nERROR: " + text)
    sys.exit(1)


def venv_python(folder):
    return os.path.join(folder, "Scripts", "python.exe") if IS_WINDOWS else os.path.join(folder, "bin", "python")


def get_python():
    """A Python with PyInstaller, numpy and mss: a private venv if possible,
    otherwise this Python with the packages installed for the current user."""
    folder = os.path.join(BUILD, "venv")
    py = venv_python(folder)
    if not os.path.exists(py):
        say("[1/3] Making a private Python environment for the build…")
        try:
            venv.create(folder, with_pip=True, clear=True)
        except Exception as e:
            say("      (couldn't make one: %s - using your normal Python instead)" % e)
            shutil.rmtree(folder, ignore_errors=True)
            py = sys.executable
    else:
        say("[1/3] Reusing the build environment from last time…")
    say("[2/3] Installing PyInstaller, numpy and mss (first time: about a minute)…")
    extra = ["--user"] if py == sys.executable else []
    run([py, "-m", "pip", "install", "--disable-pip-version-check", "--quiet", "--upgrade"] + extra + PACKAGES)
    return py


def main():
    if not IS_WINDOWS:
        say("Note: this makes a program for the system it runs on. Run it on Windows to get an .exe.")
    if sys.version_info < (3, 9):
        fail("Python 3.9 or newer is needed (you have %d.%d). Get it from https://www.python.org/downloads/"
             % sys.version_info[:2])
    try:
        import tkinter  # noqa: F401  (PyInstaller needs it to bundle the window toolkit)
    except ImportError:
        fail("Your Python has no tkinter. Re-run the Python installer, choose Modify and tick "
             "'tcl/tk and IDLE', then try again.")
    script = os.path.join(HERE, "chess_overlay.py")
    icon = os.path.join(HERE, "icon.ico")
    if not os.path.exists(script):
        fail("chess_overlay.py must be in the same folder as this file.")

    py = get_python()

    say("[3/3] Packing everything into one .exe…")
    sep = ";" if IS_WINDOWS else ":"
    dist, work = os.path.join(BUILD, "dist"), os.path.join(BUILD, "work")
    cmd = [py, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
           "--name", NAME, "--distpath", dist, "--workpath", work, "--specpath", BUILD,
           "--log-level", "WARN"]
    if os.path.exists(icon):  # absolute paths: --specpath would change what relative ones mean
        cmd += ["--icon", icon, "--add-data", icon + sep + "."]
    for mod in ("matplotlib", "scipy", "pandas", "PIL", "IPython", "pytest"):
        cmd += ["--exclude-module", mod]   # keep the .exe small if these are lying around
    run(cmd + [script])

    built = os.path.join(dist, NAME + (".exe" if IS_WINDOWS else ""))
    if not os.path.exists(built):
        fail("PyInstaller finished but no program was made - see the messages above.")
    target = os.path.join(HERE, os.path.basename(built))
    try:
        shutil.copy2(built, target)
    except PermissionError:
        fail('"%s" is open. Close Chess Overlay and build again.' % os.path.basename(target))
    shutil.rmtree(work, ignore_errors=True)
    shutil.rmtree(dist, ignore_errors=True)
    size = os.path.getsize(target) / 1e6
    say("\nDone! Made %s (%.0f MB)." % (target, size))
    say("You can move it anywhere (e.g. your Desktop). Its settings live in %APPDATA%\\Chess Overlay.")
    say('The "build" folder is only needed to build again - you can delete it.')
    if IS_WINDOWS and not os.environ.get("CI"):   # show it in Explorer (not on GitHub's build servers)
        subprocess.Popen(["explorer", "/select,", target])


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        fail("A build step failed (%s). If it says it can't reach the internet, check your "
             "connection or VPN and run Build EXE.bat again." % e)
