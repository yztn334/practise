import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from literature_manager.catalog import write_catalog


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class LiteratureManagerTests(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        self.root = Path(workspace.name)
        self.output = self.root / "output" / "literature.json"
        self.log = self.root / "logs" / "literature-manager.log"

    def make_pdf(self, name, *, with_text=False, password=None):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        writer = PdfWriter()
        page = writer.add_blank_page(width=400, height=400)
        if with_text:
            font = DictionaryObject({
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            })
            page[NameObject("/Resources")] = DictionaryObject({
                NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
            })
            stream = DecodedStreamObject()
            stream.set_data(b"BT /F1 12 Tf 10 350 Td (DOI: 10.1234/example.) Tj ET")
            page[NameObject("/Contents")] = stream
            writer.add_metadata({"/Title": "测试论文", "/Author": "李明", "/Keywords": "PDF；Python"})
            writer.add_blank_page(width=400, height=400)
        if password is not None:
            writer.encrypt(password, algorithm="RC4-128")
        writer.write(path)
        return path

    def run_cli(self, source, *flags, output=None):
        return subprocess.run(
            [sys.executable, "-X", "utf8", "-m", "literature_manager", str(source), *flags,
             "--output", str(output or self.output), "--log-file", str(self.log)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            encoding="utf-8",
            timeout=30,
        )

    def read_catalog(self):
        return json.loads(self.output.read_text(encoding="utf-8"))

    def test_extracts_metadata_doi_page_text_and_utf8_log(self):
        pdf = self.make_pdf("样例论文.PDF", with_text=True)
        result = self.run_cli(pdf, "--include-text")

        self.assertEqual(result.returncode, 0, result.stderr)
        catalogue = self.read_catalog()
        self.assertEqual(catalogue["schema_version"], 1)
        self.assertEqual(catalogue["errors"], [])
        record = catalogue["documents"][0]
        self.assertEqual(record["source"], "样例论文.PDF")
        self.assertEqual(record["title"], "测试论文")
        self.assertEqual(record["author"], "李明")
        self.assertEqual(record["keywords"], ["PDF", "Python"])
        self.assertEqual(record["doi"], "10.1234/example")
        self.assertEqual(record["page_count"], 2)
        self.assertEqual(record["pages_without_text"], [2])
        self.assertIn("DOI", record["pages"][0]["text"])
        self.assertEqual(record["pages"][1], {"page_number": 2, "text": ""})
        self.assertIn("测试论文", self.output.read_text(encoding="utf-8"))
        self.assertIn("未提取到文本", self.log.read_text(encoding="utf-8"))

    def test_recursive_batch_continues_after_corrupt_and_encrypted_files(self):
        self.make_pdf("papers/nested/备用标题.pdf")
        self.make_pdf("papers/encrypted.pdf", password="test-password")
        (self.root / "papers" / "broken.pdf").write_bytes(b"not a PDF")

        shallow = self.run_cli(self.root / "papers")
        self.assertEqual(shallow.returncode, 1, shallow.stderr)
        self.assertFalse(self.output.exists())

        recursive = self.run_cli(self.root / "papers", "--recursive")
        self.assertEqual(recursive.returncode, 1, recursive.stderr)
        catalogue = self.read_catalog()
        record = catalogue["documents"][0]
        self.assertEqual(record["source"], "nested/备用标题.pdf")
        self.assertEqual(record["title"], "备用标题")
        self.assertEqual(record["title_source"], "filename")
        self.assertIsNone(record["author"])
        self.assertNotIn("pages", record)
        self.assertEqual([error["source"] for error in catalogue["errors"]],
                         ["broken.pdf", "encrypted.pdf"])
        self.assertIn("已加密", catalogue["errors"][1]["message"])
        self.assertIn("读取失败", self.log.read_text(encoding="utf-8"))

    def test_rejects_output_that_would_replace_a_pdf(self):
        pdf = self.make_pdf("source.pdf")
        original = pdf.read_bytes()
        result = self.run_cli(pdf, output=pdf)

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("路径与输入 PDF 冲突", result.stderr)
        self.assertEqual(pdf.read_bytes(), original)

    def test_failed_replace_keeps_existing_catalogue_and_removes_temp_file(self):
        self.output.parent.mkdir()
        self.output.write_text("{}\n", encoding="utf-8")
        with patch.object(Path, "replace", side_effect=PermissionError("file locked")):
            with self.assertRaises(PermissionError):
                write_catalog(self.output, [{"title": "new"}], [])

        self.assertEqual(self.output.read_text(encoding="utf-8"), "{}\n")
        self.assertEqual(list(self.output.parent.iterdir()), [self.output])
