#!/usr/bin/env python
import os
import re

# Target text to replace
old_text = "A Project by Ghanshyam Acharya"
new_text = "Made with love \u2764\uFE0F from Nepal"

# Find all HTML files
html_files = []
for root, dirs, files in os.walk('.'):
    if '.git' in root:
        continue
    for f in files:
        if f.endswith('.html'):
            html_files.append(os.path.join(root, f))

# Process each file
for html_file in html_files:
    try:
        with open(html_file, 'r', errors='replace') as f:
            content = f.read()
        
        if old_text in content:
            # Replace the text
            new_content = content.replace(old_text, new_text)
            
            # Write back
            with open(html_file, 'w', errors='replace') as f:
                f.write(new_content)
            
            print('Replaced in: {}'.format(html_file))
        else:
            print('Not found in: {}'.format(html_file))
    except Exception as e:
        print('Error with {}: {}'.format(html_file, e))
PYEOF