"""PDF processing utilities."""

import os
import fitz  # PyMuPDF
from pathlib import Path
from PIL import Image
from io import BytesIO
from config import get_settings

settings = get_settings()


def discover_pdfs(data_path: str = None) -> list[dict]:
    """
    Discover all PDFs in the data directory.
    Returns a list of dicts with pdf_path, page_count, and inferred discipline.
    """
    if data_path is None:
        data_path = settings.data_path
    
    data_path = Path(data_path)
    pdfs = []
    
    for pdf_file in data_path.rglob("*.pdf"):
        # Skip macOS metadata files
        if pdf_file.name.startswith("._"):
            continue
            
        try:
            doc = fitz.open(pdf_file)
            page_count = len(doc)
            doc.close()
            
            # Infer discipline from folder structure
            relative_path = pdf_file.relative_to(data_path)
            parts = relative_path.parts
            
            discipline = "Unknown"
            for part in parts:
                part_lower = part.lower()
                if "arch" in part_lower:
                    discipline = "Architectural"
                elif "struct" in part_lower:
                    discipline = "Structural"
                elif "mep" in part_lower:
                    discipline = "MEP"
                elif "civil" in part_lower:
                    discipline = "Civil"
                elif "kitchen" in part_lower:
                    discipline = "Kitchen"
                elif "canopy" in part_lower:
                    discipline = "Canopy"
                elif "vapor" in part_lower:
                    discipline = "Vapor Mitigation"
                elif "electric" in part_lower:
                    discipline = "Electrical"
                elif "plumb" in part_lower:
                    discipline = "Plumbing"
                elif "mechan" in part_lower:
                    discipline = "Mechanical"
            
            pdfs.append({
                "pdf_path": str(pdf_file),
                "filename": pdf_file.name,
                "page_count": page_count,
                "discipline": discipline,
                "relative_path": str(relative_path),
            })
        except Exception as e:
            print(f"Error processing {pdf_file}: {e}")
    
    return pdfs


def get_page_name(pdf_path: str, page_number: int = 0) -> str:
    """Extract a page name from the PDF filename and page number."""
    filename = Path(pdf_path).stem
    if page_number > 0:
        return f"{filename} (Page {page_number + 1})"
    return filename


def render_page_to_image(pdf_path: str, page_number: int = 0, 
                         dpi: int = 150) -> tuple[bytes, int, int]:
    """
    Render a PDF page to PNG bytes.
    Returns (image_bytes, width, height).
    """
    doc = fitz.open(pdf_path)
    page = doc[page_number]
    
    # Calculate zoom for desired DPI (default PDF is 72 DPI)
    zoom = dpi / 72
    matrix = fitz.Matrix(zoom, zoom)
    
    # Render to pixmap
    pix = page.get_pixmap(matrix=matrix)
    
    # Convert to PNG bytes
    png_bytes = pix.tobytes("png")
    width, height = pix.width, pix.height
    
    doc.close()
    
    return png_bytes, width, height


def render_page_thumbnail(pdf_path: str, page_number: int = 0,
                          max_size: int = 300) -> bytes:
    """Render a small thumbnail of a PDF page."""
    doc = fitz.open(pdf_path)
    page = doc[page_number]
    
    # Calculate zoom to fit within max_size
    rect = page.rect
    scale = min(max_size / rect.width, max_size / rect.height)
    matrix = fitz.Matrix(scale, scale)
    
    pix = page.get_pixmap(matrix=matrix)
    png_bytes = pix.tobytes("png")
    
    doc.close()
    
    return png_bytes


def save_page_images(pdf_path: str, page_number: int, cache_dir: str) -> tuple[str, str]:
    """
    Save both full image and thumbnail for a page.
    Returns (image_path, thumbnail_path).
    """
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)
    
    # Create unique filename from pdf path and page number
    pdf_name = Path(pdf_path).stem
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in pdf_name)
    base_name = f"{safe_name}_p{page_number}"
    
    image_path = cache_path / f"{base_name}.png"
    thumb_path = cache_path / f"{base_name}_thumb.png"
    
    # Render and save full image
    img_bytes, width, height = render_page_to_image(pdf_path, page_number)
    with open(image_path, "wb") as f:
        f.write(img_bytes)
    
    # Render and save thumbnail
    thumb_bytes = render_page_thumbnail(pdf_path, page_number)
    with open(thumb_path, "wb") as f:
        f.write(thumb_bytes)
    
    return str(image_path), str(thumb_path), width, height


def get_page_image_bytes(pdf_path: str, page_number: int = 0, 
                         dpi: int = 200) -> bytes:
    """Get high-quality image bytes for Gemini processing."""
    img_bytes, _, _ = render_page_to_image(pdf_path, page_number, dpi=dpi)
    return img_bytes
