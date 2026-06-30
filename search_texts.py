import sys
from pathlib import Path
from pypdf import PdfReader

pdf_path = Path(sys.argv[1] if len(sys.argv) > 1 else "2026-hum-handbook-9a-final-web.pdf")
reader = PdfReader(str(pdf_path))
keywords = ['School of Economics', 'Political Studies', 'Sociology', 'Philosophy', 'Economics', 'Politics & Governance']
for i, page in enumerate(reader.pages, start=1):
    text = page.extract_text() or ''
    for kw in keywords:
        if kw in text:
            print(f'PAGE {i} contains {kw}')
            break
