#!/usr/bin/env python3
import re, os

for html_file in ['login.html', 'safety.html']:
    path = os.path.join('public', html_file)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Find firebase script tag and add version
        pattern = r'(<script src="\/js\/firebase.js")[^>]*>'
        match = re.search(pattern, content)
        if match:
            # Add version parameter
            new_content = re.sub(pattern, r'\1?v=2.1.0>', content)
        else:
            # Add new firebase script tag with version
            new_content = content.replace('</body>', '<script src="/js/firebase.js?v=2.1.0"></script></body>')
        
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(html_file + ': cache-buster added')
    except FileNotFoundError:
        print(html_file + ': NOT FOUND')
"