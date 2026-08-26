#!/usr/bin/env python
with open('public/index.html', 'r', errors='replace') as f:
    content = f.read()

# Find the hero button and add cursor-pointer
# The hero button's class contains 'gap-3 onclick="toggleDemoModal()"'
# We want to change 'gap-3' to 'cursor-pointer gap-3'

# Find the pattern
old = 'gap-3 onclick'
new = 'cursor-pointer gap-3 onclick'

idx = content.find(old)
if idx >= 0:
    new_content = content.replace(old, new, 1)  # Only replace first occurrence
    with open('public/index.html', 'w', errors='replace') as f:
        f.write(new_content)
    print('Successfully added cursor-pointer to hero button')
else:
    print('Pattern not found')
"