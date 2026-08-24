import os

# Read the file
with open('public/index.html', 'r', errors='replace') as f:
    content = f.read()

# Find the </body> and add script before it
idx = content.rfind('</body>')
if idx >= 0:
    # Insert script before </body>
    script = '''
<script>
    // ============================================================================
    // DEMO MODAL TOGGLE
    // ============================================================================
    function toggleModal() {
        var modal = document.getElementById('demo-modal');
        if (modal.classList.contains('hidden')) {
            modal.classList.remove('hidden');
        } else {
            modal.classList.add('hidden');
        }
    }

    // Close modal when clicking outside the card (on the backdrop)
    document.addEventListener('click', function(e) {
        var modal = document.getElementById('demo-modal');
        var modalCard = modal.querySelector('.relative');
        
        if (modal.classList.contains('hidden') === false && !modalCard.contains(e.target) && e.target !== modal) {
            modal.classList.add('hidden');
        }
    });
</script>
'''
    new_content = content[:idx] + script + content[idx:]
    with open('public/index.html', 'w', errors='replace') as f:
        f.write(new_content)
    print('Script added successfully')
    # Verify
    print('Script present:', 'toggleModal' in new_content)
else:
    print('</body> not found')