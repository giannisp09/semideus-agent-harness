---
name: write-to-my-articles
description: Generate repository-based technical articles, upload article images to Supabase Storage, and insert verified rows into public.articles. Use when the user asks to write/publish/save an article, upload cover or inline images, or persist article content to Supabase.
license: MIT
---

# Write To My Articles

Reusable workflow for drafting technical articles from a repository and publishing them into Supabase project `gfzoopjhqhxjomjtxsyy`.

## Purpose

Use this skill to produce one complete result:
1. Draft a high-quality technical article about the repository idea and implementation.
2. Upload provided image files to Supabase Storage bucket `article-images`.
3. Insert the article into `public.articles`.
4. Verify the inserted row and return publish details.

## When To Use

Apply this skill when user intent includes any of:
- "write article", "publish article", "save article", "insert article"
- "upload cover image/diagram/screenshot for article"
- "generate article from this repo/codebase and store in Supabase"

## Fixed Project Targets

- Supabase project ref: `gfzoopjhqhxjomjtxsyy`
- Supabase URL: `https://gfzoopjhqhxjomjtxsyy.supabase.co`
- Storage bucket: `article-images`
- Table: `public.articles`
- Required secret for writes: `SUPABASE_SERVICE_ROLE_KEY`

Do not silently switch projects. If runtime context points to a different project, stop and ask.

## Required Inputs

Minimum required:
- repository path to analyze
- article topic/title direction
- category (default `technical`)

Strongly recommended:
- local image files for cover and diagrams
- author name/avatar/bio
- publish mode (`published=true` by default unless user requests draft)

## Data Contract For `public.articles`

Populate at least:
- `slug` (lowercase kebab-case, unique)
- `title`
- `date` (`YYYY-MM-DD`)
- `excerpt`
- `cover_image` (public URL)
- `blocks` (JSON array with supported block types)
- `author_name`
- `published` (boolean)
- `category` (default `technical`)

If available, also set:
- `author_avatar`
- `author_bio`

## Supported Block Schema

Match renderer/editor expectations:
- heading: `{ "type": "heading", "level": 1..4, "text": "..." }`
- text: `{ "type": "text", "text": "..." }`
- bullet list: `{ "type": "bullet_list", "items": [{ "text": "..." }] }`
- numbered list: `{ "type": "numbered_list", "items": [{ "text": "..." }] }`
- image: `{ "type": "image", "src": "public-url", "alt": "required", "caption": "optional" }`

## End-to-End Workflow

Copy this checklist and complete in order:

```text
Progress:
- [ ] 1) Preflight checks
- [ ] 2) Repository analysis
- [ ] 3) Article drafting
- [ ] 4) Image upload + URL mapping
- [ ] 5) Payload validation
- [ ] 6) Insert into public.articles
- [ ] 7) Read-back verification
- [ ] 8) User-facing result bundle
```

### 1) Preflight checks

- Confirm target is project `gfzoopjhqhxjomjtxsyy`.
- Confirm `SUPABASE_SERVICE_ROLE_KEY` is available.
- Confirm bucket `article-images` exists or fail with actionable guidance.

### 2) Repository analysis

- Identify core architecture, modules, data flow, and standout implementation details.
- Prefer concrete code-backed claims over generic statements.
- Avoid claims that are not present in code.

### 3) Article drafting

- Write a technical narrative that explains:
  - idea/problem solved
  - architecture and major components
  - key implementation choices and tradeoffs
  - execution/deployment/testing notes if present
- Produce:
  - `title`
  - `slug` (auto-generated from title)
  - `excerpt` (1-2 sentences)
  - `blocks` array with coherent section flow

### 4) Image upload + URL mapping

- For each local image, upload to `article-images`.
- Store returned public URL.
- Map URLs:
  - hero image -> `cover_image`
  - inline images -> `image` blocks (`src`, `alt`, optional `caption`)
- Enforce non-empty alt text for every image block.

### 5) Payload validation

Before insert, validate:
- required fields non-empty (`title`, `slug`, `excerpt`, `blocks`, `author_name`)
- slug format: `^[a-z0-9]+(?:-[a-z0-9]+)*$`
- blocks is valid JSON array and only supported block shapes
- `published` is boolean
- `date` is `YYYY-MM-DD`
- `cover_image` is a valid URL

### 6) Insert into `public.articles`

- Prefer `execute_sql` for deterministic insertion and verification.
- Always perform slug collision check before insert.
- Use safe SQL quoting patterns; never concatenate unsanitized SQL.

### 7) Read-back verification

After insert:
- fetch by `slug`
- confirm row exists and fields persisted as expected
- return inserted `id`, `slug`, `published`, `cover_image`, and image URLs used in blocks

### 8) User-facing result bundle

Return concise delivery report:
- article `id`
- `slug` and final URL path (`/articles/<slug>`)
- publish state (`published` or `draft`)
- uploaded storage URLs
- any warnings (fallback defaults used, optional fields missing)

## Failure Playbook

- Slug already exists:
  - regenerate slug with deterministic suffix (for example `-2`, `-3`) and retry check.
- Storage upload fails with auth/permission:
  - verify service role key, bucket name, and storage policy; stop after actionable error message.
- Invalid `blocks` JSON:
  - repair shape to supported block schema and revalidate before insert.
- Missing required article fields:
  - stop and ask for missing required input instead of inserting partial invalid data.

## Validation Gates (Must Pass)

Do not run insert until every gate passes:
- Gate A: project URL includes `gfzoopjhqhxjomjtxsyy.supabase.co`
- Gate B: write credential present (`SUPABASE_SERVICE_ROLE_KEY`)
- Gate C: slug uniqueness check returns zero rows
- Gate D: `blocks` parses as JSON array and each block matches allowed schema
- Gate E: every `image` block has non-empty `src` and `alt`
- Gate F: read-back query after insert returns exactly one row

If any gate fails, stop, report the failing gate, and provide a concrete fix path.

## Quality Bar

- Favor precise engineering detail over marketing language.
- Keep paragraphs short and scannable.
- Ensure every major section is grounded in repository evidence.
- Do not fabricate metrics, traffic, or benchmark numbers.

## Additional Resources

- Query and payload templates: [TEMPLATES.md](TEMPLATES.md)
