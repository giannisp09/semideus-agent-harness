# Article Publishing Templates

Reusable snippets for `write-to-my-articles`.

## 1) Slug Generation

Use lowercase kebab-case:

```text
slug = title
  .toLowerCase()
  .replace(/[^a-z0-9]+/g, '-')
  .replace(/^-|-$/g, '')
```

Regex guard:

```text
^[a-z0-9]+(?:-[a-z0-9]+)*$
```

## 2) Minimal Blocks JSON Template

```json
[
  {
    "type": "heading",
    "level": 1,
    "text": "Article Title"
  },
  {
    "type": "text",
    "text": "Intro paragraph about the repository idea."
  },
  {
    "type": "heading",
    "level": 2,
    "text": "Architecture"
  },
  {
    "type": "bullet_list",
    "items": [
      { "text": "Core service/module 1" },
      { "text": "Core service/module 2" }
    ]
  },
  {
    "type": "image",
    "src": "https://gfzoopjhqhxjomjtxsyy.supabase.co/storage/v1/object/public/article-images/example.png",
    "alt": "Architecture diagram",
    "caption": "High-level architecture overview"
  }
]
```

## 3) Storage Upload (Local File -> Public URL)

Requirements:
- `SUPABASE_URL=https://gfzoopjhqhxjomjtxsyy.supabase.co`
- `SUPABASE_SERVICE_ROLE_KEY` present

Upload:

```bash
IMAGE_PATH="/absolute/path/to/architecture.png"
OBJECT_PATH="repo-articles/architecture-$(date +%s).png"

curl -sS -X POST \
  "${SUPABASE_URL}/storage/v1/object/article-images/${OBJECT_PATH}" \
  -H "Authorization: Bearer ${SUPABASE_SERVICE_ROLE_KEY}" \
  -H "apikey: ${SUPABASE_SERVICE_ROLE_KEY}" \
  -H "x-upsert: false" \
  -H "Content-Type: image/png" \
  --data-binary @"${IMAGE_PATH}"
```

Public URL:

```text
${SUPABASE_URL}/storage/v1/object/public/article-images/${OBJECT_PATH}
```

## 4) Slug Collision Check (execute_sql)

```sql
select id, slug
from public.articles
where slug = 'your-slug'
limit 1;
```

If collision exists, append numeric suffix (`-2`, `-3`) and re-check.

## 5) Insert Query Template (execute_sql)

Use dollar-quoted JSON to avoid escape issues:

```sql
insert into public.articles (
  slug,
  title,
  date,
  excerpt,
  cover_image,
  blocks,
  author_name,
  author_avatar,
  author_bio,
  published,
  category
)
values (
  'your-slug',
  'Your Article Title',
  '2026-03-18',
  'One to two sentence excerpt.',
  'https://gfzoopjhqhxjomjtxsyy.supabase.co/storage/v1/object/public/article-images/cover.png',
  $$[
    {"type":"heading","level":1,"text":"Your Article Title"},
    {"type":"text","text":"Opening paragraph."}
  ]$$::jsonb,
  'Author Name',
  null,
  null,
  true,
  'technical'
)
returning id, slug, published, cover_image, created_at;
```

## 6) Read-back Verification Query

```sql
select
  id,
  slug,
  title,
  published,
  cover_image,
  date,
  category,
  created_at,
  updated_at
from public.articles
where slug = 'your-slug'
limit 1;
```

## 7) Final User Report Template

```markdown
Article saved successfully.

- id: <uuid>
- slug: <slug>
- route: /articles/<slug>
- published: <true|false>
- cover_image: <public-url>
- inline_images:
  - <public-url-1>
  - <public-url-2>
```
