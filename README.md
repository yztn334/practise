# Python 文献文件管理工具

将本地 PDF 的标题、作者、主题、关键词、DOI 和页数汇总到一个 JSON 文件。支持批量扫描目录、按需导出逐页正文，并将处理进度与失败原因写入日志。处理过程在本机运行。

## 安装与运行

需要 Python 3.9 或更高版本。以下命令在项目根目录的 Windows PowerShell 中运行。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -X utf8 -m literature_manager --help
```

将文献放入 `papers` 目录。下面用 `论文.pdf` 示范单个文件处理，请替换为你的文件名。

```powershell
# 处理单个 PDF
.\.venv\Scripts\python.exe -X utf8 -m literature_manager ".\papers\论文.pdf"

# 批量处理目录及其子目录，同时保存每页正文
.\.venv\Scripts\python.exe -X utf8 -m literature_manager .\papers --recursive --include-text

# 自定义输出路径，开启调试日志
.\.venv\Scripts\python.exe -X utf8 -m literature_manager .\papers -o .\output\batch.json --log-file .\logs\batch.log -v
```

macOS 和 Linux 可使用 `python3 -m venv .venv`，随后用 `./.venv/bin/python` 替换命令中的 Windows 解释器路径。

默认输出为 `output/literature.json`，默认日志为 `logs/literature-manager.log`。路径相对于运行命令时所在的目录。目录输入默认只扫描当前层，使用 `--recursive` 才会扫描子目录。扩展名匹配忽略大小写。

## 输出示例

```json
{
  "schema_version": 1,
  "documents": [
    {
      "source": "计算机科学/论文.pdf",
      "title": "文献管理示例",
      "title_source": "metadata",
      "author": "李明",
      "subject": null,
      "keywords": ["PDF", "Python"],
      "doi": "10.1234/example",
      "page_count": 2,
      "pages_without_text": [2]
    }
  ],
  "errors": []
}
```

- `source` 是输入目录下的相对路径，单文件模式下为文件名。子目录中的同名 PDF 会有各自的记录。
- `title_source` 为 `metadata` 或 `filename`。标题缺失时使用去掉扩展名的文件名，其他缺失的单值字段保存为 `null`，缺失的关键词保存为 `[]`。
- `pages_without_text` 列出未提取到文本的页码，页码从 1 开始。启用 `--include-text` 时还会输出 `pages`，每项包含 `page_number` 和 `text`。
- 批次中部分 PDF 失败时，`documents` 保存成功的结果，`errors` 保存失败文件的 `source` 和 `message`。所有 PDF 都失败时，只记录日志，已有 JSON 会保留。
- 每次成功写入都会生成当前批次的完整快照，并替换同路径的旧结果。需要保留不同批次时，可使用不同的 `--output` 路径。

| 退出码 | 含义 |
| --- | --- |
| `0` | 所有 PDF 读取成功，JSON 已写入。 |
| `1` | 有 PDF 读取失败。部分成功时仍会写入 JSON。 |
| `2` | 参数或路径错误、未找到 PDF，或无法写入日志或 JSON。 |

PowerShell 中可以在命令执行后查看 `$LASTEXITCODE`。

## 按代码学习

程序的执行顺序是 `__main__.py` → `cli.py` → 查找文件、逐份提取 → 写入 JSON。

### 1. 用 `argparse` 处理命令行参数

`python -m literature_manager` 运行包中的 `__main__.py`。入口调用 `cli.main()`，再用 `SystemExit` 将返回值交给操作系统。`source` 是必填位置参数，`type=Path` 会把参数转换为路径对象。`--recursive` 和 `--include-text` 使用 `action="store_true"`，传入时其值为 `True`，省略时为 `False`。

### 2. 用 `pathlib` 查找 PDF

`catalog.find_pdfs()` 用 `is_file()` 和 `is_dir()` 区分单文件与目录。`suffix.lower()` 把 `.pdf` 和 `.PDF` 统一处理。递归模式通过 `os.walk()` 遍历子目录。`relative_to()` 去掉根目录，`as_posix()` 统一使用 `/`，使 JSON 更容易在不同操作系统之间使用。排序使同一批文件在多次运行时保持相同的记录顺序。

### 3. 用 `pypdf` 分别读取元数据与正文

`extractor.extract_pdf()` 以 `rb` 模式打开 PDF。`with` 会在读取结束或出现异常时关闭文件。`PdfReader` 从二进制流解析文档，`reader.metadata` 读取 PDF 文档信息字典，`reader.pages` 提供页面，`page.extract_text()` 从页面提取文本。标题、作者、主题和关键词来自文档信息字典，其中的值由 PDF 制作者填写，可能缺失或不准确。[pypdf 元数据文档](https://pypdf.readthedocs.io/en/6.21.1/user/metadata.html)

DOI 优先从 `/DOI` 或 `/doi` 元数据匹配，随后检查正文前两页。正则表达式 `10\.\d{4,9}/` 匹配常见的 DOI 前缀，后面再匹配标识符字符。结果是本地候选值。当前实现未查询注册机构，多 DOI 的文献、跨行 DOI 或超出前两页的 DOI 可能需要人工核对。双栏 PDF 的提取顺序可能和阅读顺序不同，纯图片扫描件需要先通过 OCR 生成文字层。加密 PDF 会记录为读取失败。[pypdf 文本提取文档](https://pypdf.readthedocs.io/en/6.21.1/user/extract-text.html)

### 4. 用 `json` 保存结构化结果

`catalog.write_catalog()` 将 Python 字典和列表交给 `json.dump()`。字典变成 JSON 对象，列表变成数组，`None` 变成 `null`。UTF-8 配合 `ensure_ascii=False` 让中文保留可读形式，`indent=2` 方便检查层级。程序先在目标目录写完整的临时文件，再用 `Path.replace()` 替换目标。如果序列化或替换失败，旧文件仍可读取。`schema_version` 供未来的读取程序识别数据格式。

### 5. 用 `logging` 定位批量处理中的问题

`cli.py` 将同一条日志发往两个处理器。`StreamHandler` 让终端实时显示进度，`FileHandler` 以 UTF-8 追加记录，便于运行结束后复查。`INFO` 记录读取与保存结果，`WARNING` 提示有页面没有可提取文本，`ERROR` 记录失败。`-v` 还会记录调试信息和异常堆栈。异常处理放在单个 PDF 的循环内，损坏文件不会中断后续文件的处理。

### 6. 用 `unittest` 验证完整流程

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

测试临时生成带文字、空白页和加密的 PDF，并从命令行入口检查 JSON、日志和退出码。另有测试检查输出路径与输入 PDF 冲突时的处理，以及替换失败时旧 JSON 是否保留。测试运行后会清理临时文献和输出。

## GitHub 提交内容

`.gitignore` 排除了 PDF、虚拟环境以及默认的输入、输出和日志目录。使用自定义输出目录时，提交前可用 `git status --short` 检查目录内容。`requirements.txt` 固定了 `pypdf` 的版本，克隆仓库后可以用它恢复项目依赖。[GitHub 上传本地代码指南](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github?platform=windows)
