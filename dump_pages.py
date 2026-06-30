import sys
from pathlib import Path
from pypdf import PdfReader

pdf_path = Path(sys.argv[1] if len(sys.argv) > 1 else "2026-hum-handbook-9a-final-web.pdf")
reader = PdfReader(str(pdf_path))
for page_num in [32, 44, 45, 46, 47, 48, 49]:
    print('\n' + '='*20 + f' PAGE {page_num} ' + '='*20)
    text = reader.pages[page_num - 1].extract_text() or ''
    print(text[:10000])
