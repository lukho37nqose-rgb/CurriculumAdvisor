import sys
from pathlib import Path
from pypdf import PdfReader
import re

import sys

pdf_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("2026-hum-handbook-9a-final-web.pdf")
reader = PdfReader(str(pdf_path))
patterns = [
    r'Requirements for a Major in Economics',
    r'Requirements for a Major in Philosophy',
    r'Requirements for a Major in Politics',
    r'Requirements for a Major in Political Studies',
    r'Requirements for a Major in Sociology',
    r'Major in Economics',
    r'Major in Philosophy',
    r'Major in Politics',
    r'Major in Sociology',
    r'PHI1010S',
    r'POL1005S',
    r'SOC1001F',
    r'ECO1010F',
]
for i, page in enumerate(reader.pages, start=1):
    text = page.extract_text() or ''
    if any(re.search(p, text, re.I) for p in patterns):
        print('PAGE', i)
        lines = text.splitlines()
        for line in lines:
            if any(re.search(p, line, re.I) for p in patterns):
                print(line)
        print('---')
