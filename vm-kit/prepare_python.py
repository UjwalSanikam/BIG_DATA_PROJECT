"""Create the same project Python on all VMs, preserving incompatible environments."""
import pathlib, subprocess, uuid
from download_runtime import install
VERSION = '3.11.18'

def prepare(root):
    runtime = install('python311', root / 'runtime')
    python = runtime / 'bin/python3.11'
    version = subprocess.check_output([str(python), '-c', 'import platform; print(platform.python_version())'], text=True).strip()
    if version != VERSION:
        raise RuntimeError(f'Expected project Python {VERSION}, got {version}')
    venv = root / 'venv'
    if venv.exists() or venv.is_symlink():
        try:
            existing = subprocess.check_output([str(venv / 'bin/python'), '-c', 'import platform; print(platform.python_version())'], text=True, stderr=subprocess.DEVNULL).strip()
        except (OSError, subprocess.CalledProcessError):
            existing = 'broken'
        if existing != VERSION:
            backup = root / ('venv.previous-' + uuid.uuid4().hex[:8])
            venv.rename(backup)
            print(f'Preserved Python {existing} environment at {backup}', flush=True)
    if not venv.exists():
        subprocess.run([str(python), '-m', 'venv', str(venv)], check=True)
    print('PROJECT_PYTHON_OK', VERSION, flush=True)

if __name__ == '__main__':
    prepare(pathlib.Path(__file__).resolve().parent)
