from pathlib import Path
from pypdf import PdfReader

import sys

pdf_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("2026-hum-handbook-9a-final-web.pdf")
reader = PdfReader(str(pdf_path))
for i in range(10, 16):
    page = reader.pages[i-1]
    text = page.extract_text() or ''
    print('PAGE', i)
    print(text[:1200])
    print('---')
