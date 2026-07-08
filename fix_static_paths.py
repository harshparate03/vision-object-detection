"""Fix broken static file paths across all templates."""
import os
import re

templates_dir = os.path.join('vision', 'templates')

for root, dirs, files in os.walk(templates_dir):
    for fname in files:
        if not fname.endswith('.html'):
            continue
        fpath = os.path.join(root, fname)
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        original = content

        # 1. project/static/media/X  ->  /static/media/X
        content = content.replace('project/static/media/', '/static/media/')

        # 2. _next/static/media/X  ->  /static/media/X
        content = content.replace('_next/static/media/', '/static/media/')

        # 3. {% static 'images/static/media/X' %}  ->  {% static 'media/X' %}
        content = content.replace("{% static 'images/static/media/", "{% static 'media/")

        # 4. src="_next/brand-XXXX.png?url=..."  ->  src="/static/images/brand-XXXX.png"
        content = re.sub(
            r'src="_next/([a-zA-Z0-9_\-]+\.[a-z]+)\?url=[^"]*"',
            r'src="/static/images/\1"',
            content
        )

        # 5. Remove broken srcSet="project/image?url=..." attributes entirely
        content = re.sub(r'\s*srcSet="project/image\?url=[^"]*"', '', content)

        if content != original:
            with open(fpath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f'Fixed: {fpath}')
        else:
            print(f'No changes: {fpath}')

print('Done.')
