# Complex Text Support Implementation

## Overview
This document describes the implementation of support for complex text structures in the Talmudpedia backend, following the Sefaria API schema documentation.

## Changes Made

### 1. Tree Builder (`app/services/library/tree_builder.py`)

#### Added Support for Complex Schemas
- **`process_jagged_array_node()`**: Extracts content from JaggedArrayNode structures
- **`process_complex_node()`**: Recursively processes complex schema trees with nested SchemaNodes
- **Shared Titles (Terms) Support**:
  - `fetch_term()`: Fetches shared title translations from Sefaria API
  - `collect_shared_titles_from_node()`: Recursively collects all shared titles from schemas
  - `prefetch_shared_titles()`: Pre-fetches all terms before processing schemas
  - `terms_cache`: Caches term translations for performance

#### Refactored Processing Flow
1. Fetch all book details concurrently
2. Pre-fetch all shared titles (Terms) from schemas
3. Process all book schemas with terms available in cache

#### Schema Processing
The tree builder now handles:
- **Simple texts**: Single JaggedArrayNode (e.g., Genesis)
- **Complex texts with default nodes**: SchemaNode with default content and named sections (e.g., books with Introduction/Conclusion)
- **Multi-level complex texts**: Nested SchemaNodes (e.g., Abarbanel on Torah with per-book introductions)

### 2. Text Endpoint (`app/endpoints/texts.py`)

#### Enhanced Reference Parsing
- **Updated `ReferenceNavigator.parse_ref()`**: Now handles multi-part titles and complex references
  - Supports references like "Abarbanel on Torah, Genesis 1:2"
  - Supports references like "Shulchan Arukh, Orach Chaim 1:2"
  - Maintains backward compatibility with simple references

#### New ComplexTextNavigator Class
- **`navigate_to_section()`**: Navigates through complex text structures to find content
  - Handles dictionary-based structures (complex texts)
  - Handles list-based structures (simple texts)
  - Supports nested section navigation
  
- **`_navigate_complex_structure()`**: Helper for dictionary-based navigation

#### Updated get_source_text Endpoint
- Now uses `ComplexTextNavigator` for content extraction
- Handles both simple and complex references
- For complex references (with commas), returns single page with proper highlighting
- For simple references, maintains existing pagination logic
- Robust error handling for missing content

## Text Structure Examples

### Simple Text (Genesis)
```json
{
  "title": "Genesis",
  "chapter": [
    ["Verse 1:1", "Verse 1:2", ...],  // Chapter 1
    ["Verse 2:1", "Verse 2:2", ...],  // Chapter 2
    ...
  ]
}
```

### Complex Text with Sections (Example Book)
```json
{
  "title": "Example Book",
  "chapter": {
    "Introduction": ["Intro Paragraph 1", "Intro Paragraph 2", ...],
    "default": [
      ["Chapter 1, Section 1", "Chapter 1, Section 2"],
      ["Chapter 2, Section 1", "Chapter 2, Section 2"],
      ...
    ],
    "Conclusion": ["Conclusion Paragraph 1", "Conclusion Paragraph 2", ...]
  }
}
```

### Multi-Level Complex Text (Abarbanel on Torah)
```json
{
  "title": "Abarbanel on Torah",
  "chapter": {
    "Genesis": {
      "Introduction": ["Intro Paragraph 1", ...],
      "default": [
        [["Comment on 1:1, Para 1", ...], ...],  // Chapter 1
        ...
      ]
    },
    "Exodus": {
      "Introduction": ["Intro Paragraph 1", ...],
      "default": [...]
    },
    ...
  }
}
```

## Reference Examples

### Simple References
- `"Genesis 1:2"` → Chapter 1, Verse 2
- `"Berakhot 2a"` → Daf 2a
- `"Shulchan Arukh, Orach Chaim 1"` → Orach Chaim, Chapter 1

### Complex References
- `"Abarbanel on Torah, Genesis 1:2"` → Genesis section, Chapter 1, Verse 2
- `"Abarbanel on Torah, Genesis, Introduction 5"` → Genesis Introduction, Paragraph 5

## API Usage

### Fetching a Simple Text
```
GET /api/source/Genesis%201:2
```

### Fetching a Complex Text
```
GET /api/source/Abarbanel%20on%20Torah,%20Genesis%201:2
```

### With Pagination
```
GET /api/source/Genesis%201:2?pages_before=1&pages_after=2
```

## Database Structure

The implementation assumes your MongoDB database mirrors Sefaria's structure:
- **texts collection**: Contains text content with `chapter` field
- **index collection**: Contains metadata including `heTitle`

## Future Improvements

1. **Pagination for Complex Texts**: Currently, complex references return a single page. Could implement section-aware pagination.
2. **Term Caching**: Consider persisting the terms cache to avoid repeated API calls.
3. **Best Version Selection**: Integrate with the tree's `bestVersion` field for automatic version selection.
4. **Error Messages**: Provide more specific error messages for different failure modes.

## Testing

To test complex text support:

1. Run the tree builder to generate the updated tree:
   ```bash
   cd backend
   python3 app/services/library/tree_builder.py
   ```

2. Test simple references:
   ```bash
   curl "http://localhost:8000/api/source/Genesis%201:2"
   ```

3. Test complex references:
   ```bash
   curl "http://localhost:8000/api/source/Abarbanel%20on%20Torah,%20Genesis%201:2"
   ```

## Notes

- The implementation handles both the old simple structure and the new complex structure
- Backward compatibility is maintained for all existing simple text references
- The code gracefully falls back to simple navigation when complex navigation isn't needed
