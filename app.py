# Inspect the file structure to confirm row indices and format
file_path = '6430.1.17.csv'

# Read the first 20 lines to understand the layout
with open(file_path, 'r', encoding='latin1') as f:
    lines = [f.readline().strip() for _ in range(20)]

for i, line in enumerate(lines):
    print(f"Row {i}: {line}")

# Try to load it with pandas based on visual inspection
import pandas as pd

# It seems the file uses ';' as separator
# "Credenciado" seems to be in the metadata section
# The actual header "Data;Nome..." is further down
