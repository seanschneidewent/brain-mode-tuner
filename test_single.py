"""Quick test of Brain Mode processing."""
import asyncio
import json
from gemini_service import analyze_sheet_brain_mode, process_brain_mode_result
from pdf_processor import discover_pdfs, get_page_image_bytes, get_page_name, render_page_to_image

async def main():
    # Get PDFs
    pdfs = discover_pdfs()
    print(f"Found {len(pdfs)} PDFs")

    # Find an architectural drawing (not a schedule)
    arch_pdfs = [p for p in pdfs if p['discipline'] == 'Architectural']
    print(f"Found {len(arch_pdfs)} Architectural PDFs")
    
    test_pdf = arch_pdfs[0] if arch_pdfs else pdfs[5]
    print(f"Testing: {test_pdf['filename']} ({test_pdf['discipline']})")

    # Get image with dimensions
    img_bytes, width, height = render_page_to_image(test_pdf['pdf_path'], 0, dpi=200)
    print(f"Image size: {len(img_bytes)} bytes ({width}x{height})")

    # Get page name
    page_name = get_page_name(test_pdf['pdf_path'], 0)

    # Process
    print("Calling Gemini Brain Mode...")
    result, elapsed_ms = await analyze_sheet_brain_mode(
        img_bytes, 
        page_name, 
        test_pdf['discipline']
    )

    print(f"\n=== RESULT ({elapsed_ms}ms) ===")
    
    # Process and normalize
    processed = process_brain_mode_result(result, width, height)
    print(json.dumps(processed, indent=2, default=str)[:5000])
    
    print(f"\n--- Summary ---")
    print(f"Regions found: {len(processed['regions'])}")
    print(f"Page type: {processed['page_type']}")
    print(f"Cross refs: {processed['cross_references']}")

if __name__ == "__main__":
    asyncio.run(main())
