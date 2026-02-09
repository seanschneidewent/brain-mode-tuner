# 🧠 Brain Mode Tuner

A standalone local web app to test and tune the Brain Mode processing pipeline on construction plans.

## Quick Start

1. **Install dependencies:**
   ```bash
   cd C:\Users\Sean Schneidewent\brain-mode-tuner
   pip install -r requirements.txt
   ```

2. **Configure:**
   - Copy `.env.example` to `.env`
   - Add your `GEMINI_API_KEY`
   - Optionally update `DATA_PATH` to point to your PDFs

3. **Run:**
   ```bash
   python run_app.py
   ```

4. **Open:** http://localhost:8000

## Features

### 📊 Dashboard
- Overview of processing stats
- Quick access to disciplines
- Batch processing status

### 📄 Page Browser
- Browse all PDF pages by discipline
- Filter by processed/unprocessed status
- Thumbnail previews

### 🔍 Page Detail View
- Full-size page image
- **Bounding box overlays** for detected regions
- Sheet reflection (markdown)
- Cross-references
- Processing history

### ✏️ Prompt Tuning
- Edit the Brain Mode prompt
- Save multiple versions
- Compare results across versions

### 📈 Statistics
- Processing times by discipline
- Page type distribution
- Success rates

## Workflow

1. **Scan PDFs** - Click "Scan PDFs" to discover all PDFs in the data folder
2. **Browse Pages** - View thumbnails and select pages to analyze
3. **Process** - Run Brain Mode on individual pages or batch process
4. **Review** - See detected regions overlaid on the page
5. **Tune** - Edit the prompt and re-process to compare results

## Configuration

Edit `.env`:

```env
# Required: Your Gemini API key
GEMINI_API_KEY=your_key_here

# Optional: Path to PDFs (default shown)
DATA_PATH=D:\MOCK DATA\Chick-fil-A Love Field FSU 03904 -CPS
```

## Output Format

Brain Mode returns structured JSON:

```json
{
  "page_type": "detail_sheet|floor_plan|schedule|...",
  "discipline": "structural|mechanical|electrical|...",
  "regions": [
    {
      "id": "region_001",
      "type": "detail|schedule|notes|title_block|...",
      "bbox": {"x0": 100, "y0": 200, "x1": 500, "y1": 600},
      "label": "EMBEDDED POST DETAIL",
      "detail_number": "8",
      "confidence": 0.95
    }
  ],
  "sheet_reflection": "## S-401: Structural Details\n\n...",
  "cross_references": ["S-101", "S-201", "A-401"]
}
```

## Files

- `main.py` - FastAPI backend
- `database.py` - SQLite storage
- `pdf_processor.py` - PDF→PNG conversion
- `gemini_service.py` - Gemini API integration
- `frontend/` - HTML/CSS/JS frontend
- `cache/` - Generated thumbnails and images
- `brain_mode.db` - SQLite database

## API Endpoints

- `GET /api/scan` - Scan PDFs and populate database
- `GET /api/disciplines` - List disciplines with counts
- `GET /api/pages` - List pages (with filters)
- `GET /api/pages/{id}` - Get single page
- `POST /api/process/{id}` - Process a page
- `POST /api/process/batch` - Batch process pages
- `GET /api/process/status` - Get batch status
- `GET /api/results/{id}` - Get page results
- `GET /api/prompts` - List prompt versions
- `POST /api/prompts` - Create new prompt
- `GET /api/stats` - Get statistics
