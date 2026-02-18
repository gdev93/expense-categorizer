import os
import re

def find_inline_styles(directory):
    files_with_styles = {}
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.html'):
                path = os.path.join(root, file)
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    styles = re.findall(r'style="([^"]*)"', content)
                    style_blocks = re.findall(r'<style>(.*?)</style>', content, re.DOTALL)
                    if styles or style_blocks:
                        files_with_styles[path] = {
                            'inline_attrs': styles,
                            'style_blocks': style_blocks
                        }
    return files_with_styles

if __name__ == "__main__":
    templates_dir = 'templates'
    results = find_inline_styles(templates_dir)
    for path, data in results.items():
        print(f"File: {path}")
        if data['inline_attrs']:
            print(f"  Inline attributes: {data['inline_attrs']}")
        if data['style_blocks']:
            print(f"  Style blocks found")
