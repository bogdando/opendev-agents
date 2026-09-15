#!/usr/bin/env python3
"""Wrap text to 72 characters preserving paragraphs."""
import sys
import textwrap

def wrap_text(text, width=72):
    """Wrap text to specified width, preserving paragraphs."""
    paragraphs = text.split('\n\n')
    wrapped = []
    for para in paragraphs:
        # Preserve code blocks and lists
        if para.startswith(('  ', '- ', '* ', '1.')):
            wrapped.append(para)
        else:
            wrapped.append(textwrap.fill(para, width=width))
    return '\n\n'.join(wrapped)

if __name__ == '__main__':
    text = sys.stdin.read()
    print(wrap_text(text))
