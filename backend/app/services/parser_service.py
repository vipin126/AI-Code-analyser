"""Parser service — Tree-sitter AST parsing and dependency extraction.

Supports Python, JavaScript, and TypeScript for MVP.
Extracts classes, functions, imports, and builds a dependency graph
as a JSON-serializable adjacency list (no NetworkX dependency).
"""

import logging
from pathlib import Path

import tree_sitter_javascript as tsjs
import tree_sitter_python as tspy
import tree_sitter_typescript as tsts
from tree_sitter import Language, Node, Parser

from app.schemas.analysis import ASTNode, CodeChunk, DependencyEdge, ParseResult

logger = logging.getLogger(__name__)


# ── Language Registry ────────────────────────────────────────

LANGUAGES: dict[str, Language] = {
    "python": Language(tspy.language()),
    "javascript": Language(tsjs.language()),
    "typescript": Language(tsts.language_typescript()),
}

SUPPORTED_LANGUAGES: set[str] = set(LANGUAGES.keys())


# ── Tree-sitter Query Patterns ───────────────────────────────
# These define what AST nodes we extract for each language.

PYTHON_QUERIES = {
    "classes": "(class_definition name: (identifier) @name) @class",
    "functions": "(function_definition name: (identifier) @name) @func",
    "imports": [
        "(import_statement name: (dotted_name) @module) @import",
        "(import_from_statement module_name: (dotted_name) @module) @import",
    ],
}

JS_TS_QUERIES = {
    "classes": "(class_declaration name: (identifier) @name) @class",
    "functions": [
        "(function_declaration name: (identifier) @name) @func",
        "(lexical_declaration (variable_declarator name: (identifier) @name value: (arrow_function)) ) @func",
    ],
    "imports": "(import_statement source: (string) @source) @import",
}


class ParserService:
    """Service for parsing source code files using Tree-sitter and extracting
    structural information (classes, functions, imports) and dependency edges.
    """

    def __init__(self) -> None:
        self._parsers: dict[str, Parser] = {}
        for lang_name, language in LANGUAGES.items():
            parser = Parser(language)
            self._parsers[lang_name] = parser

    def parse_file(self, file_path: Path, language: str, source: bytes | None = None) -> ParseResult:
        """Parse a single source file and extract AST nodes + dependencies.

        Args:
            file_path: Path to the source file (used for identification).
            language: Programming language identifier.
            source: Raw source bytes. If None, reads from file_path.

        Returns:
            ParseResult containing extracted nodes and dependency edges.
        """
        if language not in SUPPORTED_LANGUAGES:
            return ParseResult(
                file_path=str(file_path),
                language=language,
                error=f"Unsupported language: {language}",
            )

        try:
            if source is None:
                source = file_path.read_bytes()

            parser = self._parsers[language]
            tree = parser.parse(source)
            root_node = tree.root_node

            # Decode source for text extraction
            source_text = source.decode("utf-8", errors="replace")
            source_lines = source_text.split("\n")

            # Extract nodes based on language
            if language == "python":
                nodes = self._extract_python_nodes(root_node, str(file_path), source_lines)
                deps = self._extract_python_imports(root_node, str(file_path))
            else:
                nodes = self._extract_js_ts_nodes(root_node, str(file_path), source_lines)
                deps = self._extract_js_ts_imports(root_node, str(file_path), source_text)

            return ParseResult(
                file_path=str(file_path),
                language=language,
                nodes=nodes,
                dependencies=deps,
                line_count=len(source_lines),
            )

        except Exception as e:
            logger.error("Failed to parse %s: %s", file_path, e)
            return ParseResult(
                file_path=str(file_path),
                language=language,
                error=str(e),
            )

    def parse_repository(
        self,
        clone_path: Path,
        file_manifest: list[dict],
    ) -> list[ParseResult]:
        """Parse all recognized source files in a cloned repository.

        Args:
            clone_path: Root path of the cloned repo.
            file_manifest: List of file info dicts with 'path' and 'language' keys.

        Returns:
            List of ParseResult for each file.
        """
        results: list[ParseResult] = []

        for file_info in file_manifest:
            language = file_info["language"]
            if language not in SUPPORTED_LANGUAGES:
                continue

            file_path = clone_path / file_info["path"]
            if not file_path.exists():
                continue

            result = self.parse_file(file_path, language)
            # Normalize path to relative
            result.file_path = file_info["path"]
            results.append(result)

            if result.error:
                logger.warning("Parse error in %s: %s", file_info["path"], result.error)

        logger.info(
            "Parsed %d/%d files (%d with errors)",
            len(results),
            len(file_manifest),
            sum(1 for r in results if r.error),
        )
        return results

    def build_dependency_graph(
        self, parse_results: list[ParseResult]
    ) -> dict:
        """Build a JSON-serializable dependency graph from parse results.

        The graph is an adjacency list representation:
        - nodes: List of {id, name, type, file_path, line_start, line_end}
        - edges: List of {source, target, relationship}

        Args:
            parse_results: Parsed output from parse_repository().

        Returns:
            Dict with 'nodes' and 'edges' keys.
        """
        all_nodes: list[dict] = []
        all_edges: list[dict] = []
        seen_node_ids: set[str] = set()

        for result in parse_results:
            if result.error:
                continue

            for node in result.nodes:
                node_id = f"{result.file_path}:{node.name}"
                if node_id not in seen_node_ids:
                    seen_node_ids.add(node_id)
                    all_nodes.append({
                        "id": node_id,
                        "name": node.name,
                        "type": node.type,
                        "file_path": result.file_path,
                        "line_start": node.line_start,
                        "line_end": node.line_end,
                    })

            for dep in result.dependencies:
                all_edges.append({
                    "source": dep.source,
                    "target": dep.target,
                    "relationship": dep.relationship,
                })

        return {
            "nodes": all_nodes,
            "edges": all_edges,
            "file_count": len(parse_results),
        }

    def extract_code_chunks(
        self, file_path: str, language: str, source: bytes
    ) -> list[CodeChunk]:
        """Split a source file into semantic chunks at function/class boundaries.

        Each chunk represents a complete function, method, or class definition.
        Files smaller than the threshold are returned as a single chunk.

        Args:
            file_path: Relative file path for identification.
            language: Programming language identifier.
            source: Raw source bytes.

        Returns:
            List of CodeChunk objects suitable for local code search.
        """
        if language not in SUPPORTED_LANGUAGES:
            return []

        parser = self._parsers[language]
        tree = parser.parse(source)
        root_node = tree.root_node
        source_text = source.decode("utf-8", errors="replace")
        source_lines = source_text.split("\n")

        chunks: list[CodeChunk] = []

        # Find top-level definitions for chunking
        chunk_node_types = self._get_chunk_node_types(language)
        definition_nodes = self._find_nodes_by_type(root_node, chunk_node_types)

        if not definition_nodes:
            # No definitions found — return entire file as one chunk
            chunks.append(CodeChunk(
                content=source_text,
                file_path=file_path,
                language=language,
                start_line=1,
                end_line=len(source_lines),
                chunk_type="module",
                node_name=Path(file_path).stem,
                token_estimate=len(source_text) // 4,
            ))
            return chunks

        for node in definition_nodes:
            name = self._get_node_name(node, language)
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            content = "\n".join(source_lines[start_line - 1 : end_line])

            chunk_type = "class" if "class" in node.type else "function"

            chunks.append(CodeChunk(
                content=content,
                file_path=file_path,
                language=language,
                start_line=start_line,
                end_line=end_line,
                chunk_type=chunk_type,
                node_name=name,
                token_estimate=len(content) // 4,  # Rough estimate
            ))

        return chunks

    # ── Python Extraction ────────────────────────────────────

    def _extract_python_nodes(
        self, root: Node, file_path: str, source_lines: list[str]
    ) -> list[ASTNode]:
        """Extract class and function definitions from Python AST."""
        nodes: list[ASTNode] = []

        for node in self._walk_tree(root):
            if node.type == "class_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    nodes.append(ASTNode(
                        name=name_node.text.decode("utf-8"),
                        type="class",
                        file_path=file_path,
                        line_start=node.start_point[0] + 1,
                        line_end=node.end_point[0] + 1,
                        docstring=self._extract_python_docstring(node),
                    ))

            elif node.type == "function_definition":
                name_node = node.child_by_field_name("name")
                params_node = node.child_by_field_name("parameters")
                if name_node:
                    params = self._extract_python_params(params_node) if params_node else []
                    node_type = "method" if self._is_method(node) else "function"
                    nodes.append(ASTNode(
                        name=name_node.text.decode("utf-8"),
                        type=node_type,
                        file_path=file_path,
                        line_start=node.start_point[0] + 1,
                        line_end=node.end_point[0] + 1,
                        docstring=self._extract_python_docstring(node),
                        parameters=params,
                    ))

        return nodes

    def _extract_python_imports(self, root: Node, file_path: str) -> list[DependencyEdge]:
        """Extract import statements from Python AST."""
        edges: list[DependencyEdge] = []

        for node in self._walk_tree(root):
            if node.type == "import_statement":
                for child in node.children:
                    if child.type == "dotted_name":
                        module = child.text.decode("utf-8")
                        edges.append(DependencyEdge(
                            source=file_path,
                            target=module,
                            relationship="imports",
                        ))

            elif node.type == "import_from_statement":
                module_node = node.child_by_field_name("module_name")
                if module_node:
                    module = module_node.text.decode("utf-8")
                    edges.append(DependencyEdge(
                        source=file_path,
                        target=module,
                        relationship="imports",
                    ))

        return edges

    def _extract_python_docstring(self, node: Node) -> str | None:
        """Extract the docstring from a Python class or function node."""
        body = node.child_by_field_name("body")
        if body and body.child_count > 0:
            first_stmt = body.children[0]
            if first_stmt.type == "expression_statement":
                expr = first_stmt.children[0] if first_stmt.child_count > 0 else None
                if expr and expr.type == "string":
                    docstring = expr.text.decode("utf-8")
                    # Strip triple quotes
                    for q in ('"""', "'''"):
                        if docstring.startswith(q) and docstring.endswith(q):
                            return docstring[3:-3].strip()
        return None

    def _extract_python_params(self, params_node: Node) -> list[str]:
        """Extract parameter names from a Python function parameters node."""
        params: list[str] = []
        for child in params_node.children:
            if child.type == "identifier":
                params.append(child.text.decode("utf-8"))
            elif child.type in ("default_parameter", "typed_parameter", "typed_default_parameter"):
                name_node = child.child_by_field_name("name")
                if name_node:
                    params.append(name_node.text.decode("utf-8"))
        return params

    # ── JavaScript / TypeScript Extraction ───────────────────

    def _extract_js_ts_nodes(
        self, root: Node, file_path: str, source_lines: list[str]
    ) -> list[ASTNode]:
        """Extract class and function definitions from JS/TS AST."""
        nodes: list[ASTNode] = []

        for node in self._walk_tree(root):
            if node.type == "class_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    nodes.append(ASTNode(
                        name=name_node.text.decode("utf-8"),
                        type="class",
                        file_path=file_path,
                        line_start=node.start_point[0] + 1,
                        line_end=node.end_point[0] + 1,
                    ))

            elif node.type == "function_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    nodes.append(ASTNode(
                        name=name_node.text.decode("utf-8"),
                        type="function",
                        file_path=file_path,
                        line_start=node.start_point[0] + 1,
                        line_end=node.end_point[0] + 1,
                    ))

            elif node.type == "lexical_declaration":
                # Arrow functions: const foo = () => {}
                for child in node.children:
                    if child.type == "variable_declarator":
                        name_node = child.child_by_field_name("name")
                        value_node = child.child_by_field_name("value")
                        if (
                            name_node
                            and value_node
                            and value_node.type == "arrow_function"
                        ):
                            nodes.append(ASTNode(
                                name=name_node.text.decode("utf-8"),
                                type="function",
                                file_path=file_path,
                                line_start=node.start_point[0] + 1,
                                line_end=node.end_point[0] + 1,
                            ))

            elif node.type == "interface_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    nodes.append(ASTNode(
                        name=name_node.text.decode("utf-8"),
                        type="interface",
                        file_path=file_path,
                        line_start=node.start_point[0] + 1,
                        line_end=node.end_point[0] + 1,
                    ))

            elif node.type == "type_alias_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    nodes.append(ASTNode(
                        name=name_node.text.decode("utf-8"),
                        type="type_alias",
                        file_path=file_path,
                        line_start=node.start_point[0] + 1,
                        line_end=node.end_point[0] + 1,
                    ))

        return nodes

    def _extract_js_ts_imports(
        self, root: Node, file_path: str, source_text: str
    ) -> list[DependencyEdge]:
        """Extract import statements from JS/TS AST."""
        edges: list[DependencyEdge] = []

        for node in self._walk_tree(root):
            if node.type == "import_statement":
                source_node = node.child_by_field_name("source")
                if source_node:
                    # Strip quotes from the import path
                    module = source_node.text.decode("utf-8").strip("'\"")
                    edges.append(DependencyEdge(
                        source=file_path,
                        target=module,
                        relationship="imports",
                    ))

        return edges

    # ── Tree Walking Utilities ───────────────────────────────

    def _walk_tree(self, node: Node) -> list[Node]:
        """Depth-first walk of the AST, yielding all nodes."""
        result: list[Node] = []
        cursor = node.walk()

        visited = False
        while True:
            if not visited:
                result.append(cursor.node)
                if cursor.goto_first_child():
                    continue
            if cursor.goto_next_sibling():
                visited = False
                continue
            if not cursor.goto_parent():
                break
            visited = True

        return result

    def _find_nodes_by_type(self, root: Node, types: set[str]) -> list[Node]:
        """Find all nodes matching the given type set."""
        return [n for n in self._walk_tree(root) if n.type in types]

    def _get_chunk_node_types(self, language: str) -> set[str]:
        """Return the AST node types used for chunking boundaries."""
        if language == "python":
            return {"class_definition", "function_definition"}
        return {
            "class_declaration", "function_declaration",
            "lexical_declaration", "export_statement",
        }

    def _get_node_name(self, node: Node, language: str) -> str:
        """Extract the name from a definition node."""
        name_node = node.child_by_field_name("name")
        if name_node:
            return name_node.text.decode("utf-8")

        # For lexical_declaration (arrow functions), dig into variable_declarator
        if node.type == "lexical_declaration":
            for child in node.children:
                if child.type == "variable_declarator":
                    vn = child.child_by_field_name("name")
                    if vn:
                        return vn.text.decode("utf-8")

        return "<anonymous>"

    def _is_method(self, node: Node) -> bool:
        """Check if a function_definition is inside a class (i.e., a method)."""
        parent = node.parent
        while parent:
            if parent.type in ("class_definition", "class_declaration"):
                return True
            parent = parent.parent
        return False
