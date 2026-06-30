from pathlib import Path
from pypdf import PdfReader

import sys

pdf_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("2026-hum-handbook-9a-final-web.pdf")
reader = PdfReader(str(pdf_path))
keywords = ['ECO1010F', 'PHI1010S', 'POL1005S', 'SOC1001F', 'SOC3027F', 'ECO2003F', 'PHI2042F', 'POL2038F']
for i, page in enumerate(reader.pages, start=1):
    text = page.extract_text() or ''
    if any(k in text for k in keywords):
        print('PAGE', i)
        for k in keywords:
            if k in text:
                print('  contains', k)
        print('-----')
