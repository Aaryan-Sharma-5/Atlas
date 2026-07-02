#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.pdf_parser import extract_pdf_metadata
from ingestion.chunker import chunk_text

pdf_path = Path(__file__).parent.parent / "examples" / "2003.02320v6.pdf"

print(f"Testing: {pdf_path.name}")
print("=" * 70)
print()

try:
    # Extract metadata
    print("Extracting PDF metadata...")
    metadata = extract_pdf_metadata(pdf_path)
    
    print(f"[OK] PDF Metadata Extracted:")
    print(f"     Title:    {metadata.title or '(no title)'}")
    print(f"     Authors:  {len(metadata.authors)} author(s) found")
    print(f"     Pages:    {metadata.page_count}")
    print(f"     Text:     {len(metadata.text):,} characters")
    print(f"     Hash:     {metadata.file_hash[:16]}...")
    print()
    
    # Chunk the text
    print("Chunking text (target: 500 tokens, overlap: 50)...")
    chunks = chunk_text(
        metadata.text,
        source_file=str(pdf_path),
        target_tokens=500,
        overlap_tokens=50,
    )
    
    print(f"[OK] Text Chunked:")
    print(f"     Total chunks: {len(chunks)}")
    print()
    
    for i, chunk in enumerate(chunks[:5]):  # Show first 5 chunks
        token_count = len(chunk.content.split())
        preview = chunk.content[:50].replace("\n", " ")
        pages_str = str(chunk.page_markers) if chunk.page_markers else "auto"
        print(f"     Chunk {i:2d}: {token_count:4d} tokens | {pages_str:20s} | {preview}...")
    
    if len(chunks) > 5:
        print(f"     ...")
        print(f"     Chunk {len(chunks)-1:2d}: {len(chunks[-1].content.split()):4d} tokens | (last chunk)")
    
    print()
    total_tokens = sum(len(c.content.split()) for c in chunks)
    avg_tokens = total_tokens / len(chunks) if chunks else 0
    print(f"Total tokens: {total_tokens:,} (avg: {avg_tokens:.0f} per chunk)")
    print()
    print("=" * 70)
    print("[OK] Real PDF ingestion pipeline test PASSED")
    print()
    
except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()
