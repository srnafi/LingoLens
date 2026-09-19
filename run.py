import os
import sys
import subprocess
from pathlib import Path

def main():
    root_dir = Path(__file__).parent
    venv_python = root_dir / ".venv" / "Scripts" / "python.exe"
    
    if not venv_python.exists():
        venv_python = sys.executable

    app_script = root_dir / "app.py"
    
    print(f"Launching LingoLens Control Center using: {venv_python}")
    cmd = [str(venv_python), str(app_script)]
    
    try:
        subprocess.run(cmd, check=True)
    except Exception as e:
        print(f"Error launching LingoLens: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
