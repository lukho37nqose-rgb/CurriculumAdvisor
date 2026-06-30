from pathlib import Path
from pypdf import PdfReader
import re

pdf_path = Path(r"C:\Users\Lukho Nqose\Downloads\2026-hum-handbook-9a-final-web.pdf")
reader = PdfReader(str(pdf_path))
for i, page in enumerate(reader.pages, start=1):
    text = page.extract_text() or ''
    if re.search(r'Requirements for a Major in', text, re.I):
        print('PAGE', i)
        lines = text.splitlines()
        for line in lines:
            if re.search(r'Requirements for a Major in', line, re.I):
                print(line)
        print('---')
