"""Command-line interface and per-file error reporting."""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

from .catalog import find_pdfs, write_catalog
from .extractor import extract_pdf


LOGGER = logging.getLogger(__name__)


def parse_args(argv: Optional[list[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m literature_manager",
        description="从 PDF 文献提取信息并保存为 JSON。",
    )
    parser.add_argument("source", type=Path, help="单个 PDF 或包含 PDF 的目录")
    parser.add_argument("-r", "--recursive", action="store_true", help="包含子目录中的 PDF")
    parser.add_argument(
        "-o", "--output", type=Path, default=Path("output/literature.json"),
        help="JSON 路径（默认 output/literature.json）",
    )
    parser.add_argument(
        "--log-file", type=Path, default=Path("logs/literature-manager.log"),
        help="日志路径（默认 logs/literature-manager.log）",
    )
    parser.add_argument("--include-text", action="store_true", help="将每页提取到的正文写入 JSON")
    parser.add_argument("-v", "--verbose", action="store_true", help="记录调试信息和异常堆栈")
    return parser.parse_args(argv)


def same_path(first: Path, second: Path) -> bool:
    if first.resolve() == second.resolve():
        return True
    try:
        return first.samefile(second)
    except FileNotFoundError:
        return False


def configure_logging(log_file: Path, verbose: bool) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(log_file, encoding="utf-8")],
    )


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    try:
        root, pdfs = find_pdfs(args.source, args.recursive)
        if same_path(args.output, args.log_file):
            raise ValueError("JSON 路径和日志路径必须不同。")
        for pdf in pdfs:
            if same_path(pdf, args.output) or same_path(pdf, args.log_file):
                raise ValueError(f"JSON 或日志路径与输入 PDF 冲突：{pdf}")
        configure_logging(args.log_file, args.verbose)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"错误：{error}", file=sys.stderr)
        return 2

    if not pdfs:
        LOGGER.warning("未找到 PDF：%s", args.source)
        return 2

    LOGGER.info("开始处理，共 %d 个 PDF。", len(pdfs))
    documents = []
    errors = []
    for pdf in pdfs:
        source = pdf.relative_to(root).as_posix()
        try:
            document = extract_pdf(pdf, source, args.include_text)
        except Exception as error:
            # A malformed PDF can trigger several parser exceptions. Keep the batch running.
            message = str(error) or type(error).__name__
            errors.append({"source": source, "message": message})
            LOGGER.error("读取失败 %s：%s", source, message, exc_info=args.verbose)
            continue

        documents.append(document)
        LOGGER.info("已读取 %s（%d 页）", source, document["page_count"])
        empty_pages = document["pages_without_text"]
        if empty_pages:
            LOGGER.warning("%s 有 %d 页未提取到文本，详见 JSON 页码。", source, len(empty_pages))

    if not documents:
        LOGGER.error("所有 PDF 均读取失败，详情见日志。")
        return 1

    try:
        write_catalog(args.output, documents, errors)
    except (OSError, UnicodeError) as error:
        LOGGER.error("无法保存 JSON %s：%s", args.output, error, exc_info=args.verbose)
        return 2

    LOGGER.info("成功 %d 个，失败 %d 个。JSON 已保存至 %s", len(documents), len(errors), args.output)
    return 1 if errors else 0
