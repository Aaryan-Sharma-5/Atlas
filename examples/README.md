# Atlas Examples and Test Corpus

This directory contains:
- Fixed research paper for testing and validation
- Expected output for regression testing
- Test scripts for each pipeline stage

## Test Corpus

### 2003.02320v6.pdf

**Knowledge Graphs** (Hogan, Blomqvist, Cochez, et al., 2021)
- **Source:** https://arxiv.org/abs/2003.02320
- **Title:** Knowledge Graphs
- **Authors:** 16 co-authors (Aidan Hogan, Eva Blomqvist, Michael Cochez, Claudia d'Amato, Gerard de Melo, Claudio Gutierrez, José Emilio Labra Gayo, Sabrina Kirrane, Sebastian Neumaier, Axel Polleres, Roberto Navigli, Axel-Cyrille Ngonga Ngomo, Sabbir M. Rashid, Anisa Rula, Lukas Schmelzeisen, Juan Sequeda, Steffen Staab, Antoine Zimmermann)
- **Pages:** 135 (comprehensive survey)
- **Content:** Complete survey on knowledge graphs: representation, acquisition, applications, quality
- **Purpose:** Primary test corpus for entire ingestion and extraction pipeline

**Properties:**
- Format: PDF (binary, official arXiv version)
- Size: 2.3 MB
- Chunks Created: 41 chunks (500 token target, 50 token overlap)
- Total Tokens: ~24,000+
- Extractable Characters: 487,126
- Quality: High (rich entity diversity, complex structure, UTF-8 encoded)

**Why this paper?**
- Rich entity content (16 authors, multiple organizations, cited papers)
- Real-world PDF complexity (135 pages, sections, references)
- Regression testing foundation (fixed, versioned from arXiv)
- Multiple types of entities for validation (PERSON, ORG, GPE, PRODUCT, LANGUAGE)

## Test Scripts

Test scripts are located in the `testing/` directory (not here).

See `testing/README.md` for:
- `test_pdf_ingestion.py` - Validates PDF extraction and chunking
- Instructions for running tests
- Expected output and validation procedures

## Expected Output

Regression test baselines for:
- `expected_output/sample_chunks.json` - Chunked text with metadata
- `expected_output/extracted_entities.json` - Entities from spaCy NER (Day 4)
- `expected_output/internal_entities.json` - Internal Entity objects (Day 5)
- `expected_output/resolved_entities.json` - After deduplication (Day 6)

These serve as the "golden output" for regression testing. When extraction or resolution logic changes, the expected output must be deliberately updated (not silently regenerated).

## Validation Workflow

```
PDF Input (2003.02320v6.pdf)
    ↓
ingestion/pdf_parser.py
    ↓
PDFMetadata (title, authors, pages, text, hash)
    ↓
ingestion/chunker.py
    ↓
list[TextChunk] (41 chunks, ~24k tokens)
    ↓
extraction/entity_extractor.py (Day 4)
    ↓
Raw extraction results (spaCy NER)
    ↓
models/entity.py (Day 5)
    ↓
Entity/Relationship objects
    ↓
graph/validators/ (Day 6)
    ↓
Validated objects
    ↓
graph/builders/ (Day 7)
    ↓
Cypher statements
    ↓
Neo4j write
    ↓
Verify in Neo4j Browser
```

## Adding New Test Cases

To add a new PDF to the test corpus:

1. Download real PDF (preferably from arXiv or official source)
2. Place in `examples/` folder
3. Update this README with paper metadata
4. Run `python examples/test_pdf_ingestion.py` to verify extraction
5. Manually review first 2-3 chunks for quality
6. Generate expected output and save to `expected_output/`

**Why real PDFs?** Regression testing against a fixed corpus of real-world papers catches silent failures when extraction logic changes. Synthetic test data is not acceptable for production validation.
