import re

with open('public/index.html', 'r', errors='replace') as f:
    content = f.read()

# The inner card - let's find it by looking for the transform-ease-scale class
# and the bg-white rounded-2xl shadow-2xl
old_pattern = 'transform-ease-scale"'
if old_pattern in content:
    # Find the class attribute that contains this
    idx = content.find(old_pattern)
    # Go back to find the start of the class attribute
    start = idx - 100
    while start > 0 and content[start:start+1] not in ['"', "’"]:
        start -= 1
    # Now find the end
    end = idx + len(old_pattern) + 50
    end = min(end, len(content))
    segment = content[start:end]
    print('Segment containing the card class:')
    print(segment[:200])
    
    # Try to find and replace the full class attribute
    # Look for: class="..." where ... contains rounded-2xl shadow-2xl
    regex = r'class="[^"]*rounded-2xl shadow-2xl[^"]*"'
    match = re.search(regex, content)
    if match:
        print('\\nFound card class via regex:', match.group())
        # Replace with new classes
        new_class = 'class="w-[95%] md:w-full max-w-lg max-h-[90vh] overflow-y-auto bg-white rounded-2xl shadow-2xl relative p-6 md:p-8"'
        content = content.replace(match.group(), new_class)
        print('Replaced card class')
    else:
        print('Could not find card class via regex')
else:
    print('old_pattern not found')

# Write back
with open('public/index.html', 'w', errors='replace') as f:
    f.write(content)
print('\\nFile updated')