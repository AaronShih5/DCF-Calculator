# pull_financials.py — step 1: annual statements for the competition targets (edit TARGETS in config.py)
from config import TARGETS
from data_sources import pull_all

if __name__ == "__main__":
    pull_all(TARGETS)
