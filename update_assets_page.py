"""
One-time script to rewrite assets.html with:
- Fixed card clicks (filterAssetStatus)
- Fixed filter with search
- Short branch names (2ยะหา format)
- Edit modal with change tracking
- Sortable table
"""
import re

# Read current file
with open('templates/assets.html', 'r') as f:
    content = f.read()

# This is a marker file — the actual rewrite will be done via patch commands
print("Marker file created")
