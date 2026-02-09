"""Test Brain Mode across different disciplines."""
import asyncio
import json
from gemini_service import analyze_sheet_brain_mode, process_brain_mode_result
from pdf_processor import discover_pdfs, render_page_to_image, get_page_name

async def test_discipline(pdfs, discipline, max_pages=2):
    """Test pages from a specific discipline."""
    disc_pdfs = [p for p in pdfs if p['discipline'] == discipline]
    if not disc_pdfs:
        return []
    
    results = []
    for pdf in disc_pdfs[:max_pages]:
        try:
            img_bytes, width, height = render_page_to_image(pdf['pdf_path'], 0, dpi=200)
            page_name = get_page_name(pdf['pdf_path'], 0)
            
            result, elapsed_ms = await analyze_sheet_brain_mode(
                img_bytes, page_name, pdf['discipline']
            )
            
            processed = process_brain_mode_result(result, width, height)
            results.append({
                'filename': pdf['filename'],
                'discipline': discipline,
                'elapsed_ms': elapsed_ms,
                'regions': len(processed['regions']),
                'page_type': processed['page_type'],
                'reflection_length': len(processed['sheet_reflection']),
                'cross_refs': len(processed['cross_references']),
            })
            print(f"  OK {pdf['filename'][:40]}: {elapsed_ms}ms, {len(processed['regions'])} regions, {processed['page_type']}")
        except Exception as e:
            print(f"  ERR {pdf['filename'][:40]}: {e}")
            results.append({'filename': pdf['filename'], 'error': str(e)})
    
    return results

async def main():
    pdfs = discover_pdfs()
    print(f"Found {len(pdfs)} PDFs\n")
    
    disciplines = ['Architectural', 'Structural', 'MEP', 'Civil', 'Electrical', 'Plumbing', 'Mechanical']
    
    all_results = []
    for disc in disciplines:
        count = len([p for p in pdfs if p['discipline'] == disc])
        if count == 0:
            continue
        print(f"\n{disc} ({count} pages):")
        results = await test_discipline(pdfs, disc, max_pages=2)
        all_results.extend(results)
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    successful = [r for r in all_results if 'error' not in r]
    if successful:
        avg_time = sum(r['elapsed_ms'] for r in successful) / len(successful)
        avg_regions = sum(r['regions'] for r in successful) / len(successful)
        print(f"Tested: {len(successful)} pages")
        print(f"Avg time: {avg_time:.0f}ms")
        print(f"Avg regions: {avg_regions:.1f}")
        
        # Page types
        types = {}
        for r in successful:
            t = r['page_type']
            types[t] = types.get(t, 0) + 1
        print(f"Page types: {types}")

if __name__ == "__main__":
    asyncio.run(main())
