#!/usr/bin/env python3
import re, os

for html_file in ['safety.html', 'login.html']:
    path = os.path.join('public', html_file)
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find and fix stylesheet links
    # Look for <link rel="stylesheet" href="..."> patterns
    pattern = r'<link\s+rel="stylesheet"\s+href="([^"]*)"'
    matches = re.findall(pattern, content)
    
    print(f'{html_file}: found {len(matches)} stylesheet links')
    for m in matches:
        print(f'  href="{m}"')
    
    # If the href doesn't start with /css/, rewrite it
    new_content = content
    for m in matches:
        if not m.startswith('/css/') and not m.startswith('http'):
            # Replace with /css/main.css as a safe default
            new_content = new_content.replace(
                f'<link rel="stylesheet" href="{m}">',
                '<link rel="stylesheet" href="/css/main.css">'
            )
    
    if new_content != content:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f'  Updated {html_file}')
    else:
        print(f'  {html_file}: no changes needed')
"