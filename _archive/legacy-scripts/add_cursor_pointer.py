with open('public/index.html', 'r', errors='replace') as f:
    content = f.read()

# The hero button class string - find and modify
# Looking for the pattern: ...gap-3 onclick
# We want to add cursor-pointer before gap-3

# Find the position of 'gap-3 onclick'
idx = content.find('gap-3 onclick')
if idx >= 0:
    # Insert 'cursor-pointer ' before 'gap-3'
    new_content = content[:idx] + 'cursor-pointer ' + content[idx:]
    with open('public/index.html', 'w', errors='replace') as f:
        f.write(new_content)
    print('Added cursor-pointer to hero button')
    print(f'Position found at index: {idx}')
else:
    print('Could not find gap-3 onclick position')
    # Try alternative: find the class attribute end
    idx2 = content.find('onclick="toggleDemoModal()"')
    if idx2 >= 0:
        # Find gap-3 before that
        idx2a = content.rfind('gap-3', 0, idx2)
        if idx2a >= 0:
            new_content2 = content[:idx2a] + 'cursor-pointer ' + content[idx2a:]
            with open('public/index.html', 'w', errors='replace') as f:
                f.write(new_content2)
            print('Added cursor-pointer using alternative method')
        else:
            print('Could not find gap-3 before onclick')
    else:
        print('Could not find onclick position either')
else:
    print('gap-3 onclick not found')
"