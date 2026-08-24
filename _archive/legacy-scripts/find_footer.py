#!/usr/bin/env python
import os
import re

# Search for footer text variations
search_texts = ['A Project by Ghanshyam Acharya', 'Ghanshyam Acharya', 'Made with love']
html_files = []

for root, dirs, files in os.walk('.'):
    if '.git' in root:
        continue
    for f in files:
        if f.endswith('.html'):
            html_files.append(os.path.join(root, f))

print('Found {} HTML files'.format(len(html_files)))
print()

# Check each file for footer text
for html_file in html_files:
    try:
        with open(html_file, 'r', errors='replace') as f:
            content = f.read()
        
        found_texts = []
        for text in search_texts:
            if text in content:
                found_texts.append(text)
        
        if found_texts:
            # Get context around the text
            for text in found_texts:
                idx = content.find(text)
                if idx >= 0:
                    context = content[max(0, idx-60):idx+100]
                    print('{}: Found "{}"'.format(html_file, text))
                    print('  Context: ...{}...'.format(context[:100]))
                    print()
    except Exception as e:
        print('Error with {}: {}'.format(html_file, e))
PYEOF