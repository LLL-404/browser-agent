"""知识库 — 数据加载、文本检索、来源追踪。"""

from __future__ import annotations

import re
import sqlite3
from collections import Counter
from pathlib import Path

from shared.logging_config import get_logger

logger = get_logger("chat.knowledge")

_TEXT_EXTENSIONS = {".txt", ".md", ".rst", ".csv"}
_DOCS_DIR = Path("docs")
_DB_PATH = Path("data/jobs.db")

_SECTION_SEPARATOR = "\n---\n"


def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _read_pdf_file(path: Path) -> str:
    try:
        from PyPDF2 import PdfReader  # pylint: disable=import-outside-toplevel
    except ImportError:
        return f"[PDF 解析需要 PyPDF2 库: {path.name}]"
    try:
        reader = PdfReader(str(path))
        pages: list[str] = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
        return "\n\n".join(pages)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("PDF 解析失败 %s: %s", path, e)
        return f"[PDF 解析失败: {path.name}]"


def _simple_tokenize(text: str) -> list[str]:
    return re.findall(r"[\w\u4e00-\u9fff]+", text.lower())


def _keyword_score(query_tokens: list[str], text_tokens: list[str]) -> float:
    if not query_tokens:
        return 0.0
    q_set = set(query_tokens)
    t_set = set(text_tokens)
    hits = q_set & t_set
    return len(hits) / len(q_set) if q_set else 0.0


class KnowledgeSource:
    """单个知识来源。"""

    def __init__(self, name: str, content: str, source_type: str):
        self.name = name
        self.content = content
        self.source_type = source_type  # "sqlite", "doc", "file"
        self._tokens = _simple_tokenize(content)

    def match_score(self, query: str) -> float:
        """计算查询与当前知识来源的关键词匹配分数。"""
        q_tokens = _simple_tokenize(query)
        return _keyword_score(q_tokens, self._tokens)


class KnowledgeBase:
    """知识库：管理多个来源，支持关键词检索。"""

    def __init__(self):
        self.sources: list[KnowledgeSource] = []
        self._auto_loaded = False
        self._loaded_paths: set[str] = set()
        logger.info("KnowledgeBase 初始化")

    def auto_load(self) -> None:
        """自动加载项目已有的数据源。"""
        if self._auto_loaded:
            return
        self._auto_loaded = True

        # 加载 SQLite 岗位数据
        self._load_from_sqlite()

        # 加载 docs/ 文档
        self._load_docs_dir()

        logger.info("KnowledgeBase 自动加载完成，共 %d 个来源", len(self.sources))

    def _load_from_sqlite(self) -> None:
        if not _DB_PATH.exists():
            logger.info("SQLite 数据库不存在: %s", _DB_PATH)
            return
        try:
            conn = sqlite3.connect(str(_DB_PATH))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row["name"] for row in cursor.fetchall()]

            for table in tables:
                cursor.execute(f"SELECT * FROM \"{table}\" LIMIT 500")
                rows = cursor.fetchall()
                if not rows:
                    continue
                columns = [desc[0] for desc in cursor.description]
                lines: list[str] = []
                for row in rows:
                    values = {col: str(row[col] or "") for col in columns}
                    line = " | ".join(f"{k}={v}" for k, v in values.items())
                    lines.append(line)
                content = "\n".join(lines)
                if content.strip():
                    name = f"db:{table}({len(rows)}条)"
                    self.sources.append(KnowledgeSource(name, content, "sqlite"))

            conn.close()
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("SQLite 加载失败: %s", e)

    def _load_docs_dir(self) -> None:
        if not _DOCS_DIR.exists():
            return
        md_files = sorted(_DOCS_DIR.rglob("*.md"))
        for fp in md_files:
            try:
                content = _read_text_file(fp)
                if content.strip():
                    rel = fp.relative_to(_DOCS_DIR.parent) if fp.is_relative_to(_DOCS_DIR.parent) else fp
                    name = f"doc:{rel}"
                    self.sources.append(KnowledgeSource(name, content, "doc"))
                    self._loaded_paths.add(str(fp.resolve()))
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.warning("文档加载失败 %s: %s", fp, e)

    def load_file(self, path: str) -> str:
        """加载用户指定的文件或目录。返回加载结果的描述文本。"""
        p = Path(path).resolve()
        if not p.exists():
            return f"路径不存在: {path}"
        if str(p) in self._loaded_paths:
            return f"已加载过: {path}"

        loaded_count = 0
        if p.is_dir():
            exts = _TEXT_EXTENSIONS | {".pdf"}
            for fp in sorted(p.rglob("*")):
                if fp.suffix.lower() in exts and str(fp.resolve()) not in self._loaded_paths:
                    self._load_single_file(fp)
                    loaded_count += 1
        else:
            self._load_single_file(p)
            loaded_count = 1

        if loaded_count > 0:
            logger.info("知识库新增 %d 个来源（来自 %s）", loaded_count, path)
            return f"已加载 {loaded_count} 个文件（来源: {path}）"
        return f"未找到可加载的文件（支持: {', '.join(sorted(_TEXT_EXTENSIONS | {'.pdf'}))}）"

    def _load_single_file(self, path: Path) -> None:
        try:
            ext = path.suffix.lower()
            content = _read_pdf_file(path) if ext == ".pdf" else _read_text_file(path)
            if content.strip():
                rel = str(path)
                self.sources.append(KnowledgeSource(rel, content, "file"))
                self._loaded_paths.add(str(path.resolve()))
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("文件加载失败 %s: %s", path, e)

    def search(self, query: str, top_k: int = 5) -> list[tuple[str, str, float]]:
        """关键词检索，返回 [(名称, 内容片段, 匹配分数)]。"""
        if not self.sources or not query.strip():
            return []

        scored = [(s, s.match_score(query)) for s in self.sources]
        scored.sort(key=lambda x: x[1], reverse=True)
        results: list[tuple[str, str, float]] = []
        for source, score in scored:
            if score > 0:
                snippet = source.content[:500]
                results.append((source.name, snippet, round(score, 3)))
                if len(results) >= top_k:
                    break
        return results

    def format_context(self, query: str = "") -> str:
        """将所有知识格式化为 System Prompt 可注入的文本。"""
        if not self.sources:
            return ""

        relevant = self.search(query) if query else []
        if relevant:
            lines = ["根据以下信息回答用户问题：\n"]
            for name, snippet, score in relevant:
                lines.append(f"--- {name} (匹配度: {score}) ---")
                lines.append(snippet)
                lines.append("")
            return "\n".join(lines)

        parts: list[str] = []
        for source in self.sources:
            content = source.content
            if len(content) > 1000:
                content = content[:1000] + "\n...(截断)"
            parts.append(f"--- {source.name} ---")
            parts.append(content)
        return _SECTION_SEPARATOR.join(parts)

    @property
    def source_summary(self) -> str:
        """返回知识来源摘要。"""
        if not self.sources:
            return "未加载任何知识来源"
        type_counts: Counter[str] = Counter(s.source_type for s in self.sources)
        lines = [f"共 {len(self.sources)} 个知识来源："]
        for stype, count in sorted(type_counts.items()):
            lines.append(f"  {stype}: {count} 个")
        lines.append("")
        lines.append("详细来源列表：")
        for i, s in enumerate(self.sources, 1):
            c_len = len(s.content)
            lines.append(f"  {i}. [{s.source_type}] {s.name} ({c_len} 字符)")
        return "\n".join(lines)
