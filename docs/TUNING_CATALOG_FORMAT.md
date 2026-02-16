# Tuning Catalog Format (v3.4)

This file describes the Script Catalog data layout used by `Pekat Tuning`.

## Storage tree

```text
resources/code_modules/
  scripts_raw/
  scripts_utf8/
  pmodule/
  catalog.json
  categories.json
```

## `catalog.json` schema

Top-level:
- `schema_version`
- `generated_at`
- `items` (array)

Each item fields:
- `id`
- `name`
- `source_filename`
- `storage_path_utf8`
- `storage_path_raw`
- `format` (`txt|py|pmodule`)
- `category`
- `tags`
- `short_description`
- `encoding_source`
- `size_bytes`
- `sha256`
- `created_at`
- `updated_at`
- `empty`

## Import rules
- Accept `.txt`, `.py`, `.pmodule`.
- Text decode order:
  1) `utf-8-sig`
  2) `utf-8`
  3) `cp1250`
  4) `latin1`
- Canonical UTF-8 copy is used for preview and clipboard copy.
- Raw source is preserved for traceability.

