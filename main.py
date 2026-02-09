"""Brain Mode Tuner - FastAPI Backend."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from config import get_settings
import database as db
from pdf_processor import (
    discover_pdfs, 
    get_page_name, 
    save_page_images, 
    get_page_image_bytes
)
from gemini_service import (
    analyze_sheet_brain_mode,
    process_brain_mode_result,
    analyze_pointer_pass2,
    crop_region_from_image,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(
    title="Brain Mode Tuner",
    description="Test and tune the Brain Mode processing pipeline for construction plans",
    version="1.0.0"
)

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

settings = get_settings()

# Create cache directory
cache_dir = Path(settings.cache_path)
cache_dir.mkdir(exist_ok=True)


# ============================================================================
# Pydantic Models
# ============================================================================

class PromptUpdate(BaseModel):
    name: str
    prompt_text: str
    set_active: bool = True


class BatchProcessRequest(BaseModel):
    page_ids: list[int]
    prompt_version_id: Optional[int] = None


class ProcessRequest(BaseModel):
    prompt_version_id: Optional[int] = None


class RegionsUpdate(BaseModel):
    regions: list[dict]


# ============================================================================
# Startup
# ============================================================================

@app.on_event("startup")
async def startup():
    """Initialize database on startup."""
    await db.init_db()
    logger.info("Database initialized")


# ============================================================================
# Static Files - Serve frontend
# ============================================================================

# Mount cache for images
app.mount("/cache", StaticFiles(directory=str(cache_dir)), name="cache")

# Serve frontend
frontend_path = Path(__file__).parent / "frontend"


@app.get("/")
async def serve_frontend():
    """Serve the main frontend page."""
    return FileResponse(frontend_path / "index.html")


@app.get("/app.js")
async def serve_js():
    """Serve the JavaScript."""
    return FileResponse(frontend_path / "app.js", media_type="application/javascript")


@app.get("/styles.css")
async def serve_css():
    """Serve the CSS."""
    return FileResponse(frontend_path / "styles.css", media_type="text/css")


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/api/scan")
async def scan_pdfs():
    """Scan the data directory and populate the database with PDF pages."""
    try:
        pdfs = discover_pdfs()
        total_pages = 0
        
        for pdf_info in pdfs:
            pdf_path = pdf_info["pdf_path"]
            discipline = pdf_info["discipline"]
            
            for page_num in range(pdf_info["page_count"]):
                page_name = get_page_name(pdf_path, page_num)
                
                # Save images and get paths
                try:
                    image_path, thumb_path, width, height = save_page_images(
                        pdf_path, page_num, str(cache_dir)
                    )
                    
                    # Save to database
                    await db.save_page(
                        pdf_path=pdf_path,
                        page_number=page_num,
                        page_name=page_name,
                        discipline=discipline,
                        thumbnail_path=thumb_path,
                        image_path=image_path,
                        width=width,
                        height=height
                    )
                    total_pages += 1
                except Exception as e:
                    logger.error(f"Error processing {pdf_path} page {page_num}: {e}")
        
        return {
            "success": True,
            "pdfs_found": len(pdfs),
            "pages_indexed": total_pages
        }
    except Exception as e:
        logger.error(f"Scan failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/disciplines")
async def get_disciplines():
    """Get all disciplines with page counts."""
    disciplines = await db.get_disciplines()
    return {"disciplines": disciplines}


@app.get("/api/pages")
async def get_pages(
    discipline: Optional[str] = None,
    processed: Optional[bool] = None,
    limit: int = 100,
    offset: int = 0
):
    """Get pages with optional filters."""
    pages = await db.get_pages(discipline, processed, limit, offset)
    
    # Convert paths to URLs
    for page in pages:
        if page.get("thumbnail_path"):
            page["thumbnail_url"] = f"/cache/{Path(page['thumbnail_path']).name}"
        if page.get("image_path"):
            page["image_url"] = f"/cache/{Path(page['image_path']).name}"
    
    return {"pages": pages}


@app.get("/api/pages/{page_id}")
async def get_page(page_id: int):
    """Get a single page by ID."""
    page = await db.get_page_by_id(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    
    # Convert paths to URLs
    if page.get("thumbnail_path"):
        page["thumbnail_url"] = f"/cache/{Path(page['thumbnail_path']).name}"
    if page.get("image_path"):
        page["image_url"] = f"/cache/{Path(page['image_path']).name}"
    
    return page


async def _crop_and_attach(image_bytes: bytes, processed: dict, page_id: int, annotated_images: list[bytes] = None):
    """Save region crop images from Pass 1's part.as_image() outputs."""
    regions = processed.get("regions", [])
    if not regions:
        return

    images = annotated_images or []

    for idx, region in enumerate(regions):
        if idx < len(images) and images[idx]:
            crop_png = images[idx]
        else:
            # Fall back to local PIL crop using bbox
            bbox = region.get("bbox", {})
            if not bbox:
                logger.warning(f"No crop image or bbox for region {idx}, skipping")
                continue
            crop_png = crop_region_from_image(image_bytes, bbox, 0, 0)
            logger.info(f"Used local PIL crop for region {idx} (no Pass 1 image)")

        crop_filename = f"crop_{page_id}_{idx}.png"
        crop_path = cache_dir / crop_filename
        with open(crop_path, "wb") as f:
            f.write(crop_png)
        region["cropped_png_path"] = str(crop_path)
        logger.info(f"Saved crop for region {idx}: {crop_filename} ({len(crop_png)} bytes)")


# Background processing state
processing_status = {
    "active": False,
    "total": 0,
    "completed": 0,
    "current_page": None,
    "errors": []
}


async def batch_process_pages(page_ids: list[int], prompt_version_id: int = None):
    """Background task for batch processing."""
    global processing_status

    try:
        processing_status["active"] = True
        processing_status["total"] = len(page_ids)
        processing_status["completed"] = 0
        processing_status["errors"] = []

        # Get prompt
        if prompt_version_id:
            prompt_info = await db.get_prompt_by_id(prompt_version_id)
            prompt_id = prompt_info["id"] if prompt_info else 0
            prompt_text = prompt_info["prompt_text"] if prompt_info else None
        else:
            prompt_id, prompt_text = await db.get_active_prompt()

        for page_id in page_ids:
            try:
                page = await db.get_page_by_id(page_id)
                if not page:
                    continue

                processing_status["current_page"] = page["page_name"]

                # Get image bytes
                image_bytes = get_page_image_bytes(page["pdf_path"], page["page_number"])

                # Run Brain Mode
                result, processing_time_ms = await analyze_sheet_brain_mode(
                    image_bytes=image_bytes,
                    page_name=page["page_name"],
                    discipline=page["discipline"],
                    custom_prompt=prompt_text
                )

                # Extract Pass 1 crop images before normalization drops them
                annotated_images = result.get("_annotated_images", [])

                # Normalize result
                processed = process_brain_mode_result(result, page["width"], page["height"])

                # Save Pass 1 crop images to disk
                await _crop_and_attach(image_bytes, processed, page_id, annotated_images)

                await db.save_result(
                    page_id=page_id,
                    prompt_version_id=prompt_id,
                    result=processed,
                    processing_time_ms=processing_time_ms,
                    success=True
                )

            except Exception as e:
                logger.error(f"Batch processing error for page {page_id}: {e}")
                processing_status["errors"].append({"page_id": page_id, "error": str(e)})

                await db.save_result(
                    page_id=page_id,
                    prompt_version_id=prompt_id,
                    result={},
                    processing_time_ms=0,
                    success=False,
                    error_message=str(e)
                )

            processing_status["completed"] += 1

            # Small delay to avoid rate limiting
            await asyncio.sleep(0.5)

        processing_status["active"] = False
        processing_status["current_page"] = None
    except Exception as e:
        logger.error(f"Batch processing crashed: {type(e).__name__}: {e}", exc_info=True)
        processing_status["active"] = False
        processing_status["current_page"] = None
        processing_status["errors"].append({"page_id": None, "error": f"Batch crashed: {e}"})


# NOTE: /api/process/batch and /api/process/status MUST come before /api/process/{page_id}
# Otherwise FastAPI will try to parse "batch" and "status" as integers

@app.post("/api/process/batch")
async def start_batch_processing(
    request: BatchProcessRequest,
    background_tasks: BackgroundTasks
):
    """Start batch processing of multiple pages."""
    if processing_status["active"]:
        raise HTTPException(status_code=400, detail="Batch processing already in progress")
    
    background_tasks.add_task(
        batch_process_pages,
        request.page_ids,
        request.prompt_version_id
    )
    
    return {
        "success": True,
        "message": f"Started processing {len(request.page_ids)} pages"
    }


@app.get("/api/process/status")
async def get_processing_status():
    """Get the current batch processing status."""
    return processing_status


@app.post("/api/process/{page_id}")
async def process_page(page_id: int, request: ProcessRequest = None):
    """Process a single page with Brain Mode."""
    page = await db.get_page_by_id(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    
    # Get prompt
    if request and request.prompt_version_id:
        prompt_info = await db.get_prompt_by_id(request.prompt_version_id)
        if not prompt_info:
            raise HTTPException(status_code=404, detail="Prompt version not found")
        prompt_id = prompt_info["id"]
        prompt_text = prompt_info["prompt_text"]
    else:
        prompt_id, prompt_text = await db.get_active_prompt()
    
    try:
        # Get image bytes
        image_bytes = get_page_image_bytes(page["pdf_path"], page["page_number"])
        
        # Run Brain Mode
        result, processing_time_ms = await analyze_sheet_brain_mode(
            image_bytes=image_bytes,
            page_name=page["page_name"],
            discipline=page["discipline"],
            custom_prompt=prompt_text
        )
        
        # Extract Pass 1 crop images before normalization drops them
        annotated_images = result.get("_annotated_images", [])

        # Log raw result structure for debugging
        logger.info(f"Raw result type={type(result).__name__}, keys={list(result.keys()) if isinstance(result, dict) else 'N/A'}")
        if isinstance(result, dict) and "regions" in result:
            regions_raw = result["regions"]
            logger.info(f"Raw regions type={type(regions_raw).__name__}, len={len(regions_raw) if isinstance(regions_raw, (list, dict)) else 'N/A'}")
            if isinstance(regions_raw, list) and len(regions_raw) > 0:
                logger.info(f"First region type={type(regions_raw[0]).__name__}, value={str(regions_raw[0])[:200]}")

        # Normalize result
        processed = process_brain_mode_result(
            result,
            page["width"],
            page["height"]
        )

        # Save Pass 1 crop images to disk
        await _crop_and_attach(image_bytes, processed, page_id, annotated_images)

        # Save result
        result_id = await db.save_result(
            page_id=page_id,
            prompt_version_id=prompt_id,
            result=processed,
            processing_time_ms=processing_time_ms,
            success=True
        )
        
        return {
            "success": True,
            "result_id": result_id,
            "processing_time_ms": processing_time_ms,
            **processed
        }
        
    except Exception as e:
        logger.error(f"Processing failed for page {page_id}: {e}", exc_info=True)

        # Save error result
        await db.save_result(
            page_id=page_id,
            prompt_version_id=prompt_id,
            result={},
            processing_time_ms=0,
            success=False,
            error_message=str(e)
        )
        
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/results/{page_id}")
async def get_results(page_id: int):
    """Get all processing results for a page."""
    results = await db.get_results_for_page(page_id)
    return {"results": results}


@app.get("/api/prompts")
async def get_prompts():
    """Get all prompt versions."""
    prompts = await db.get_prompt_versions()
    return {"prompts": prompts}


@app.get("/api/prompts/{prompt_id}")
async def get_prompt(prompt_id: int):
    """Get a specific prompt version."""
    prompt = await db.get_prompt_by_id(prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return prompt


@app.post("/api/prompts")
async def create_prompt(request: PromptUpdate):
    """Create a new prompt version."""
    prompt_id = await db.save_prompt_version(
        name=request.name,
        prompt_text=request.prompt_text,
        set_active=request.set_active
    )
    return {"success": True, "prompt_id": prompt_id}


@app.put("/api/prompts/{prompt_id}/activate")
async def activate_prompt(prompt_id: int):
    """Set a prompt version as active."""
    prompt = await db.get_prompt_by_id(prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    
    await db.set_active_prompt(prompt_id)
    return {"success": True}


@app.get("/api/stats")
async def get_stats():
    """Get processing statistics."""
    stats = await db.get_stats()
    return stats


# ============================================================================
# Region Editing (Manual BBox Editor)
# ============================================================================

@app.put("/api/regions/{page_id}")
async def update_regions(page_id: int, request: RegionsUpdate):
    """Update regions for a page (manual bbox editing)."""
    # Get the latest result for this page
    results = await db.get_results_for_page(page_id)
    if not results:
        raise HTTPException(status_code=400, detail="Page has not been processed yet")
    
    latest_result = results[0]
    result_id = latest_result["id"]
    
    try:
        # Update regions in database
        await db.update_regions(result_id, request.regions)
        
        return {
            "success": True,
            "message": "Regions updated successfully",
            "result_id": result_id,
            "region_count": len(request.regions)
        }
        
    except Exception as e:
        logger.error(f"Update regions failed for page {page_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Pass 2 - Pointer Enrichment
# ============================================================================

# Enrichment processing status
enrichment_status = {
    "active": False,
    "result_id": None,
    "total": 0,
    "completed": 0,
    "current_region": None,
    "errors": []
}


async def enrich_regions_background(result_id: int, region_indices: list[int] = None):
    """Background task for enriching regions."""
    global enrichment_status

    try:
        # Get the result and page
        result = await db.get_result_by_id(result_id)
        if not result:
            return

        page = await db.get_page_by_id(result["page_id"])
        if not page:
            return

        regions = result.get("regions", [])
        if not regions:
            return

        # Filter to specific indices if provided
        if region_indices:
            process_regions = [(i, regions[i]) for i in region_indices if i < len(regions)]
        else:
            process_regions = list(enumerate(regions))

        enrichment_status["active"] = True
        enrichment_status["result_id"] = result_id
        enrichment_status["total"] = len(process_regions)
        enrichment_status["completed"] = 0
        enrichment_status["errors"] = []

        # Render high-quality page image for Gemini processing
        full_page_png = get_page_image_bytes(page["pdf_path"], page["page_number"])

        # Build pass1 context
        raw = result.get("raw_response", {})
        pass1_context = {
            "sheet_info": raw.get("sheet_info", {}),
            "sheet_reflection": result.get("sheet_reflection", ""),
            "index": raw.get("index", {}),
            "cross_references": result.get("cross_references", []),
            "page_name": page["page_name"],
            "discipline": page["discipline"]
        }

        for idx, region in process_regions:
            try:
                enrichment_status["current_region"] = region.get("label", region.get("id", f"region_{idx}"))

                # Use Gemini-cropped PNG if available, fall back to local crop
                gemini_crop_path = region.get("cropped_png_path")
                if gemini_crop_path and Path(gemini_crop_path).exists():
                    with open(gemini_crop_path, "rb") as f:
                        cropped_png = f.read()
                    crop_path = Path(gemini_crop_path)
                    logger.info(f"Using Gemini crop for region {idx}: {gemini_crop_path}")
                else:
                    if gemini_crop_path:
                        logger.warning(f"Gemini crop missing at {gemini_crop_path}, falling back to local crop")
                    bbox = region.get("bbox", {})
                    cropped_png = crop_region_from_image(
                        full_page_png,
                        bbox,
                        page["width"],
                        page["height"]
                    )
                    crop_filename = f"crop_{result_id}_{idx}.png"
                    crop_path = cache_dir / crop_filename
                    with open(crop_path, "wb") as f:
                        f.write(cropped_png)

                # Run Pass 2
                enrichment_result, processing_time_ms = await analyze_pointer_pass2(
                    cropped_png=cropped_png,
                    full_page_png=full_page_png,
                    region=region,
                    pass1_context=pass1_context
                )

                # Ensure enrichment_result is a dict
                if not isinstance(enrichment_result, dict):
                    enrichment_result = {"content_markdown": str(enrichment_result), "extraction_failed": True}

                # Save enrichment
                await db.save_pointer_enrichment(
                    result_id=result_id,
                    region_index=idx,
                    region_id=region.get("id", f"region_{idx}"),
                    content_markdown=enrichment_result.get("content_markdown", ""),
                    structured_fields=enrichment_result,
                    cropped_png_path=str(crop_path),
                    processing_time_ms=processing_time_ms,
                    status="complete" if enrichment_result.get("content_markdown") else "partial"
                )

            except Exception as e:
                logger.error(f"Enrichment error for region {idx}: {e}", exc_info=True)
                enrichment_status["errors"].append({
                    "region_index": idx,
                    "region_id": region.get("id"),
                    "error": str(e)
                })

                # Save failed enrichment
                try:
                    await db.save_pointer_enrichment(
                        result_id=result_id,
                        region_index=idx,
                        region_id=region.get("id", f"region_{idx}"),
                        content_markdown="",
                        structured_fields={},
                        processing_time_ms=0,
                        status="failed",
                        error_message=str(e)
                    )
                except Exception as save_err:
                    logger.error(f"Failed to save error enrichment for region {idx}: {save_err}")

            enrichment_status["completed"] += 1

            # Small delay to avoid rate limiting
            await asyncio.sleep(0.5)

    except Exception as e:
        logger.error(f"Enrichment background task crashed: {type(e).__name__}: {e}", exc_info=True)
        enrichment_status["errors"].append({"region_index": None, "error": f"Task crashed: {e}"})
    finally:
        enrichment_status["active"] = False
        enrichment_status["current_region"] = None


# NOTE: /api/enrich/status and /api/enrich/region MUST come before /api/enrich/{page_id}
# Otherwise FastAPI will try to parse "status" and "region" as integers

@app.get("/api/enrich/status")
async def get_enrichment_status():
    """Get the current enrichment processing status."""
    return enrichment_status


@app.post("/api/enrich/region/{result_id}/{region_index}")
async def enrich_single_region(result_id: int, region_index: int, background_tasks: BackgroundTasks):
    """Trigger Pass 2 enrichment for a single region."""
    if enrichment_status["active"]:
        raise HTTPException(status_code=400, detail="Enrichment already in progress")
    
    result = await db.get_result_by_id(result_id)
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")
    
    regions = result.get("regions", [])
    if region_index >= len(regions):
        raise HTTPException(status_code=400, detail=f"Region index {region_index} out of range (max {len(regions)-1})")
    
    background_tasks.add_task(enrich_regions_background, result_id, [region_index])
    
    return {
        "success": True,
        "message": f"Started Pass 2 enrichment for region {region_index}",
        "result_id": result_id,
        "region_index": region_index
    }


@app.post("/api/enrich/{result_id}")
async def enrich_page(result_id: int, background_tasks: BackgroundTasks):
    """Trigger Pass 2 enrichment for all regions on a result."""
    if enrichment_status["active"]:
        raise HTTPException(status_code=400, detail="Enrichment already in progress")

    result = await db.get_result_by_id(result_id)
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")

    regions = result.get("regions", [])
    if not regions:
        raise HTTPException(status_code=400, detail="No regions found in Pass 1 result")

    background_tasks.add_task(enrich_regions_background, result["id"])
    
    return {
        "success": True,
        "message": f"Started Pass 2 enrichment for {len(regions)} regions",
        "result_id": result["id"],
        "region_count": len(regions)
    }


@app.get("/api/enrichments/{result_id}")
async def get_enrichments(result_id: int):
    """Get all Pass 2 enrichments for a result."""
    result = await db.get_result_by_id(result_id)
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")
    
    enrichments = await db.get_enrichments_for_result(result_id)
    for e in enrichments:
        if e.get("cropped_png_path"):
            e["cropped_png_url"] = f"/cache/{Path(e['cropped_png_path']).name}"
    stats = await db.get_enrichment_stats(result_id)

    return {
        "result_id": result_id,
        "stats": stats,
        "enrichments": enrichments
    }


@app.get("/api/enrichments/{result_id}/{region_index}")
async def get_enrichment(result_id: int, region_index: int):
    """Get Pass 2 enrichment for a specific region."""
    enrichment = await db.get_enrichment_by_region(result_id, region_index)
    if not enrichment:
        raise HTTPException(status_code=404, detail="Enrichment not found")
    
    # Convert cropped PNG path to URL if exists
    if enrichment.get("cropped_png_path"):
        enrichment["cropped_png_url"] = f"/cache/{Path(enrichment['cropped_png_path']).name}"
    
    return enrichment


# ============================================================================
# Run
# ============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Catch-all exception handler to prevent server crashes."""
    logger.error(f"Unhandled exception on {request.url}: {type(exc).__name__}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {type(exc).__name__}: {str(exc)}"}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_includes=["*.py"],
        reload_excludes=["__pycache__/*", "cache/*", "*.db"],
        timeout_keep_alive=30,
        log_level="info",
    )
