# Pass 2 — Pointer Enrichment Design

## Overview

Two-pass Brain Mode pipeline for construction plan analysis:

- **Pass 1 (Sheet):** Gemini sees the full page PNG. Produces bounding boxes, sheet_reflection, master_index, cross_references, regionIndex per region. This is the map.
- **Pass 2 (Pointer):** Gemini sees the cropped PNG of one region, plus all Pass 1 context. Produces a rich structured markdown document for that specific pointer. This is reading each chapter.

Pass 1 divides attention across 12+ regions. Pass 2 focuses entirely on one region with full page context as background knowledge — reads every dimension, every note callout, every material spec.

---

## Pass 2 Input Package

What Gemini receives per pointer:

| Input | Source | Purpose |
|-------|--------|---------|
| **Cropped region PNG** | Generated from bbox + full page image | The primary visual input — Gemini stares at this |
| **Full page PNG** | Storage | Surrounding context — what's adjacent, what's connected |
| **sheet_info** | Pass 1 | Sheet number, title, discipline, scale, date |
| **sheet_reflection** | Pass 1 | Page-level superintendent summary |
| **This region's regionIndex** | Pass 1 | Gemini's own first impression from Pass 1 — materials, items, keynotes, dimensions, cross_refs |
| **master_index.keynotes** | Pass 1 | Full keynote list (details reference keynotes that live elsewhere on the sheet) |
| **cross_references** | Pass 1 | What other sheets relate to this page |
| **page_name** | DB | e.g. "A101 Floor Plan" |
| **discipline** | DB | e.g. "Architectural" |
| **region type + label** | Pass 1 | e.g. type="detail", label="WALL BASE DETAIL", detail_number="5" |

The key insight: Gemini already told you what it *thinks* is in this region during Pass 1 (the regionIndex). Pass 2 says "ok, look closer. Read everything. Write the real document."

---

## Pass 2 Output Schema

Dual format: a **markdown blob** (human-readable technical brief) and **structured fields** (machine-queryable for RAG/search).

### Universal Fields (every pointer gets these)

```json
{
  "content_markdown": "string — the full markdown document (see format below)",
  "materials": ["FRP panel", "1/2\" CDX plywood", "Composeal Gold 40 mil"],
  "dimensions": ["5.5\" curb height", "16\" O.C.", "4\" lap minimum"],
  "keynotes_referenced": [
    { "number": "B", "text": "Concrete curb height 5.5\"" },
    { "number": "7", "text": "Remove air curtain" }
  ],
  "specifications": [
    "Composeal Gold 40 mil waterproofing membrane",
    "FRP per finish schedule"
  ],
  "cross_references": [
    { "sheet": "A401", "detail": "2", "context": "head condition at same wall type" }
  ],
  "coordination_notes": [
    "Plumbing rough-in must complete before FRP installation",
    "Verify FRP adhesive compatibility with Composeal Gold"
  ],
  "questions_answered": [
    "How is the wall base waterproofed?",
    "What material is behind the FRP?",
    "What is the curb height at wet areas?"
  ]
}
```

### Optional Fields (by region type)

**Details (wall sections, sill details, head conditions, etc.):**
```json
{
  "assembly": [
    { "position": 1, "layer": "finish", "material": "FRP panel", "spec": "per finish schedule", "thickness": "1/16\"", "attachment": "adhesive" },
    { "position": 2, "layer": "substrate", "material": "1/2\" CDX plywood", "attachment": "adhesive + mechanical fastened to studs" },
    { "position": 3, "layer": "waterproofing", "material": "Composeal Gold 40 mil", "notes": "continuous, lap onto floor slab min 4\"" },
    { "position": 4, "layer": "structure", "material": "2x6 wood studs", "spacing": "16\" O.C." }
  ],
  "connections": [
    { "to": "floor slab", "condition": "membrane laps onto slab 4\" minimum" },
    { "to": "wall framing above", "condition": "continuous vapor barrier" }
  ]
}
```

**Plan views (floor plans, RCPs, site plans):**
```json
{
  "areas": [
    { "name": "kitchen", "notes": "new equipment layout per food service drawings" },
    { "name": "dining", "notes": "seating reconfigured, new finishes" },
    { "name": "drive-thru", "notes": "new Tormax sliding door system" }
  ],
  "equipment": [
    { "name": "Tormax sliding door", "location": "drive-thru window", "keynote": "1" },
    { "name": "POS counter", "location": "order point", "keynote": "5" }
  ],
  "modifications": [
    { "action": "install", "item": "Tormax sliding drive-thru door", "location": "drive-thru" },
    { "action": "demolish", "item": "existing service counter", "location": "dining" }
  ]
}
```

**Keynotes/Legend:**
```json
{
  "keynotes": [
    { "number": "1", "text": "NEW TORMAX SLIDING DRIVE-THRU DOOR" },
    { "number": "2", "text": "NEW WALK-UP WINDOW PER DETAIL 8/A401" },
    { "number": "3", "text": "EXISTING COLUMN TO BE BOXED WITH GYP. BD." }
  ],
  "symbol_definitions": [
    { "symbol": "triangle with number", "meaning": "detail reference marker" }
  ]
}
```

**Schedules (door, finish, equipment):**
```json
{
  "schedule_type": "door_schedule",
  "columns": ["mark", "width", "height", "type", "hardware_set", "notes"],
  "rows": [
    { "mark": "101", "width": "3'-0\"", "height": "7'-0\"", "type": "HM", "hardware_set": "1", "notes": "fire rated" }
  ]
}
```

**Notes (general notes, code notes):**
```json
{
  "note_categories": [
    {
      "category": "General",
      "notes": [
        "All dimensions to be verified in field prior to fabrication",
        "Contractor to coordinate all MEP rough-ins before wall close-in"
      ]
    },
    { "category": "Code", "notes": ["Comply with IBC 2021 Chapter 7 for fire-rated assemblies"] }
  ]
}
```

---

## Markdown Format (content_markdown)

The markdown blob should read like a technical brief you'd hand someone in the field. Format varies by region type:

### Detail Example

```markdown
## Detail 5 — Wall Base Detail
**Scale:** 1-1/2" = 1'-0"

Wall base assembly at wet areas showing waterproofing transition from wall to floor slab.

### Assembly (exterior to interior)
1. **FRP finish panel** — per finish schedule, adhesive applied
2. **1/2" CDX plywood substrate** — adhesive + mechanical fastened to studs
3. **Composeal Gold 40 mil waterproofing membrane** — continuous, lap onto floor slab minimum 4"
4. **2x6 wood studs @ 16" O.C.** — standard wood framing

### Key Dimensions
- Concrete curb height: 5.5" (per General Note B)
- Stud spacing: 16" O.C.
- Membrane lap onto slab: 4" minimum

### Coordination
- Plumbing rough-in must complete before FRP installation
- Verify FRP adhesive compatibility with Composeal Gold membrane
- See **A401 Detail 2** for head condition at same wall type
```

### Plan View Example

```markdown
## Proposed Floor Plan
**Scale:** 1/4" = 1'-0"

Primary floor plan showing kitchen, dining, service areas, and drive-thru modifications for the Chick-fil-A Love Field FSU renovation.

### Key Areas
- **Kitchen** — new equipment layout per food service drawings
- **Dining** — seating reconfigured, new wall finishes
- **Drive-thru** — new Tormax sliding door system at window

### Major Modifications
- INSTALL: Tormax sliding drive-thru door (Keynote 1)
- INSTALL: POS counter at order point (Keynote 5)
- DEMOLISH: Existing service counter in dining area
- PROTECT: Existing canopy structure during construction

### Referenced Keynotes
- **KN 1:** New Tormax sliding drive-thru door
- **KN 3:** Existing column to be boxed with gyp. bd.
- **KN 5:** New POS counter

### Coordination
- Electrical: coordinate power for Tormax door operator
- Food service: verify equipment clearances before framing
- See **A401, A402** for exterior detail conditions
```

### Keynotes Example

```markdown
## Key Notes

1. NEW TORMAX SLIDING DRIVE-THRU DOOR
2. NEW WALK-UP WINDOW PER DETAIL 8/A401
3. EXISTING COLUMN TO BE BOXED WITH GYP. BD.
4. NEW FRP WALL FINISH — SEE FINISH SCHEDULE
5. NEW POS COUNTER
...
```

---

## Prompt Design (Pass 2)

```
You are deeply analyzing a single region from a construction drawing. You have already seen the full sheet and identified this region during a first pass. Now focus exclusively on this cropped area and extract EVERYTHING.

## CONTEXT FROM PASS 1

Sheet: {sheet_info.number} — {sheet_info.title}
Discipline: {discipline}
Region: {region.type} — {region.label}
{if detail_number}: Detail Number: {region.detail_number}

Sheet Summary:
{sheet_reflection}

Your first impression of this region:
{region.regionIndex as formatted text}

Full keynote list from this sheet:
{master_index.keynotes}

Cross-referenced sheets:
{cross_references}

## YOUR TASK

Look at the cropped region image. Read EVERYTHING visible:
- Every line of text, every dimension string, every callout
- Every material indication (hatching patterns, labels, specs)
- Every connection point (how does this detail meet adjacent assemblies?)
- Every note, flag, or reference marker

Then produce two things:

### 1. content_markdown
Write a structured markdown technical brief for this region. A superintendent should be able to hand this to a subcontractor and they know exactly what to build.

{format guidance varies by region.type — see examples above}

### 2. Structured fields
Extract the same information as queryable data.

## OUTPUT JSON

{
  "content_markdown": "...",
  "materials": [...],
  "dimensions": [...],
  "keynotes_referenced": [...],
  "specifications": [...],
  "cross_references": [...],
  "coordination_notes": [...],
  "questions_answered": [...],
  // Include type-specific fields as applicable:
  // details: "assembly", "connections"
  // plans: "areas", "equipment", "modifications"
  // keynotes: "keynotes", "symbol_definitions"
  // schedules: "schedule_type", "columns", "rows"
  // notes: "note_categories"
}
```

---

## Pipeline Flow

```
Pass 1 completes for page
          |
          v
For each region in page.regions:
  1. Crop region PNG from full page image using bbox
  2. Build Pass 2 input package (cropped PNG + Pass 1 context)
  3. Call Gemini with Pass 2 prompt
  4. Parse response → content_markdown + structured fields
  5. Save to pointer row:
     - description = content_markdown
     - structured fields → new JSONB column or embedded in description
  6. Generate embedding from content_markdown (Voyage AI)
          |
          v
Pointer enrichment complete — enrichment_status = 'complete'
```

### Processing Notes

- Pass 2 runs as a **background worker** after Pass 1 completes
- Can be parallelized (multiple pointers from same page concurrently) but watch rate limits
- Retry logic: if a pointer fails, mark `enrichment_status = 'failed'` and continue
- The cropped PNGs should be stored (pointer `png_path`) for future re-processing
- Pass 2 is idempotent — can re-run with updated prompts without touching Pass 1 data

---

## Database Changes

Add to the `pointers` table (or a new `pointer_enrichment` table):

```sql
-- Option B: separate enrichment table (cleaner for versioning/re-runs)
CREATE TABLE pointer_enrichments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pointer_id UUID NOT NULL REFERENCES pointers(id) ON DELETE CASCADE,
    prompt_version INTEGER NOT NULL,
    content_markdown TEXT NOT NULL,
    structured_fields JSONB NOT NULL DEFAULT '{}',
    processing_time_ms INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(pointer_id, prompt_version)
);
```

Option B is better for the tuner workflow — you can re-run Pass 2 with different prompts and compare results without overwriting previous enrichments.

---

## Integration with Brain Mode Tuner

The tuner already has:
- PDF scanning + page rendering (`pdf_processor.py`)
- Gemini service with agentic vision (`gemini_service.py`)
- Prompt versioning + A/B comparison (`database.py`)
- Batch processing with background worker (`main.py`)

To add Pass 2:

1. **New function in `gemini_service.py`:** `analyze_pointer_pass2(cropped_png, full_page_png, pass1_context, prompt)`
2. **New prompt file:** `prompts/pointer_enrichment_v1.txt`
3. **New endpoints in `main.py`:**
   - `POST /api/enrich/{page_id}` — trigger Pass 2 for all pointers on a page
   - `POST /api/enrich/pointer/{pointer_id}` — trigger Pass 2 for single pointer
   - `GET /api/enrichments/{pointer_id}` — get enrichment results
4. **New table in `database.py`:** `pointer_enrichments`
5. **Cropping utility:** take full page PNG + bbox → cropped region PNG
6. **Frontend:** new tab/view in the tuner to inspect + compare Pass 2 results per pointer
