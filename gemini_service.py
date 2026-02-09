"""Gemini AI service for Brain Mode processing.

Uses Gemini 3 Flash Thinking with Agentic Vision:
- Think→Act→Observe loop for visual understanding
- Code execution for precise bounding box detection
- High thinking level for complex spatial reasoning
"""

import json
import logging
import re
import time
from google import genai
from google.genai import types
from config import get_settings, BRAIN_MODE_MODEL, THINKING_LEVEL

logger = logging.getLogger(__name__)


def _extract_json_response(text: str) -> dict:
    """Extract JSON from response text, handling markdown code blocks and malformed JSON.

    Handles common Gemini issues:
    - JSON wrapped in markdown code blocks
    - Missing opening brace (starts with "key":)
    - Missing closing brace (truncated response)
    - Trailing commas before closing brace
    - Extra text before/after JSON
    """
    if not text:
        return {}

    original_text = text

    # Try to find JSON in code blocks first
    code_block_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if code_block_match:
        text = code_block_match.group(1)

    # Try to parse as JSON directly
    try:
        parsed = json.loads(text.strip())
        # If Gemini returned a list at top level, try to find the dict inside
        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict):
                    return item
            return {}
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in text by matching outermost braces
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            # Try fixing trailing comma before closing brace
            candidate = text[start:end]
            candidate = re.sub(r',\s*}', '}', candidate)
            candidate = re.sub(r',\s*]', ']', candidate)
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

    # Handle Gemini's malformed JSON - missing opening brace
    # e.g., '\n  "content_markdown": "...",\n  "materials": [...]'
    cleaned = text.strip()

    # If it starts with a quote (key name), wrap in braces
    if cleaned.lstrip().startswith('"'):
        wrapped = "{" + cleaned.lstrip()
        # Ensure it ends with a closing brace
        if not wrapped.rstrip().endswith("}"):
            wrapped = wrapped.rstrip().rstrip(",") + "}"
        # Fix trailing commas
        wrapped = re.sub(r',\s*}', '}', wrapped)
        wrapped = re.sub(r',\s*]', ']', wrapped)
        try:
            return json.loads(wrapped)
        except json.JSONDecodeError:
            # Try to find the last valid JSON by progressively trimming
            # Sometimes Gemini appends extra text after the JSON
            for i in range(len(wrapped) - 1, 0, -1):
                if wrapped[i] == '}':
                    try:
                        return json.loads(wrapped[:i + 1])
                    except json.JSONDecodeError:
                        continue

    # Try aggressive cleanup - wrap anything with known keys in braces
    known_keys = ['"content_markdown"', '"regions"', '"sheet_info"', '"materials"']
    if any(key in text for key in known_keys):
        cleaned = text.strip()
        if not cleaned.startswith("{"):
            cleaned = "{" + cleaned
        if not cleaned.endswith("}"):
            cleaned = cleaned.rstrip().rstrip(",") + "}"
        # Fix trailing commas
        cleaned = re.sub(r',\s*}', '}', cleaned)
        cleaned = re.sub(r',\s*]', ']', cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Last resort: try to find the largest valid JSON substring
            for i in range(len(cleaned) - 1, 0, -1):
                if cleaned[i] == '}':
                    try:
                        return json.loads(cleaned[:i + 1])
                    except json.JSONDecodeError:
                        continue

    # Return empty result if all parsing fails
    logger.warning(f"Failed to extract JSON from response: {original_text[:500]}...")
    return {}


def _get_gemini_client():
    """Get Gemini client."""
    settings = get_settings()
    if not settings.gemini_api_key:
        raise ValueError("Gemini API key must be configured in .env file")
    return genai.Client(api_key=settings.gemini_api_key)


async def analyze_sheet_brain_mode(
    image_bytes: bytes,
    page_name: str,
    discipline: str,
    custom_prompt: str = None,
) -> tuple[dict, int]:
    """
    Single Gemini call for Brain Mode comprehension.
    
    Returns:
        tuple of (result_dict, processing_time_ms)
    """
    from database import get_default_prompt
    
    start_time = time.perf_counter()
    
    try:
        client = _get_gemini_client()
        
        prompt_text = custom_prompt or get_default_prompt()
        prompt = (
            f"{prompt_text}\n\n"
            f"PAGE NAME: {page_name}\n"
            f"DISCIPLINE: {discipline}"
        )
        
        # Gemini 3 Flash Thinking with Agentic Vision
        # - thinking_level="high" enables deep reasoning (Flash Thinking)
        # - code_execution enables Think→Act→Observe loop for visual grounding
        response = client.models.generate_content(
            model=BRAIN_MODE_MODEL,
            contents=[
                types.Content(
                    parts=[
                        types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                        types.Part.from_text(text=prompt),
                    ]
                )
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0,
                thinking_config=types.ThinkingConfig(thinking_level=THINKING_LEVEL),
                tools=[types.Tool(code_execution=types.ToolCodeExecution)],
            ),
        )
        
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        
        # Handle multi-part response from Agentic Vision
        # Response may contain: thought, text, executable_code, code_execution_result, images
        response_text = ""
        annotated_images = []
        
        for part in response.candidates[0].content.parts:
            if part.thought:
                continue
            if part.text is not None:
                response_text += part.text
            if part.executable_code is not None:
                logger.debug(f"Model executed code: {part.executable_code.code[:200]}...")
            if part.code_execution_result is not None:
                logger.debug(f"Code result: {part.code_execution_result.output[:200] if part.code_execution_result.output else 'none'}")
            if part.as_image() is not None:
                annotated_images.append(part.as_image().image_bytes)
                logger.info(f"Model generated annotated image")
        
        result = _extract_json_response(response_text)
        
        # Store annotated images if model generated any (for future use)
        if annotated_images:
            result["_annotated_images"] = annotated_images
        
        logger.info(f"Brain Mode analysis complete for {page_name} in {elapsed_ms}ms (thinking={THINKING_LEVEL})")
        return result, elapsed_ms
        
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        logger.error(f"Brain Mode analysis failed: {e}")
        raise


def normalize_bbox(bbox: dict, width: int, height: int) -> dict:
    """Normalize bounding box coordinates to be within image bounds."""
    def coerce_int(val, default=0):
        try:
            return int(val)
        except (TypeError, ValueError):
            return default
    
    x0 = coerce_int(bbox.get("x0"), 0)
    y0 = coerce_int(bbox.get("y0"), 0)
    x1 = coerce_int(bbox.get("x1"), 0)
    y1 = coerce_int(bbox.get("y1"), 0)
    
    # Clamp to image bounds
    x0 = max(0, min(width, x0))
    y0 = max(0, min(height, y0))
    x1 = max(0, min(width, x1))
    y1 = max(0, min(height, y1))
    
    # Ensure x0 < x1 and y0 < y1
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    
    return {"x0": x0, "y0": y0, "x1": x1, "y1": y1}


def process_brain_mode_result(result: dict, width: int, height: int) -> dict:
    """Process and normalize Brain Mode result."""
    if not isinstance(result, dict):
        logger.error(f"process_brain_mode_result got non-dict result: {type(result)} — {str(result)[:300]}")
        result = {}
    regions = result.get("regions", [])
    if not isinstance(regions, list):
        regions = []
    
    normalized_regions = []
    for idx, region in enumerate(regions):
        if not isinstance(region, dict):
            # Gemini sometimes returns a region as a list [x0, y0, x1, y1]
            if isinstance(region, list) and len(region) == 4:
                region = {"bbox": {"x0": region[0], "y0": region[1], "x1": region[2], "y1": region[3]}}
            else:
                logger.warning(f"Skipping non-dict region at index {idx}: {type(region)}")
                continue

        bbox = region.get("bbox", {})
        # Handle bbox as list [x0, y0, x1, y1]
        if isinstance(bbox, list) and len(bbox) >= 4:
            bbox = {"x0": bbox[0], "y0": bbox[1], "x1": bbox[2], "y1": bbox[3]}
        elif not isinstance(bbox, dict):
            bbox = {}
        normalized = {
            "id": region.get("id") or f"region_{idx + 1:03d}",
            "type": (region.get("type") or "unknown").lower(),
            "bbox": normalize_bbox(bbox, width, height),
            "label": region.get("label") or "",
            "confidence": float(region.get("confidence") or 0.0),
        }
        
        if region.get("detail_number") is not None:
            normalized["detail_number"] = str(region["detail_number"])

        if region.get("region_index"):
            normalized["region_index"] = region["region_index"]
        if region.get("shows"):
            normalized["shows"] = region["shows"]
        if region.get("scale"):
            normalized["scale"] = str(region["scale"])

        # Include contains field if present (areas within the region)
        if region.get("contains"):
            normalized["contains"] = region["contains"]
        
        normalized_regions.append(normalized)
    
    sheet_reflection = result.get("sheet_reflection", "")
    if not isinstance(sheet_reflection, str):
        sheet_reflection = ""
    
    page_type = result.get("page_type", "unknown")
    if not isinstance(page_type, str):
        page_type = "unknown"
    
    # Handle cross_references - can be list of strings or list of objects with context
    cross_refs = result.get("cross_references", [])
    if not isinstance(cross_refs, list):
        cross_refs = []
    # Normalize to list of strings for simple display, keep full objects in raw
    cross_refs_simple = []
    for r in cross_refs:
        if isinstance(r, dict):
            cross_refs_simple.append(r.get("sheet", str(r)))
        elif r:
            cross_refs_simple.append(str(r))
    
    # Extract the new index structure (handle if Gemini returns unexpected types)
    index = result.get("index", {})
    if not isinstance(index, dict):
        index = {}
    sheet_info = result.get("sheet_info", {})
    if not isinstance(sheet_info, dict):
        sheet_info = {}
    questions = result.get("questions_this_sheet_answers", [])
    if not isinstance(questions, list):
        questions = []
    
    return {
        "regions": normalized_regions,
        "sheet_reflection": sheet_reflection,
        "page_type": page_type,
        "discipline": result.get("discipline", ""),
        "cross_references": cross_refs_simple,
        # New RAG-optimized fields
        "sheet_info": sheet_info,
        "index": index,
        "questions_this_sheet_answers": questions,
    }


# verify_regions removed - replaced by manual bbox editor


def crop_region_from_image(image_bytes: bytes, bbox: dict, width: int, height: int, padding: int = 20) -> bytes:
    """
    Crop a region from a full page image using normalized bbox coordinates.
    
    Args:
        image_bytes: Full page PNG as bytes
        bbox: Normalized bbox with x0, y0, x1, y1 (0-1000 scale)
        width: Original image width in pixels
        height: Original image height in pixels
        padding: Extra pixels around the crop (default 20)
    
    Returns:
        Cropped region as PNG bytes
    """
    from PIL import Image
    import io
    
    # Load image
    img = Image.open(io.BytesIO(image_bytes))
    img_w, img_h = img.size

    # Convert normalized coords (0-1000) to pixel coords using actual image dimensions
    # (not the DB-stored width/height which may be from a different DPI render)
    scale_x = img_w / 1000.0
    scale_y = img_h / 1000.0

    x0 = int(bbox.get("x0", 0) * scale_x) - padding
    y0 = int(bbox.get("y0", 0) * scale_y) - padding
    x1 = int(bbox.get("x1", 0) * scale_x) + padding
    y1 = int(bbox.get("y1", 0) * scale_y) + padding

    # Clamp to image bounds
    x0 = max(0, x0)
    y0 = max(0, y0)
    x1 = min(img_w, x1)
    y1 = min(img_h, y1)
    
    # Crop
    cropped = img.crop((x0, y0, x1, y1))
    
    # Save to bytes
    output = io.BytesIO()
    cropped.save(output, format="PNG")
    return output.getvalue()


async def crop_regions_via_gemini(image_bytes: bytes, regions: list[dict]) -> list[bytes]:
    """
    Use Gemini's code execution to crop regions from a full page image.

    Args:
        image_bytes: Full page PNG as bytes
        regions: List of region dicts, each with bbox {x0, y0, x1, y1} on 0-1000 scale

    Returns:
        List of PNG bytes, one per region (in order). Empty bytes for failed crops.
    """
    if not regions:
        return []

    # Build the bbox list for the prompt
    bbox_lines = []
    for i, region in enumerate(regions):
        bbox = region.get("bbox", {})
        coords = [bbox.get("x0", 0), bbox.get("y0", 0), bbox.get("x1", 0), bbox.get("y1", 0)]
        label = region.get("label", region.get("id", f"region_{i}"))
        bbox_lines.append(f"Region {i}: {coords} — \"{label}\"")

    regions_text = "\n".join(bbox_lines)

    prompt = f"""You have a construction drawing image. Crop the following bounding box regions from it using Python code.
Display each crop in order. Bounding boxes are normalized [x0, y0, x1, y1] on a 0–1000 scale:

{regions_text}

Use PIL to crop each region, scaling the 0–1000 coordinates to the actual image pixel dimensions.
Add 20px padding around each crop (clamped to image bounds).
Display each cropped image using PIL's Image.show() or IPython display so it appears in the output."""

    try:
        client = _get_gemini_client()

        response = client.models.generate_content(
            model=BRAIN_MODE_MODEL,
            contents=[
                types.Content(
                    parts=[
                        types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                        types.Part.from_text(text=prompt),
                    ]
                )
            ],
            config=types.GenerateContentConfig(
                temperature=0,
                thinking_config=types.ThinkingConfig(thinking_level="low"),
                tools=[types.Tool(code_execution=types.ToolCodeExecution)],
            ),
        )

        # Collect images from the response in order (matching SDK docs pattern)
        crop_images = []
        for part in response.candidates[0].content.parts:
            if part.text is not None:
                logger.debug(f"Crop response text: {part.text[:200]}...")
            if part.executable_code is not None:
                logger.debug(f"Crop code: {part.executable_code.code[:300]}...")
            if part.code_execution_result is not None:
                logger.debug(f"Crop exec result: {part.code_execution_result.output[:200] if part.code_execution_result.output else 'none'}...")
            if part.as_image() is not None:
                crop_images.append(part.as_image().image_bytes)

        logger.info(f"Gemini returned {len(crop_images)} crop images for {len(regions)} regions")

        # Pad with empty bytes if fewer images returned than regions
        while len(crop_images) < len(regions):
            crop_images.append(b"")

        return crop_images

    except Exception as e:
        logger.error(f"crop_regions_via_gemini failed: {type(e).__name__}: {e}")
        # Return empty list so callers can fall back to local cropping
        return [b""] * len(regions)


def get_pass2_prompt() -> str:
    """Return the Pass 2 pointer enrichment prompt."""
    return '''You are deeply analyzing a single region from a construction drawing. You have already seen the full sheet and identified this region during a first pass. Now focus exclusively on this cropped area and extract EVERYTHING.

## CONTEXT FROM PASS 1

Sheet: {sheet_number} — {sheet_title}
Discipline: {discipline}
Region: {region_type} — {region_label}
{detail_number_line}

Sheet Summary:
{sheet_reflection}

Your first impression of this region:
{region_index_text}

Full keynote list from this sheet:
{keynotes_text}

Cross-referenced sheets:
{cross_refs_text}

## YOUR TASK

You are provided ONE image: the CROPPED REGION extracted from the sheet. This is the ONLY area you should analyze. The context above tells you where this region sits on the full sheet.

Read EVERYTHING visible in this cropped image:
- Every line of text, every dimension string, every callout
- Every material indication (hatching patterns, labels, specs)
- Every connection point (how does this detail meet adjacent assemblies?)
- Every note, flag, or reference marker

Then produce two things:

### 1. content_markdown
Write a structured markdown technical brief for this region. A superintendent should be able to hand this to a subcontractor and they know exactly what to build.

For DETAILS: Include assembly layers (exterior to interior), key dimensions, coordination notes
For PLANS: Include key areas, major modifications, referenced keynotes
For KEYNOTES: List all keynotes with their full text
For SCHEDULES: Include schedule type, columns, and key rows

### 2. Structured fields
Extract the same information as queryable data.

## OUTPUT JSON

Return a JSON object with these fields:

{{
  "content_markdown": "The full markdown document as a string",
  "materials": ["list of materials mentioned"],
  "dimensions": ["list of dimensions read"],
  "keynotes_referenced": [{{"number": "1", "text": "keynote text"}}],
  "specifications": ["list of specs"],
  "cross_references": [{{"sheet": "A401", "detail": "2", "context": "why referenced"}}],
  "coordination_notes": ["things to coordinate with other trades"],
  "questions_answered": ["questions this region answers"]
}}

For DETAILS, also include:
- "assembly": [{{"position": 1, "layer": "finish", "material": "FRP", "thickness": "1/16\\""}}]
- "connections": [{{"to": "floor slab", "condition": "membrane laps 4\\" min"}}]

For PLANS, also include:
- "areas": [{{"name": "kitchen", "notes": "new equipment layout"}}]
- "equipment": [{{"name": "Tormax door", "location": "drive-thru", "keynote": "1"}}]
- "modifications": [{{"action": "install", "item": "door", "location": "entry"}}]

For KEYNOTES, also include:
- "keynotes": [{{"number": "1", "text": "NEW TORMAX DOOR"}}]

For SCHEDULES, also include:
- "schedule_type": "door_schedule"
- "columns": ["mark", "width", "height", "type"]
- "rows": [{{"mark": "101", "width": "3'-0\\"", "height": "7'-0\\""}}]
'''


async def analyze_pointer_pass2(
    cropped_png: bytes,
    full_page_png: bytes,
    region: dict,
    pass1_context: dict,
    custom_prompt: str = None,
) -> tuple[dict, int]:
    """
    Pass 2: Deep analysis of a single region/pointer.
    
    Args:
        cropped_png: Cropped region image as bytes
        full_page_png: Full page image for context
        region: The region dict from Pass 1 (type, label, bbox, region_index, etc.)
        pass1_context: Dict with sheet_info, sheet_reflection, index, cross_references, page_name, discipline
        custom_prompt: Optional custom prompt override
    
    Returns:
        tuple of (result_dict, processing_time_ms)
    """
    start_time = time.perf_counter()
    
    try:
        client = _get_gemini_client()
        
        # Build prompt with context substitution
        prompt_template = custom_prompt or get_pass2_prompt()
        
        # Extract context values
        sheet_info = pass1_context.get("sheet_info", {})
        index = pass1_context.get("index", {})
        region_index = region.get("region_index", {})
        
        # Format region index for prompt
        region_index_text = ""
        if region_index:
            if region_index.get("materials"):
                region_index_text += f"Materials: {', '.join(region_index['materials'])}\n"
            if region_index.get("items"):
                items = [f"{i.get('name', '')} ({i.get('action', '')})" for i in region_index['items']]
                region_index_text += f"Items: {', '.join(items)}\n"
            if region_index.get("dimensions"):
                region_index_text += f"Dimensions: {', '.join(region_index['dimensions'])}\n"
            if region_index.get("keynotes_shown"):
                region_index_text += f"Keynotes shown: {', '.join(str(k) for k in region_index['keynotes_shown'])}\n"
        if not region_index_text:
            region_index_text = region.get("shows", "No prior analysis available")
        
        # Format keynotes
        keynotes = index.get("keynotes", [])
        keynotes_text = "\n".join([f"- {k.get('number', '?')}: {k.get('text', '')}" for k in keynotes]) if keynotes else "No keynotes found"
        
        # Format cross references
        cross_refs = pass1_context.get("cross_references", [])
        if isinstance(cross_refs, list):
            cross_refs_text = ", ".join(str(r) for r in cross_refs) if cross_refs else "None"
        else:
            cross_refs_text = str(cross_refs)
        
        # Build final prompt
        prompt = prompt_template.format(
            sheet_number=sheet_info.get("number", pass1_context.get("page_name", "Unknown")),
            sheet_title=sheet_info.get("title", ""),
            discipline=pass1_context.get("discipline", ""),
            region_type=region.get("type", "unknown"),
            region_label=region.get("label", ""),
            detail_number_line=f"Detail Number: {region['detail_number']}" if region.get("detail_number") else "",
            sheet_reflection=pass1_context.get("sheet_reflection", ""),
            region_index_text=region_index_text,
            keynotes_text=keynotes_text,
            cross_refs_text=cross_refs_text
        )

        # Send cropped region image only
        response = client.models.generate_content(
            model=BRAIN_MODE_MODEL,
            contents=[
                types.Content(
                    parts=[
                        types.Part.from_bytes(data=cropped_png, mime_type="image/png"),
                        types.Part.from_text(text=prompt),
                    ]
                )
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0,
                thinking_config=types.ThinkingConfig(thinking_level=THINKING_LEVEL),
            ),
        )
        
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        
        # Extract response text
        response_text = ""
        for part in response.candidates[0].content.parts:
            if hasattr(part, 'thought') and part.thought:
                continue
            if part.text is not None:
                response_text += part.text
        
        result = _extract_json_response(response_text)
        
        # If extraction failed, log the raw response for debugging
        if not result or not result.get("content_markdown"):
            logger.warning(f"Pass 2 extraction may have failed. Raw response: {response_text[:500]}...")
            # Still return what we got, don't fail
            if not result:
                result = {"content_markdown": response_text, "extraction_failed": True}
        
        logger.info(f"Pass 2 analysis complete for {region.get('label', region.get('id', 'unknown'))} in {elapsed_ms}ms")
        return result, elapsed_ms
        
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        logger.error(f"Pass 2 analysis failed: {type(e).__name__}: {e}")
        # Return a failure result instead of raising, so enrichment can continue
        return {
            "content_markdown": f"Error: {e}",
            "error": str(e),
            "materials": [],
            "dimensions": [],
        }, elapsed_ms
