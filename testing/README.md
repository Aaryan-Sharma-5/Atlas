# Testing

Test scripts for validating each stage of the Atlas pipeline.

## Test Scripts

### test_pdf_ingestion.py

Validates the PDF ingestion pipeline (Days 3-4):
- Loads PDF from `examples/2003.02320v6.pdf`
- Extracts metadata (title, authors, page count, text)
- Chunks text into fixed-size segments (500 tokens, 50 token overlap)
- Verifies output format and statistics

**Run:**
```bash
python testing/test_pdf_ingestion.py
```

**Expected Output:**
```
Testing: 2003.02320v6.pdf
======================================================================
Extracting PDF metadata...
[OK] PDF Metadata Extracted:
     Title:    Knowledge Graphs
     Authors:  16 author(s) found
     Pages:    135
     Text:     487,126 characters
     Hash:     348d06999cd5fd03...

Chunking text (target: 500 tokens, overlap: 50)...
[OK] Text Chunked:
     Total chunks: 41

     Chunk  0:  500 tokens | auto                 | --- Page 1 --- Knowledge Graphs...
     Chunk  1:  500 tokens | auto                 | ...(continued)
     Chunk  2:  500 tokens | auto                 | 
     Chunk  3:  500 tokens | auto                 | 
     Chunk  4:  500 tokens | auto                 | 
     ...
     Chunk 40:  (last chunk)

Total tokens: 24,056 (avg: 587 per chunk)

======================================================================
[OK] Real PDF ingestion pipeline test PASSED
```

**What it validates:**
- PDF parsing works correctly
- Text extraction preserves content
- Metadata extraction (title, authors, page count)
- Chunking produces expected output
- Page markers track chunk location
- SHA256 file hash computed for deduplication

## Test Corpus

Test data is stored in `examples/`:
- `2003.02320v6.pdf` - Knowledge Graphs paper (135 pages, 2.3 MB)
- `expected_output/` - Golden output for regression testing

See `examples/README.md` for test corpus documentation.

## Regression Testing

When extraction or processing logic changes:
1. Run `python testing/test_pdf_ingestion.py`
2. Compare output against `examples/expected_output/`
3. If changes are intentional, update expected output
4. If unexpected, debug the root cause

Do NOT silently regenerate expected output. Every change must be deliberate and documented.

## Adding New Tests

When adding new test scripts:
1. Place in `testing/` directory
2. Name: `test_<stage>.py` (e.g., `test_entity_extraction.py`, `test_validation.py`)
3. Load test data from `examples/`
4. Validate against `examples/expected_output/`
5. Document in this README
6. Ensure script is executable: `chmod +x testing/test_*.py`
