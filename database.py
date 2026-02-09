"""SQLite database for Brain Mode Tuner."""

import aiosqlite
import json
from datetime import datetime
from pathlib import Path
from config import get_settings

settings = get_settings()
DB_PATH = settings.db_path


async def init_db():
    """Initialize the database with required tables."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Pages table - stores discovered PDF pages
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pdf_path TEXT NOT NULL,
                page_number INTEGER NOT NULL,
                page_name TEXT,
                discipline TEXT,
                thumbnail_path TEXT,
                image_path TEXT,
                width INTEGER,
                height INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(pdf_path, page_number)
            )
        """)
        
        # Pointer enrichments table - stores Pass 2 results per region
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pointer_enrichments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                result_id INTEGER NOT NULL,
                region_index INTEGER NOT NULL,
                region_id TEXT,
                prompt_version INTEGER NOT NULL DEFAULT 1,
                content_markdown TEXT NOT NULL,
                structured_fields TEXT NOT NULL DEFAULT '{}',
                cropped_png_path TEXT,
                processing_time_ms INTEGER,
                status TEXT DEFAULT 'complete',
                error_message TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (result_id) REFERENCES results(id),
                UNIQUE(result_id, region_index, prompt_version)
            )
        """)
        
        # Results table - stores Brain Mode processing results
        await db.execute("""
            CREATE TABLE IF NOT EXISTS results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                page_id INTEGER NOT NULL,
                prompt_version_id INTEGER,
                page_type TEXT,
                discipline TEXT,
                regions TEXT,
                sheet_reflection TEXT,
                cross_references TEXT,
                raw_response TEXT,
                processing_time_ms INTEGER,
                success INTEGER DEFAULT 1,
                error_message TEXT,
                verification_status TEXT DEFAULT 'pending',
                verification_result TEXT,
                corrected_regions TEXT,
                original_regions TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (page_id) REFERENCES pages(id),
                FOREIGN KEY (prompt_version_id) REFERENCES prompt_versions(id)
            )
        """)

        # Add verification columns to existing results table if they don't exist
        try:
            await db.execute("ALTER TABLE results ADD COLUMN verification_status TEXT DEFAULT 'pending'")
        except:
            pass  # Column already exists
        try:
            await db.execute("ALTER TABLE results ADD COLUMN verification_result TEXT")
        except:
            pass  # Column already exists
        try:
            await db.execute("ALTER TABLE results ADD COLUMN corrected_regions TEXT")
        except:
            pass  # Column already exists
        try:
            await db.execute("ALTER TABLE results ADD COLUMN original_regions TEXT")
        except:
            pass  # Column already exists
        
        # Prompt versions table - stores different prompt versions for tuning
        await db.execute("""
            CREATE TABLE IF NOT EXISTS prompt_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                prompt_text TEXT NOT NULL,
                is_active INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Insert default prompt if not exists
        cursor = await db.execute("SELECT COUNT(*) FROM prompt_versions")
        count = (await cursor.fetchone())[0]
        if count == 0:
            await db.execute("""
                INSERT INTO prompt_versions (name, prompt_text, is_active)
                VALUES (?, ?, ?)
            """, ("default", get_default_prompt(), 1))
        
        await db.commit()


def get_default_prompt() -> str:
    """Return the default Brain Mode prompt - RAG-optimized for query-time retrieval."""
    return '''You are analyzing a construction drawing for a superintendent. Your job is to DEEPLY COMPREHEND this sheet and create a SEARCHABLE INDEX.

## STEP 1: VISUAL SCAN (Do this first!)

Before extracting anything, systematically scan the ENTIRE sheet:

### 1.1 Find ALL Regions
Scan the sheet and create bounding boxes for every distinct region. Common region types include:

- **Details** — Numbered details (1, 2, 3... or 1/A401) with drawing content and title
- **Key Notes / Keynotes** — Numbered list of notes (often upper right)
- **Legend** — Symbol definitions, line types, abbreviations
- **General Notes** — Text blocks with construction notes
- **Title Block** — Sheet number, title, date, firm info (usually right edge)
- **Revision Block** — Revision history table
- **Plan Views** — Floor plans, site plans, roof plans
- **Schedules** — Tables (door schedule, finish schedule, etc.)
- **Sections / Elevations** — Building sections, exterior/interior elevations

Not every sheet has all of these. Detect what's actually there.

### 1.2 Find ALL Details Specifically
Look for EVERY detail on the sheet. Details have:
- A detail NUMBER (in a circle, hexagon, or flag: ①, 5, 2/A401)
- A TITLE below or beside it ("WALL DETAIL", "SILL DETAIL")
- A SCALE notation
- The drawing CONTENT (the actual construction drawing)

**COUNT the details.** If you see 8 detail numbers, you must create 8 detail regions. Don't skip any.

**BOUNDING BOX ACCURACY:**
- Include the detail number, title, scale, AND drawing content in the bbox
- The bbox should contain ALL the content for that detail
- Don't cut details in half — if content extends further, expand the bbox

### 1.2 Read ALL Text
Scan for every piece of text on the sheet:
- Title block (sheet number, title, date, scale)
- Detail titles and scales
- Keynotes and callout numbers
- Dimensions (every dimension string you can read)
- Notes sections (general notes, code notes, specifications)
- Material callouts and tags
- Grid lines and column markers
- Room names and area labels

### 1.3 Identify Visual Elements
Look for:
- Hatching patterns (indicate materials - concrete, insulation, earth, etc.)
- Line weights (heavy = cut lines, light = beyond)
- Symbols (north arrows, section cuts, detail markers, door/window tags)
- Leaders and arrows pointing to specific items

### 1.4 Trace Cross-References
Find every reference to other sheets:
- "SEE DETAIL 3/A401"
- "REFER TO STRUCTURAL"
- Section cut symbols pointing to other sheets
- Door/window tags referencing schedules

## STEP 2: EXTRACT EVERYTHING

Now extract what you found. Be EXHAUSTIVE. If you can read it, include it.

### For EACH Detail Found:
- Detail number (exactly as shown: "1", "2/A301", "A", etc.)
- Title (exactly as written)
- Scale
- What it shows (describe the construction assembly)
- Materials visible (concrete, steel, wood, insulation, membrane, etc.)
- Key dimensions (list them all)
- Keynotes within this detail
- References to other details/sheets

### For the Overall Sheet:
- Every keynote with its full text
- Every room/area name visible
- Every material specification mentioned
- Every dimension you can read
- Every cross-reference to other sheets

## CRITICAL: COMPLETENESS CHECK
Before outputting, verify:

**REGION CHECK:**
- Did I detect every distinct region on this sheet?
- If there are numbered details, did I get ALL of them? (Count to verify)
- Did I catch the keynotes, legend, and general notes if they exist?
- Did I include the title block?

**BOUNDING BOX CHECK:**
- Does each bbox fully contain its region (not cutting off content)?
- Is the detail title included in each detail's bbox?

**CONTENT CHECK:**
- Did I read the keynotes?
- Did I note cross-references to other sheets?

## STEP 3: BUILD HIERARCHICAL INDEX

Your output will power RAG retrieval. The structure is DETAIL-CENTRIC:

1. **Each detected region gets its own mini-index** — What's IN that detail/area
2. **Master index aggregates from all details** — Sheet-level searchability

When a superintendent asks "show me detail 3" or "what's the flashing detail?" — your index must match.

## OUTPUT STRUCTURE

Return JSON with this structure:

{
  "page_type": "floor_plan|detail_sheet|schedule|section|elevation|notes|cover|rcp|demo",
  "discipline": "architectural|structural|mechanical|electrical|plumbing|civil|kitchen|canopy",
  
  "sheet_info": {
    "number": "A002",
    "title": "DEMOLITION RCP",
    "full_title": "A002 - DEMOLITION RCP",
    "scale": "1/4\" = 1'-0\"",
    "date": "03.27.2025"
  },
  
  "index": {
    "keywords": [
      "demolition", "RCP", "reflected ceiling plan", "ceiling", 
      "air curtain", "canopy", "ACT", "acoustic ceiling tile"
    ],
    
    "areas_shown": [
      {"name": "kitchen", "notes": "ceiling demolition area"},
      {"name": "dining", "notes": "ACT ceiling to be removed"}
    ],
    
    "items": [
      {
        "name": "air curtain",
        "action": "demolish",
        "location": "entry door",
        "keynote": "7",
        "details": "remove existing air curtain at entry"
      }
    ],
    
    "keynotes": [
      {"number": "1", "text": "Existing ACT ceiling to be removed"},
      {"number": "7", "text": "Remove air curtain"}
    ],
    
    "dimensions": ["14'-0\"", "21'-6\""],
    
    "specifications": [
      "ACT ceiling: remove in shaded areas"
    ],
    
    "cross_references": [
      {"sheet": "A201", "context": "new RCP configuration"},
      {"sheet": "A301", "context": "exterior elevations"}
    ]
  },
  
  "regions": [
    {
      "id": "region_floor_plan",
      "type": "detail",
      "detail_number": "1",
      "label": "PROPOSED FLOOR PLAN",
      "bbox": {"x0": 110, "y0": 510, "x1": 810, "y1": 960},
      "confidence": 0.98,
      "scale": "1/4\" = 1'-0\"",
      "shows": "Complete floor plan showing kitchen, dining, service areas, drive-thru modifications",
      "region_index": {
        "areas": ["kitchen", "dining", "hallway", "restrooms", "service yard", "catering area"],
        "items": [
          {"name": "Tormax sliding door", "action": "install", "keynote": "1"},
          {"name": "POS counter", "action": "install", "keynote": "5"}
        ],
        "materials": [],
        "keynotes_shown": ["1", "3", "5", "8", "11", "14", "15", "21", "28"],
        "dimensions": ["17'-6 1/2\"", "26'-0\"", "42'-0\""],
        "cross_refs": ["A401", "A402", "A601"]
      }
    },
    {
      "id": "region_wall_detail",
      "type": "detail",
      "detail_number": "5",
      "label": "WALL DETAIL",
      "bbox": {"x0": 60, "y0": 240, "x1": 280, "y1": 465},
      "confidence": 0.95,
      "scale": "1-1/2\" = 1'-0\"",
      "shows": "Wall section showing FRP finish, waterproofing membrane, and base assembly",
      "region_index": {
        "areas": [],
        "items": [{"name": "waterproof membrane", "action": "install"}],
        "materials": ["FRP", "Composeal Gold 40 mil", "1/2\" CDX plywood", "2x studs @ 16\" O.C."],
        "keynotes_shown": [],
        "dimensions": ["1/2\" plywood", "16\" O.C."],
        "cross_refs": []
      }
    },
    {
      "id": "region_keynotes",
      "type": "legend",
      "label": "KEY NOTES",
      "bbox": {"x0": 740, "y0": 35, "x1": 895, "y1": 245},
      "confidence": 0.99,
      "region_index": {
        "keynotes": [
          {"number": "1", "text": "NEW TORMAX SLIDING DRIVE-THRU DOOR"},
          {"number": "3", "text": "EXISTING COLUMN TO BE BOXED WITH GYP. BD."}
        ]
      }
    },
    {
      "id": "region_title_block",
      "type": "title_block",
      "label": "TITLE BLOCK",
      "bbox": {"x0": 915, "y0": 20, "x1": 995, "y1": 980},
      "confidence": 0.99
    }
  ],
  
  "questions_this_sheet_answers": [
    "What ceiling work is being demolished?",
    "Where is the air curtain located?",
    "What needs to be protected during demolition?",
    "What keynotes are on the demo RCP?"
  ],
  
  "sheet_reflection": "Demo RCP showing ceiling elements to remove (ACT in dining/kitchen) and protect (canopies). Key coordination: electrical fixtures in demo zones. See A201 for new configuration.",
  
  "cross_references": ["A201", "A301"]
}

## GUIDELINES

### REGIONS: The Foundation of Comprehension
Every detected area becomes a region with its OWN mini-index (`region_index`).

For EACH region, include:
- **id**: Unique identifier (e.g., "region_floor_plan", "region_wall_detail")
- **type**: "detail" | "legend" | "notes" | "title_block" | "schedule"
- **detail_number**: If it's a numbered detail ("1", "5", "2/A301")
- **label**: The title text shown on the drawing
- **bbox**: Bounding box coordinates (0-1000 normalized)
- **scale**: Scale for this detail/view (if shown)
- **shows**: What this region illustrates (1-2 sentences)
- **region_index**: Mini-index of what's IN this region:
  - `areas`: Rooms/spaces shown in this region
  - `items`: Equipment/elements with actions
  - `materials`: Specific materials called out
  - `keynotes_shown`: Which keynotes appear here
  - `dimensions`: Dimensions readable in this region
  - `cross_refs`: Sheet references from this region

**If you see 8 detail bubbles, you MUST have 8 regions with type "detail".**

### MASTER INDEX: Built from Regions
The top-level `index` object AGGREGATES from all region_indexes:
- Combine all keywords from all regions
- Combine all items from all regions  
- Combine all materials from all regions
- List all keynotes (from the keynotes legend region)
- Aggregate all cross-references with context

This creates a hierarchical search structure:
- Search "wall detail" → finds region_wall_detail
- Search "FRP" → finds it in region_wall_detail.region_index.materials
- Search "keynote 5" → finds it in master index AND which regions reference it

### Keywords
Extract EVERY searchable term:
- Equipment names (air curtain, RTU, VAV box, diffuser)
- Materials (ACT, gypsum board, CMU, concrete, TPO, EPDM, flashing)
- Actions (demolish, remove, protect, relocate, install, verify)
- Drawing types (RCP, floor plan, section, detail, wall section, sill detail)
- Abbreviations AND full names (RCP = reflected ceiling plan, GWB = gypsum wall board)
- Detail titles (use the exact titles as keywords)

### Items
For each significant item shown:
- What is it? (name)
- What's happening to it? (action: demolish/install/protect/relocate/verify)
- Where on the sheet? (location/area)
- Any keynote or callout number?
- Relevant details

### Areas Shown
List every room/area visible with notes about what's shown there:
- Kitchen, dining, hallway, restrooms, office
- Service yard, drive-thru, patio, walk-in cooler/freezer

### Cross References
Include context for each reference:
- "A201" → {"sheet": "A201", "context": "new RCP showing final ceiling configuration"}
- "2/A401" → {"sheet": "A401", "context": "detail 2 showing sill condition"}

### Questions This Sheet Answers
Pre-generate 5-8 natural questions based on WHAT'S ACTUALLY ON THE SHEET:
- "What does detail 1 show?"
- "How is the storefront head flashed?"
- "What's the roof assembly?"
- "Where is the vapor barrier?"

### Sheet Reflection (superintendent_summary)
2-3 sentences maximum. Focus on:
- What does this sheet tell me to DO?
- What coordination is needed?
- What's the key takeaway for the field?

### Regions (with bounding boxes)
Create a region for EACH distinct area:
- Each detail gets its own region with type "detail"
- Include the detail_number in the region
- Notes sections, legends, title blocks get their own regions

## BOUNDING BOX FORMAT
Use 0-1000 normalized coordinates where (0,0) is top-left and (1000,1000) is bottom-right.
'''


async def get_active_prompt() -> tuple[int, str]:
    """Get the active prompt version."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT id, prompt_text FROM prompt_versions WHERE is_active = 1 LIMIT 1"
        )
        row = await cursor.fetchone()
        if row:
            return row[0], row[1]
        # Fallback to default
        return 0, get_default_prompt()


async def save_prompt_version(name: str, prompt_text: str, set_active: bool = False) -> int:
    """Save a new prompt version."""
    async with aiosqlite.connect(DB_PATH) as db:
        if set_active:
            await db.execute("UPDATE prompt_versions SET is_active = 0")
        
        cursor = await db.execute(
            "INSERT INTO prompt_versions (name, prompt_text, is_active) VALUES (?, ?, ?)",
            (name, prompt_text, 1 if set_active else 0)
        )
        await db.commit()
        return cursor.lastrowid


async def get_prompt_versions() -> list[dict]:
    """Get all prompt versions."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, name, is_active, created_at FROM prompt_versions ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_prompt_by_id(prompt_id: int) -> dict | None:
    """Get a specific prompt version."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM prompt_versions WHERE id = ?", (prompt_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def set_active_prompt(prompt_id: int):
    """Set a prompt version as active."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE prompt_versions SET is_active = 0")
        await db.execute("UPDATE prompt_versions SET is_active = 1 WHERE id = ?", (prompt_id,))
        await db.commit()


async def save_page(pdf_path: str, page_number: int, page_name: str, 
                    discipline: str, thumbnail_path: str, image_path: str,
                    width: int, height: int) -> int:
    """Save a page to the database."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            INSERT OR REPLACE INTO pages 
            (pdf_path, page_number, page_name, discipline, thumbnail_path, image_path, width, height)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (pdf_path, page_number, page_name, discipline, thumbnail_path, image_path, width, height))
        await db.commit()
        
        # Get the ID
        cursor = await db.execute(
            "SELECT id FROM pages WHERE pdf_path = ? AND page_number = ?",
            (pdf_path, page_number)
        )
        row = await cursor.fetchone()
        return row[0] if row else cursor.lastrowid


async def get_pages(discipline: str = None, processed: bool = None, 
                    limit: int = 100, offset: int = 0) -> list[dict]:
    """Get pages with optional filters."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        query = "SELECT p.*, (SELECT COUNT(*) FROM results r WHERE r.page_id = p.id) as result_count FROM pages p WHERE 1=1"
        params = []
        
        if discipline:
            query += " AND p.discipline = ?"
            params.append(discipline)
        
        if processed is not None:
            if processed:
                query += " AND (SELECT COUNT(*) FROM results r WHERE r.page_id = p.id) > 0"
            else:
                query += " AND (SELECT COUNT(*) FROM results r WHERE r.page_id = p.id) = 0"
        
        query += " ORDER BY p.discipline, p.page_name LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_page_by_id(page_id: int) -> dict | None:
    """Get a single page by ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM pages WHERE id = ?", (page_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_disciplines() -> list[dict]:
    """Get all disciplines with page counts."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT 
                discipline,
                COUNT(*) as page_count,
                SUM(CASE WHEN (SELECT COUNT(*) FROM results r WHERE r.page_id = p.id) > 0 THEN 1 ELSE 0 END) as processed_count
            FROM pages p
            GROUP BY discipline
            ORDER BY discipline
        """)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def save_result(page_id: int, prompt_version_id: int, result: dict, 
                      processing_time_ms: int, success: bool = True, 
                      error_message: str = None) -> int:
    """Save a processing result."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO results 
            (page_id, prompt_version_id, page_type, discipline, regions, 
             sheet_reflection, cross_references, raw_response, 
             processing_time_ms, success, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            page_id,
            prompt_version_id,
            result.get("page_type") if success else None,
            result.get("discipline") if success else None,
            json.dumps(result.get("regions", [])) if success else None,
            result.get("sheet_reflection") if success else None,
            json.dumps(result.get("cross_references", [])) if success else None,
            json.dumps(result) if success else None,
            processing_time_ms,
            1 if success else 0,
            error_message
        ))
        await db.commit()
        return cursor.lastrowid


async def get_results_for_page(page_id: int) -> list[dict]:
    """Get all results for a page."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT r.*, pv.name as prompt_name
            FROM results r
            LEFT JOIN prompt_versions pv ON r.prompt_version_id = pv.id
            WHERE r.page_id = ?
            ORDER BY r.created_at DESC
        """, (page_id,))
        rows = await cursor.fetchall()
        results = []
        for row in rows:
            result = dict(row)
            if result.get("regions"):
                result["regions"] = json.loads(result["regions"])
            if result.get("cross_references"):
                result["cross_references"] = json.loads(result["cross_references"])
            if result.get("raw_response"):
                result["raw_response"] = json.loads(result["raw_response"])
            results.append(result)
        return results


async def get_latest_result_for_page(page_id: int) -> dict | None:
    """Get the latest result for a page."""
    results = await get_results_for_page(page_id)
    return results[0] if results else None


async def save_verification_result(
    result_id: int,
    verification_status: str,
    verification_result: dict,
    corrected_regions: list | None = None
) -> None:
    """Save verification result for a processing result."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE results
            SET verification_status = ?,
                verification_result = ?,
                corrected_regions = ?
            WHERE id = ?
        """, (
            verification_status,
            json.dumps(verification_result),
            json.dumps(corrected_regions) if corrected_regions else None,
            result_id
        ))
        await db.commit()


async def apply_corrected_regions(result_id: int) -> bool:
    """Apply corrected regions from verification to the result's regions.
    Stores original regions in 'original_regions' for revert capability."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT regions, corrected_regions FROM results WHERE id = ?", (result_id,)
        )
        row = await cursor.fetchone()

        if not row or not row["corrected_regions"]:
            return False

        original = row["regions"]  # Save current regions for revert
        corrected = json.loads(row["corrected_regions"])

        # Update the regions with corrected ones, store original for revert
        await db.execute("""
            UPDATE results
            SET regions = ?,
                original_regions = ?,
                verification_status = 'green'
            WHERE id = ?
        """, (json.dumps(corrected), original, result_id))
        await db.commit()
        return True


async def revert_to_original_regions(result_id: int) -> bool:
    """Revert regions back to original (before correction was applied)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT original_regions FROM results WHERE id = ?", (result_id,)
        )
        row = await cursor.fetchone()

        if not row or not row["original_regions"]:
            return False

        original = row["original_regions"]

        # Restore original regions, reset verification status
        await db.execute("""
            UPDATE results
            SET regions = ?,
                original_regions = NULL,
                verification_status = 'pending'
            WHERE id = ?
        """, (original, result_id))
        await db.commit()
        return True


async def get_unverified_results(limit: int = 100) -> list[dict]:
    """Get results that have been processed but not verified."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT r.*, p.page_name, p.discipline as page_discipline, p.pdf_path, p.page_number,
                   p.width, p.height, p.image_path
            FROM results r
            JOIN pages p ON r.page_id = p.id
            WHERE r.success = 1
              AND (r.verification_status = 'pending' OR r.verification_status IS NULL)
            ORDER BY r.created_at DESC
            LIMIT ?
        """, (limit,))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_result_by_id(result_id: int) -> dict | None:
    """Get a single result by ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM results WHERE id = ?", (result_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        result = dict(row)
        if result.get("regions"):
            result["regions"] = json.loads(result["regions"])
        if result.get("cross_references"):
            result["cross_references"] = json.loads(result["cross_references"])
        if result.get("raw_response"):
            result["raw_response"] = json.loads(result["raw_response"])
        if result.get("verification_result"):
            result["verification_result"] = json.loads(result["verification_result"])
        if result.get("corrected_regions"):
            result["corrected_regions"] = json.loads(result["corrected_regions"])
        return result


async def update_regions(result_id: int, regions: list) -> None:
    """Update regions for a result (manual bbox editing)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE results
            SET regions = ?
            WHERE id = ?
        """, (json.dumps(regions), result_id))
        await db.commit()


async def get_stats() -> dict:
    """Get processing statistics."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Total pages
        cursor = await db.execute("SELECT COUNT(*) FROM pages")
        total_pages = (await cursor.fetchone())[0]
        
        # Processed pages
        cursor = await db.execute(
            "SELECT COUNT(DISTINCT page_id) FROM results WHERE success = 1"
        )
        processed_pages = (await cursor.fetchone())[0]
        
        # Total results
        cursor = await db.execute("SELECT COUNT(*) FROM results")
        total_results = (await cursor.fetchone())[0]
        
        # Success rate
        cursor = await db.execute(
            "SELECT COUNT(*) FROM results WHERE success = 1"
        )
        successful_results = (await cursor.fetchone())[0]
        
        # Average processing time
        cursor = await db.execute(
            "SELECT AVG(processing_time_ms) FROM results WHERE success = 1"
        )
        avg_time = (await cursor.fetchone())[0] or 0
        
        # By discipline
        cursor = await db.execute("""
            SELECT 
                p.discipline,
                COUNT(DISTINCT p.id) as page_count,
                COUNT(DISTINCT CASE WHEN r.success = 1 THEN p.id END) as processed_count,
                AVG(CASE WHEN r.success = 1 THEN r.processing_time_ms END) as avg_time_ms
            FROM pages p
            LEFT JOIN results r ON r.page_id = p.id
            GROUP BY p.discipline
            ORDER BY p.discipline
        """)
        by_discipline = [dict(zip(["discipline", "page_count", "processed_count", "avg_time_ms"], row)) 
                         for row in await cursor.fetchall()]
        
        # By page type
        cursor = await db.execute("""
            SELECT page_type, COUNT(*) as count
            FROM results
            WHERE success = 1 AND page_type IS NOT NULL
            GROUP BY page_type
            ORDER BY count DESC
        """)
        by_page_type = [dict(zip(["page_type", "count"], row)) for row in await cursor.fetchall()]
        
        return {
            "total_pages": total_pages,
            "processed_pages": processed_pages,
            "total_results": total_results,
            "successful_results": successful_results,
            "success_rate": successful_results / total_results if total_results > 0 else 0,
            "avg_processing_time_ms": round(avg_time, 2),
            "by_discipline": by_discipline,
            "by_page_type": by_page_type,
        }


# ============================================================================
# Pass 2 - Pointer Enrichments
# ============================================================================

async def save_pointer_enrichment(
    result_id: int,
    region_index: int,
    region_id: str,
    content_markdown: str,
    structured_fields: dict,
    cropped_png_path: str = None,
    processing_time_ms: int = None,
    prompt_version: int = 1,
    status: str = "complete",
    error_message: str = None
) -> int:
    """Save a Pass 2 enrichment result for a region."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            INSERT OR REPLACE INTO pointer_enrichments 
            (result_id, region_index, region_id, prompt_version, content_markdown, 
             structured_fields, cropped_png_path, processing_time_ms, status, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            result_id,
            region_index,
            region_id,
            prompt_version,
            content_markdown,
            json.dumps(structured_fields),
            cropped_png_path,
            processing_time_ms,
            status,
            error_message
        ))
        await db.commit()
        return cursor.lastrowid


async def get_enrichments_for_result(result_id: int, prompt_version: int = None) -> list[dict]:
    """Get all enrichments for a result (Pass 1 output)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        if prompt_version:
            cursor = await db.execute("""
                SELECT * FROM pointer_enrichments 
                WHERE result_id = ? AND prompt_version = ?
                ORDER BY region_index
            """, (result_id, prompt_version))
        else:
            cursor = await db.execute("""
                SELECT * FROM pointer_enrichments 
                WHERE result_id = ?
                ORDER BY prompt_version DESC, region_index
            """, (result_id,))
        
        rows = await cursor.fetchall()
        enrichments = []
        for row in rows:
            enrichment = dict(row)
            if enrichment.get("structured_fields"):
                enrichment["structured_fields"] = json.loads(enrichment["structured_fields"])
            enrichments.append(enrichment)
        return enrichments


async def get_enrichment_by_region(result_id: int, region_index: int, prompt_version: int = None) -> dict | None:
    """Get enrichment for a specific region."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        if prompt_version:
            cursor = await db.execute("""
                SELECT * FROM pointer_enrichments 
                WHERE result_id = ? AND region_index = ? AND prompt_version = ?
            """, (result_id, region_index, prompt_version))
        else:
            cursor = await db.execute("""
                SELECT * FROM pointer_enrichments 
                WHERE result_id = ? AND region_index = ?
                ORDER BY prompt_version DESC LIMIT 1
            """, (result_id, region_index))
        
        row = await cursor.fetchone()
        if not row:
            return None
        enrichment = dict(row)
        if enrichment.get("structured_fields"):
            enrichment["structured_fields"] = json.loads(enrichment["structured_fields"])
        return enrichment


async def get_enrichment_stats(result_id: int) -> dict:
    """Get enrichment statistics for a result."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'complete' THEN 1 ELSE 0 END) as complete,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                AVG(processing_time_ms) as avg_time_ms
            FROM pointer_enrichments
            WHERE result_id = ?
        """, (result_id,))
        row = await cursor.fetchone()
        return {
            "total": row[0] or 0,
            "complete": row[1] or 0,
            "failed": row[2] or 0,
            "pending": row[3] or 0,
            "avg_time_ms": round(row[4] or 0, 2)
        }
