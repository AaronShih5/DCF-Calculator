# comps_financials.py — annual statements for the comp set (edit COMPS in config.py)
from config import COMPS
from data_sources import pull_all

if __name__ == "__main__":
    pull_all(COMPS)
