#!/usr/bin/env python
with open('public/index.html', 'r', errors='replace') as f:
    content = f.read()

# Find the a tag and replace with button
# Looking for the pattern with cursor-pointer and onclick
search_pattern = '<a class="w-full sm:w-auto px-8 py-4 text-base font-bold text-white bg-gradient-to-r from-brand-600 to-teal-600 hover:from-brand-700 hover:to-teal-600 rounded-xl shadow-lg shadow-brand-500/30 transition-all hover:scale-[1.02] flex items-center justify-center gap-3 cursor-pointer onclick="toggleDemoModal()">'

print('Searching for pattern...')
print('Pattern length:', len(search_pattern))

idx = content.find(search_pattern)
print('Found at index:', idx)

if idx >= 0:
    # Found it - now replace
    new_tag = '''<button type="button" class="w-full sm:w-auto px-8 py-4 text-base font-bold text-white bg-gradient-to-r from-brand-600 to-teal-600 hover:from-brand-700 hover:to-teal-600 rounded-xl shadow-lg shadow-brand-500/30 transition-all hover:scale-[1.02] flex items-center justify-center gap-3 cursor-pointer onclick="toggleDemoModal()">
        <i class="fa-solid fa-rocket text-lg"></i> Request Demo
    </button>'''
    
    content = content.replace(old_tag, new_tag)
    with open('public/index.html', 'w', errors='replace') as f:
        f.write(content)
    print('Successfully converted a tag to button tag')
else:
    print('Pattern not found in content')
    # Try alternative: just find the a tag and manually change it
    a_start = content.find('<a class="')
    if a_start >= 0:
        a_end = content.find('</a>', a_start)
        if a_end >= 0:
            print('Found a tag at index', a_start)
            print('Current a tag content:')
            print(content[a_start:a_start+200])
"