"""GitHub repository ingestion — Phase 1 scope.

Clones (shallow) and extracts repo metadata plus prose documentation (.md/.rst) for NER. Source code itself is NOT parsed here: AST-based code intelligence is next Phase. The clone lands in a gitignored cache dir and the commit hash is recorded for provenance.
"""

from dataclasses import dataclass
from pathlib import Path

from git import Repo

DOC_SUFFIXES: frozenset[str] = frozenset({".md", ".rst"})
MAX_DOC_BYTES = 200_000  # skip generated/changelog monsters
SKIP_DIRS: frozenset[str] = frozenset({".git", "node_modules", ".venv", "venv"})


@dataclass
class RepoDocument:
    path: str  # repo-relative, posix-style
    text: str


@dataclass
class RepoContent:
    name: str
    url: str
    commit: str
    documents: list[RepoDocument]


def ingest_repository(url: str, cache_dir: str | Path) -> RepoContent:
    """Clone (or reuse a cached clone of) a repository and extract docs.

    Args:
        url: HTTPS clone URL, e.g. "https://github.com/rdflib/rdflib".
        cache_dir: Directory for clones; must be gitignored.

    Returns:
        RepoContent with metadata and cleaned doc texts.
    """
    from ingestion.markdown_parser import clean_markdown

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    name = url.rstrip("/").removesuffix(".git").rsplit("/", 1)[-1]
    dest = cache_dir / name

    if (dest / ".git").exists():
        repo = Repo(dest)
    else:
        repo = Repo.clone_from(url, dest, depth=1)
    commit = repo.head.commit.hexsha

    documents: list[RepoDocument] = []
    for file in sorted(dest.rglob("*")):
        if (
            file.is_file()
            and file.suffix.lower() in DOC_SUFFIXES
            and file.stat().st_size <= MAX_DOC_BYTES
            and not (SKIP_DIRS & set(file.parts))
        ):
            raw = file.read_text(encoding="utf-8", errors="replace")
            text = clean_markdown(raw)
            if text.strip():
                documents.append(
                    RepoDocument(
                        path=file.relative_to(dest).as_posix(),
                        text=text,
                    )
                )

    return RepoContent(name=name, url=url, commit=commit, documents=documents)
