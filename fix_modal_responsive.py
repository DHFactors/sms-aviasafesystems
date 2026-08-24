with open('public/index.html', 'r', errors='replace') as f:
    content = f.read()

# The inner card class we need to replace
old_class = 'class="relative w-96 md:w-max max-w-full bg-white rounded-2xl shadow-2xl transform-ease-scale"'
new_class = 'class="w-[95%] md:w-full max-w-lg max-h-[90vh] overflow-y-auto bg-white rounded-2xl shadow-2xl relative p-6 md:p-8"'

if old_class in content:
    content = content.replace(old_class, new_class)
    print('Replaced inner card class with responsive classes')
    print('Old:', old_class)
    print('New:', new_class)
else:
    print('Old class not found exactly')
    # Try regex
    import re
    match = re.search(r'class="relative w[^"]*md:w-max max-w-full bg-white rounded-2xl shadow-2xl transform-ease-scale"', content)
    if match:
        print('Found with regex:', match.group())
        content = content.replace(match.group(), new_class)
        print('Replaced with regex')
    else:
        print('Could not find the card class')

# Write back
with open('public/index.html', 'w', errors='replace') as f:
    f.write(content)
print('File updated')