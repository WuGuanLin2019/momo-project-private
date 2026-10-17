# Action.py 顶部新增
import os

# Action.py 位于 pyScripts/Core/ 下，向上两级即 pyScripts/ 根目录
_PYSCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MEMO_DIR = os.path.join(_PYSCRIPTS_DIR, "Data", "Memo")


def _try_read_text(path: str, encoding: str, errors: str = "strict") -> str | None:
    """按指定编码尝试读取文本文件；解码失败时返回 None。"""
    try:
        with open(path, "r", encoding=encoding, errors=errors) as f:
            return f.read()
    except UnicodeDecodeError:
        return None


def _read_txt(path: str) -> str:
    """尝试常见编码读取 txt 文件，全部失败时忽略无法解码的字节兜底。"""
    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        text = _try_read_text(path, encoding)
        if text is not None:
            return text

    # 所有编码尝试均失败：忽略无法解码的字节，保证总能返回内容
    return _try_read_text(path, "utf-8", errors="ignore") or ""


def _read_pdf(path: str) -> str:
    try:
        import fitz  # pyright: ignore[reportMissingImports]  # PyMuPDF（可选依赖，未安装时由 except 兜底）
        doc = fitz.open(path)
        try:
            return "\n".join(page.get_text() for page in doc)
        finally:
            doc.close()
    except ImportError:
        pass
    try:
        from pypdf import PdfReader  # pyright: ignore[reportMissingImports]  # 可选依赖，未安装时由 except 兜底
        return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    except ImportError:
        return "[无法解析 PDF：未安装 pymupdf/pypdf，请执行 pip install pymupdf]"


def _read_docx(path: str) -> str:
    try:
        import docx  # pyright: ignore[reportMissingImports]  # python-docx（可选依赖，未安装时由 except 兜底）
        d = docx.Document(path)
        return "\n".join(p.text for p in d.paragraphs)
    except ImportError:
        return "[无法解析 docx：未安装 python-docx，请执行 pip install python-docx]"


def read_memo(max_chars_per_file: int = 3000) -> str:
    """
    当你需要阅读备忘录信息时调用。
    读取 Data/Memo 目录下所有 txt / pdf / docx 文件，拼接后以字符串返回。
    """
    if not os.path.isdir(MEMO_DIR):
        return f"备忘录目录不存在：{MEMO_DIR}"

    parts: list[str] = []
    for name in sorted(os.listdir(MEMO_DIR)):
        path = os.path.join(MEMO_DIR, name)
        if not os.path.isfile(path):
            continue

        ext = os.path.splitext(name)[1].lower()
        try:
            if ext == ".txt":
                content = _read_txt(path)
            elif ext == ".pdf":
                content = _read_pdf(path)
            elif ext == ".docx":
                content = _read_docx(path)
            elif ext == ".doc":
                content = "[旧版 .doc 格式暂不支持，请另存为 .docx 或 .txt]"
            else:
                continue  # 跳过其他类型文件

            if max_chars_per_file and len(content) > max_chars_per_file:
                content = content[:max_chars_per_file] + "\n……(已截断)"
        except Exception as e:
            content = f"[读取失败: {e}]"

        parts.append(f"【{name}】\n{content}")

    if not parts:
        return "备忘录目录为空"
    return "\n\n" + "\n\n".join(parts) + "\n"
