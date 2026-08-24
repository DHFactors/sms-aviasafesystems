#!/usr/bin/env python
import re

with open('public/index.html', 'r', errors='replace') as f:
    content = f.read()

# Find the a tag and replace with button
a_tags = re.finditer(r'<a[^>]+>', content)
for m in a_tags:
    a_tag = m.group()
    # Check if this is the hero button (has cursor-pointer and onclick)
    if 'cursor-pointer' in a_tag and 'onclick="toggleDemoModal()"' in a_tag:
        # Get the start position
        start_pos = m.start()
        
        # Create the new button tag
        new_button = '<button type="button" class="w-full sm:w-auto px-8 py-4 text-base font-bold text-white bg-gradient-to-r from-brand-600 to-teal-600 hover:from-brand-700 hover:to-teal-600 rounded-xl shadow-lg shadow-brand-500/30 transition-all hover:scale-[1.02] flex items-center justify-center gap-3 cursor-pointer onclick="toggleDemoModal()"><i class="fa-solid fa-rocket text-lg"></i> Request Demo</button>'
        
        # Replace in content
        content = content[:m.start()] + new_button + content[m.start() + len(m.group()):]
        
        with open('public/index.html', 'w', errors='replace') as f:
            f.write(content)
        print('Successfully converted a tag to button tag')
        break
PYEOF
PYEOF