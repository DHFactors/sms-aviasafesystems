#!/usr/bin/env python
with open('public/index.html', 'r', errors='replace') as f:
    content = f.read()

# Replace the a tag with button tag
old = '''<a class="w-full sm:w-auto px-8 py-4 text-base font-bold text-white bg-gradient-to-r from-brand-600 to-teal-600 hover:from-brand-700 hover:to-teal-600 rounded-xl shadow-lg shadow-brand-500/30 transition-all hover:scale-[1.02] flex items-center justify-center gap-3 cursor-pointer onclick="toggleDemoModal()">
        <i class="fa-solid fa-rocket text-lg"></i> Request Demo
    </a>'''

new = '''<button type="button" class="w-full sm:w-auto px-8 py-4 text-base font-bold text-white bg-gradient-to-r from-brand-600 to-teal-600 hover:from-brand-700 hover:to-teal-600 rounded-xl shadow-lg shadow-brand-500/30 transition-all hover:scale-[1.02] flex items-center justify-center gap-3 cursor-pointer onclick="toggleDemoModal()">
        <i class="fa-solid fa-rocket text-lg"></i> Request Demo
    </button>'''

if old in content:
    content = content.replace(old, new)
    with open('public/index.html', 'w', errors='replace') as f:
        f.write(content)
    print('Successfully converted a tag to button tag')
else:
    print('Old string not found')
    # Try to find what's actually there
    idx = content.find('cursor-pointer onclick')
    if idx >= 0:
        print('Found at index', idx)
        print(content[idx-50:idx+150])