# Task: Manual BBox Editor ✅ COMPLETE

## Goal
Replace Pass 2 verification with a manual bounding box editor. Gemini Pass 1 gets close enough — human just nudges edge cases.

## Removed (Pass 2 / Verification)

### Backend (main.py)
- [x] DELETE `/api/verify/{page_id}`
- [x] DELETE `/api/apply-correction/{page_id}`
- [x] DELETE `/api/revert-correction/{page_id}`
- [x] DELETE `/api/verify/batch`
- [x] DELETE `/api/verify/status`
- [x] DELETE `/api/unverified`
- [x] DELETE `batch_verify_pages()` background task
- [x] DELETE `verification_status` global
- [x] DELETE `VerifyRequest` model

### Backend (gemini_service.py)
- [x] DELETE `verify_regions()` function

### Frontend
- [x] DELETE Verify button
- [x] DELETE Apply Fix button
- [x] DELETE Revert button
- [x] DELETE verification status badges (🟢/🟡)
- [x] DELETE human guidance input
- [x] DELETE Verify All sidebar button

### Files
- [x] DELETE `prompts/verify_v1.txt`

## Added (Manual BBox Editor)

### Backend (main.py)
- [x] ADD `PUT /api/regions/{page_id}` — update regions for a page

### Backend (database.py)
- [x] ADD `update_regions()` function

### Frontend (app.js)
- [x] Canvas overlay on page image (existing)
- [x] Click box to select (highlight selected)
- [x] Drag edges to resize
- [x] Drag corners to resize
- [x] Drag center to move box
- [x] Save button → PUT to backend
- [x] Cancel button to exit edit mode
- [x] Visual feedback (cursor changes, selection highlight, handles)

### UI Flow
1. User clicks "Edit Boxes" on a processed page
2. Image shows boxes with selection enabled
3. Click a box to select it (shows resize handles)
4. Drag handles to resize, drag box to move
5. Click "Save" to persist changes
6. Changes saved to DB via PUT /api/regions/{page_id}

## Files Modified
- `main.py` — removed verification endpoints, added regions update
- `gemini_service.py` — removed verify_regions
- `database.py` — added update_regions
- `frontend/app.js` — removed verification UI, added bbox editor
- `frontend/index.html` — replaced verification buttons with edit buttons
- `frontend/styles.css` — added editor styles, removed verification styles
- `prompts/verify_v1.txt` — DELETED
