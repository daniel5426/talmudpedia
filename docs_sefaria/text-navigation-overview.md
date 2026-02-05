# Text Navigation Overview

## Data Sources
- Mongo collections: `texts` (content and chapter arrays), `index` (schemas and metadata).
- Library menu: generated from Sefaria TOC via `tree_builder.py` into `sefaria_tree.json` and `backend/library_chunks/*.json`.

## API Surface
- `GET /api/source/{ref}`: primary fetch with optional `pages_before` and `pages_after`.
- `GET /api/texts/{ref}`: raw document lookup (by exact or case-insensitive title).

## Navigation Modes
- Simple (chapter/verse): references parsed to `index_title`, `chapter`, optional `verse`. Pagination scans `chapter` array, skipping empty slots, and returns page lists with highlighting when verse is present.
- Talmud (daf/amud): no custom offsets; array index 0 → 1a, 1 → 1b, etc. Page content is `chapter[daf_index]` flattened; empty pages skipped. Next/previous pages are chosen by scanning array for the next non-empty slot.
- Complex schema texts: `ComplexTextNavigator.navigate_to_section` walks the index schema to locate content. Returns either multi-page (complex) or single-page payloads depending on structure and pagination parameters. Jagged arrays whose `addressTypes` include `Talmud` accept daf tokens like `12a/12b` with optional line tokens separated by space or colon when navigating through the complex path. When a complex schema has a default Talmud node, chapter-style refs (e.g., `:2`) are reinterpreted to daf (`2a`), and depth-1 sections (e.g., Introductions) paginate into the first non-empty daf from the default content.

## Payload Shapes
- Simple/multi-page response: `{ pages: [{ ref, he_ref, segments, highlight_index, highlight_indices }], main_page_index, index_title, he_title, he_ref, version_title, language, can_load_more }`.
- Single-page response is normalized into the same multi-page shape when needed.

## Parsing Helpers
- `ReferenceNavigator.parse_ref`: extracts index title and numeric parts (chapter/verse or daf/side/line).
- Ref reconstruction: `get_ref_from_index` and `get_ref_from_linear` map array indices back to refs.
- Hebrew refs: `_build_he_ref` composes book Hebrew title with daf/chapter numerals.
- Flattening: `_flatten_segments` flattens nested lists and drops empty strings before returning segments.

## Pagination Behavior
- `pages_before/pages_after` drive window size; scanning stops at empty slots.
- Range queries use `parse_range_ref` and `is_in_range` to mark highlights across requested ranges.
- For Talmud, next/previous is derived purely from the `chapter` array order; missing dapim remain absent.

## Library Menu Construction
- `tree_builder.py` pulls schemas and version metadata, prefetches terms, and builds chunked menus.
- Talmud children skip empty amudim using `content_counts`, including nested lists of counts, so only populated dapim appear in menus.

## Known Edge Handling
- If a book starts mid-masechet or has gaps, missing pages simply stay absent; navigation uses the array as-is. Depth-1 sections that precede a Talmud default will fall through to the first populated daf when next-section traversal yields nothing.
- Complex texts with `force_single_page` or raw ranges return single pages with appropriate highlighting.

