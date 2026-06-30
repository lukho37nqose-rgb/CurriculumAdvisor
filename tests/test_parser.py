import unittest
from unittest.mock import patch, MagicMock

from engine.parser import parse_transcript_pdf

class TestParserPdf(unittest.TestCase):
    def test_parse_transcript_pdf_missing_pypdf(self):
        """Test that missing pypdf raises an ImportError."""
        with patch.dict('sys.modules', {'pypdf': None}):
            with self.assertRaises(ImportError) as context:
                parse_transcript_pdf("dummy_path.pdf")
            self.assertIn("pypdf is required", str(context.exception))

    @patch("engine.parser.parse_transcript_text")
    def test_parse_transcript_pdf_success(self, mock_parse_text):
        """Test successful extraction and delegation to parse_transcript_text."""
        mock_pdf_reader = MagicMock()

        # Setup pages with some text
        mock_page_1 = MagicMock()
        mock_page_1.extract_text.return_value = "Page 1 Text"
        mock_page_2 = MagicMock()
        mock_page_2.extract_text.return_value = "Page 2 Text"

        mock_pdf_reader.return_value.pages = [mock_page_1, mock_page_2]

        mock_parse_text.return_value = "Mocked Record"

        with patch.dict('sys.modules', {'pypdf': MagicMock(PdfReader=mock_pdf_reader)}):
            result = parse_transcript_pdf("dummy_path.pdf")

            # Check PdfReader initialization
            mock_pdf_reader.assert_called_once_with("dummy_path.pdf")

            # Check parse_transcript_text call with concatenated text
            mock_parse_text.assert_called_once_with("Page 1 Text\nPage 2 Text\n")

            # Check result
            self.assertEqual(result, "Mocked Record")

    @patch("engine.parser.parse_transcript_text")
    def test_parse_transcript_pdf_none_text(self, mock_parse_text):
        """Test handling of pages where extract_text returns None."""
        mock_pdf_reader = MagicMock()

        # Setup page that returns None for text
        mock_page_1 = MagicMock()
        mock_page_1.extract_text.return_value = None

        mock_pdf_reader.return_value.pages = [mock_page_1]

        with patch.dict('sys.modules', {'pypdf': MagicMock(PdfReader=mock_pdf_reader)}):
            parse_transcript_pdf("dummy_path.pdf")

            # Check parse_transcript_text call with empty text and newline
            mock_parse_text.assert_called_once_with("\n")

if __name__ == '__main__':
    unittest.main()
