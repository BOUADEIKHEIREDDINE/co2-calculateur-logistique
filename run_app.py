"""Lance l'interface : python run_app.py, puis ouvrir http://localhost:8501"""
import subprocess
import sys
from pathlib import Path

racine = Path(__file__).resolve().parent
subprocess.run([sys.executable, "-m", "streamlit", "run", str(racine / "app" / "app.py")], cwd=racine, check=False)
