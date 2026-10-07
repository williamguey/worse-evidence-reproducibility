"""Offline scientific reproduction; spending information is withheld."""
import importlib.util,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def main():
    for cohort in ('original','followup','baidu'):
        subprocess.run([sys.executable,'-B',str(ROOT/cohort/'src/offline_reproduce.py')],check=True,cwd=ROOT)
if __name__=='__main__':main()
