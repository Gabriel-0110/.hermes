# Desk Scripts

This folder contains small source-controlled support scripts used by the trading desk.

Current script:
- [`bitmart_paper_guard.py`](./bitmart_paper_guard.py): validates that paper-mode BitMart requests do not target live endpoints

Rules:
- scripts here should be safe to publish
- they should not embed credentials or operator-local state
- any generated outputs should go to ignored locations, not back into this folder
