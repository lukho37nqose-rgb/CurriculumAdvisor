from pathlib import Path
from pypdf import PdfReader
import re

pdf_path = Path(r"C:\Users\Lukho Nqose\Downloads\2026-hum-handbook-9a-final-web.pdf")
reader = PdfReader(str(pdf_path))
keywords = [
    'Economics', 'Philosophy', 'Political Studies', 'Politics', 'Sociology',
    'Major in Economics', 'Major in Philosophy', 'Major in Sociology',
    'Bachelor of Social Science in Philosophy', 'Bachelor of Social Science',
    'Politics & Governance', 'Politics and Governance'
]
for i, page in enumerate(reader.pages, start=1):
    text = page.extract_text() or ''
    if any(k.lower() in text.lower() for k in keywords):
        print('PAGE', i)
        for line in text.splitlines():
            if any(k.lower() in line.lower() for k in keywords):
                print(line)
        print('---')
