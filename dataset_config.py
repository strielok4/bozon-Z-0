"""Select the input dataset for classification and its matching evaluation key."""
from pathlib import Path

# Change this flag to "delphes" or  "delphi" use the other dataset.
DATASETS = ["delphes", "delphi"]
DATASET = DATASETS[1]

if DATASET not in ("delphi", "delphes"):
    raise ValueError('DATASET must be "delphi" or "delphes"')

ROOT_DIR = Path(__file__).resolve().parent
ASSETS_DIR = ROOT_DIR / "assets" / DATASET
DEBUG_DIR = ROOT_DIR / "debug" / DATASET
TRUTH_PATH = ROOT_DIR / "evaluation" / DATASET / "truth.csv"
