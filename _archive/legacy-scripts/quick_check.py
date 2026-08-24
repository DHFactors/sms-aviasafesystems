with open('public/index.html', 'r', errors='replace') as f:
    c = f.read()
    
results = {}
results['func'] = 'function toggleDemoModal' in c
results['cursor'] = 'cursor-pointer' in c
results['modal_id'] = 'id="demo-modal"' in c
results['onclick_toggle'] = 'onclick="toggleDemoModal()"' in c

for k, v in results.items():
    status = 'PASS' if v else 'FAIL'
    print(f'[{status}] {k}')