/**
 * Brain Mode Tuner - Frontend Application
 */

// ============================================================================
// State
// ============================================================================

const state = {
    currentView: 'dashboard',
    selectedPage: null,
    selectedResult: null,
    showRegions: true,
    prompts: [],
    currentPromptId: null,
    pollingInterval: null,
    enrichPollingInterval: null,
    // BBox editor state
    editMode: false,
    selectedRegionIndex: null,
    dragState: null,
    editedRegions: null,
};

// ============================================================================
// API
// ============================================================================

const api = {
    async get(endpoint) {
        const res = await fetch(`/api${endpoint}`);
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },
    
    async post(endpoint, data = {}) {
        const res = await fetch(`/api${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    },
    
    async put(endpoint, data = {}) {
        const res = await fetch(`/api${endpoint}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    }
};

// ============================================================================
// Toast Notifications
// ============================================================================

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.remove();
    }, 4000);
}

// ============================================================================
// Navigation
// ============================================================================

function initNavigation() {
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const view = btn.dataset.view;
            switchView(view);
        });
    });
}

function switchView(viewName) {
    state.currentView = viewName;
    
    // Update nav buttons
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.view === viewName);
    });
    
    // Update views
    document.querySelectorAll('.view').forEach(view => {
        view.classList.toggle('active', view.id === `${viewName}-view`);
    });
    
    // Load view data
    switch (viewName) {
        case 'dashboard':
            loadDashboard();
            break;
        case 'pages':
            loadPages();
            break;
        case 'prompts':
            loadPrompts();
            break;
        case 'stats':
            loadStats();
            break;
    }
}

// ============================================================================
// Dashboard
// ============================================================================

async function loadDashboard() {
    try {
        const stats = await api.get('/stats');
        
        document.getElementById('stat-total-pages').textContent = stats.total_pages || 0;
        document.getElementById('stat-processed').textContent = stats.processed_pages || 0;
        document.getElementById('stat-success-rate').textContent = 
            stats.success_rate ? `${(stats.success_rate * 100).toFixed(1)}%` : '-';
        document.getElementById('stat-avg-time').textContent = 
            stats.avg_processing_time_ms ? Math.round(stats.avg_processing_time_ms) : '-';
        
        await loadDisciplines();
        await updateBatchStatus();
    } catch (err) {
        showToast('Failed to load dashboard: ' + err.message, 'error');
    }
}

async function loadDisciplines() {
    try {
        const data = await api.get('/disciplines');
        const container = document.getElementById('disciplines-list');
        const filterSelect = document.getElementById('filter-discipline');
        const batchSelect = document.getElementById('batch-discipline');
        
        container.innerHTML = '';
        filterSelect.innerHTML = '<option value="">All Disciplines</option>';
        batchSelect.innerHTML = '';
        
        for (const disc of data.disciplines) {
            // Sidebar list
            const item = document.createElement('div');
            item.className = 'discipline-item';
            item.innerHTML = `
                <span class="name">${disc.discipline}</span>
                <span class="count">${disc.processed_count || 0}/${disc.page_count}</span>
            `;
            item.addEventListener('click', () => {
                document.getElementById('filter-discipline').value = disc.discipline;
                switchView('pages');
                loadPages();
            });
            container.appendChild(item);
            
            // Filter dropdown
            const option = document.createElement('option');
            option.value = disc.discipline;
            option.textContent = disc.discipline;
            filterSelect.appendChild(option.cloneNode(true));
            batchSelect.appendChild(option);
        }
    } catch (err) {
        console.error('Failed to load disciplines:', err);
    }
}

async function updateBatchStatus() {
    try {
        const status = await api.get('/process/status');
        const container = document.getElementById('batch-status');
        const indicator = document.getElementById('processing-indicator');
        
        if (status.active) {
            indicator.classList.remove('hidden');
            const progress = status.total > 0 ? (status.completed / status.total * 100) : 0;
            container.innerHTML = `
                <p><strong>Processing:</strong> ${status.current_page || '...'}</p>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: ${progress}%"></div>
                </div>
                <p class="status-text">${status.completed} of ${status.total} pages (${progress.toFixed(1)}%)</p>
                ${status.errors.length > 0 ? `<p class="status-text" style="color: var(--error)">${status.errors.length} errors</p>` : ''}
            `;
        } else {
            indicator.classList.add('hidden');
            container.innerHTML = '<p>No batch processing active</p>';
        }
    } catch (err) {
        console.error('Failed to get batch status:', err);
    }
}

// ============================================================================
// Pages
// ============================================================================

async function loadPages() {
    try {
        const discipline = document.getElementById('filter-discipline').value;
        const processed = document.getElementById('filter-processed').value;
        
        let url = '/pages?limit=200';
        if (discipline) url += `&discipline=${encodeURIComponent(discipline)}`;
        if (processed) url += `&processed=${processed}`;
        
        const data = await api.get(url);
        const container = document.getElementById('pages-grid');
        
        container.innerHTML = '';
        
        for (const page of data.pages) {
            const card = document.createElement('div');
            card.className = 'page-card';
            card.innerHTML = `
                <img class="thumbnail" src="${page.thumbnail_url || ''}" alt="${page.page_name}" loading="lazy">
                <div class="info">
                    <div class="name" title="${page.page_name}">${page.page_name}</div>
                    <div class="meta">
                        <span>${page.discipline}</span>
                        <span class="status ${page.result_count > 0 ? 'processed' : ''}"></span>
                    </div>
                </div>
            `;
            card.addEventListener('click', () => openPageDetail(page.id));
            container.appendChild(card);
        }
        
        if (data.pages.length === 0) {
            container.innerHTML = '<p style="grid-column: 1/-1; text-align: center; color: var(--text-secondary);">No pages found. Click "Scan PDFs" to discover pages.</p>';
        }
    } catch (err) {
        showToast('Failed to load pages: ' + err.message, 'error');
    }
}

// ============================================================================
// Page Detail Modal
// ============================================================================

async function openPageDetail(pageId) {
    const modal = document.getElementById('page-modal');
    modal.classList.remove('hidden');

    // Exit edit mode when opening new page
    exitEditMode();

    // Clear stale enrichment polling
    if (state.enrichPollingInterval) {
        clearInterval(state.enrichPollingInterval);
        state.enrichPollingInterval = null;
    }
    document.getElementById('enrichment-status').classList.add('hidden');

    // Clear stale state before loading new page
    state.selectedPage = null;
    state.selectedResult = null;
    state.imageScale = null;
    document.getElementById('page-name').textContent = 'Loading...';
    document.getElementById('page-discipline').textContent = '';
    document.getElementById('page-image').src = '';
    document.getElementById('page-image').onload = null;
    clearResult();
    clearRegions();

    try {
        const page = await api.get(`/pages/${pageId}`);
        state.selectedPage = page;
        
        // Set page info
        document.getElementById('page-name').textContent = page.page_name;
        document.getElementById('page-discipline').textContent = page.discipline;
        document.getElementById('page-image').src = page.image_url;
        
        // Store image dimensions for overlay scaling
        const img = document.getElementById('page-image');
        img.onload = () => {
            state.imageScale = {
                displayWidth: img.clientWidth,
                displayHeight: img.clientHeight,
                naturalWidth: page.width,
                naturalHeight: page.height,
            };
            if (state.selectedResult) {
                renderRegions(state.selectedResult.regions || []);
            }
        };
        
        // Load results
        const resultData = await api.get(`/results/${pageId}`);
        if (resultData.results.length > 0) {
            state.selectedResult = resultData.results[0];
            displayResult(state.selectedResult);
            renderResultsHistory(resultData.results);
            
            // Load enrichments if they exist
            try {
                await loadEnrichments(state.selectedResult.id);
            } catch (e) {
                // No enrichments yet, that's fine
            }
        } else {
            clearResult();
        }
    } catch (err) {
        showToast('Failed to load page: ' + err.message, 'error');
    }
}

function clearResult() {
    state.selectedResult = null;
    document.getElementById('sheet-reflection').innerHTML = '<p class="placeholder">No results yet. Click "Process" to analyze.</p>';
    document.getElementById('page-type-badge').textContent = '-';
    document.getElementById('processing-time').textContent = '-';
    document.getElementById('cross-refs').innerHTML = '';
    document.getElementById('regions-list').innerHTML = '<p class="placeholder">No regions detected.</p>';
    document.getElementById('raw-json').querySelector('code').textContent = '{}';
    document.getElementById('results-history').innerHTML = '<p class="placeholder">No processing history.</p>';
    clearRegions();
}

function displayResult(result) {
    // Get the raw response for the full index data
    const raw = result.raw_response || result;
    const index = raw.index || {};
    
    // Sheet reflection / summary (markdown)
    const reflection = result.sheet_reflection || raw.sheet_reflection || '';
    let reflectionHTML = marked.parse(reflection);
    
    // Add index sections if present
    if (index.keywords && index.keywords.length > 0) {
        reflectionHTML += `
            <div class="index-section">
                <strong>🔍 Keywords:</strong>
                <div class="keyword-tags">${index.keywords.map(k => `<span class="keyword-tag">${k}</span>`).join('')}</div>
            </div>`;
    }
    
    if (index.items && index.items.length > 0) {
        reflectionHTML += `
            <div class="index-section">
                <strong>📦 Items:</strong>
                <ul class="items-list">${index.items.map(item => `
                    <li><strong>${item.name}</strong> — ${item.action || 'shown'}${item.location ? ` @ ${item.location}` : ''}${item.keynote ? ` (KN ${item.keynote})` : ''}</li>
                `).join('')}</ul>
            </div>`;
    }
    
    if (index.areas_shown && index.areas_shown.length > 0) {
        reflectionHTML += `
            <div class="index-section">
                <strong>📍 Areas:</strong>
                <div class="areas-list">${index.areas_shown.map(a => 
                    typeof a === 'string' ? `<span class="area-tag">${a}</span>` : 
                    `<span class="area-tag" title="${a.notes || ''}">${a.name}</span>`
                ).join('')}</div>
            </div>`;
    }
    
    if (index.keynotes && index.keynotes.length > 0) {
        reflectionHTML += `
            <div class="index-section">
                <strong>📝 Keynotes:</strong>
                <ul class="keynotes-list">${index.keynotes.map(kn => `
                    <li><strong>${kn.number}:</strong> ${kn.text}</li>
                `).join('')}</ul>
            </div>`;
    }
    
    const questions = raw.questions_this_sheet_answers || [];
    if (questions.length > 0) {
        reflectionHTML += `
            <div class="index-section">
                <strong>❓ Questions This Answers:</strong>
                <ul class="questions-list">${questions.map(q => `<li>${q}</li>`).join('')}</ul>
            </div>`;
    }
    
    document.getElementById('sheet-reflection').innerHTML = reflectionHTML;
    
    // Meta info
    document.getElementById('page-type-badge').textContent = result.page_type || '-';
    document.getElementById('processing-time').textContent = 
        result.processing_time_ms ? `${result.processing_time_ms}ms` : '-';
    
    // Cross references (with context if available)
    const crossRefs = result.cross_references || [];
    const indexRefs = index.cross_references || [];
    const refsContainer = document.getElementById('cross-refs');
    if (crossRefs.length > 0 || indexRefs.length > 0) {
        // Prefer index refs with context
        if (indexRefs.length > 0 && typeof indexRefs[0] === 'object') {
            refsContainer.innerHTML = '<strong>Cross References:</strong> ' + 
                indexRefs.map(ref => `<span class="ref-tag" title="${ref.context || ''}">${ref.sheet}</span>`).join('');
        } else {
            refsContainer.innerHTML = '<strong>Cross References:</strong> ' + 
                crossRefs.map(ref => `<span class="ref-tag">${ref}</span>`).join('');
        }
    } else {
        refsContainer.innerHTML = '';
    }
    
    // Regions list
    const regions = result.regions || [];
    renderRegionsList(regions);
    
    // Raw JSON
    document.getElementById('raw-json').querySelector('code').textContent = 
        JSON.stringify(result.raw_response || result, null, 2);
    
    // Render regions on image
    if (state.showRegions) {
        renderRegions(regions);
    }
}

function renderRegionsList(regions) {
    const regionsList = document.getElementById('regions-list');
    if (regions.length > 0) {
        regionsList.innerHTML = regions.map((r, i) => `
            <div class="region-item ${state.selectedRegionIndex === i ? 'selected' : ''}" data-index="${i}">
                <div class="type">${r.type}${r.detail_number ? ` #${r.detail_number}` : ''}</div>
                <div class="label">${r.label || 'No label'}</div>
                <div class="confidence">Confidence: ${(r.confidence * 100).toFixed(0)}%</div>
                ${r.contains ? `<div class="contains">Contains: ${r.contains.join(', ')}</div>` : ''}
            </div>
        `).join('');
        
        // Add click/hover listeners
        regionsList.querySelectorAll('.region-item').forEach(item => {
            item.addEventListener('mouseenter', () => {
                if (!state.editMode) {
                    const idx = parseInt(item.dataset.index);
                    highlightRegion(idx);
                }
            });
            item.addEventListener('mouseleave', () => {
                if (!state.editMode) {
                    clearHighlight();
                }
            });
            item.addEventListener('click', () => {
                if (state.editMode) {
                    const idx = parseInt(item.dataset.index);
                    selectRegion(idx);
                }
            });
        });
    } else {
        regionsList.innerHTML = '<p class="placeholder">No regions detected.</p>';
    }
}

function renderResultsHistory(results) {
    const container = document.getElementById('results-history');
    if (results.length === 0) {
        container.innerHTML = '<p class="placeholder">No processing history.</p>';
        return;
    }
    
    container.innerHTML = results.map(r => `
        <div class="history-item" data-result='${JSON.stringify(r).replace(/'/g, "\\'")}'>
            <div class="prompt-name">${r.prompt_name || 'Default'}</div>
            <div class="time">${new Date(r.created_at).toLocaleString()} • ${r.processing_time_ms}ms • ${r.success ? '✓' : '✗'}</div>
        </div>
    `).join('');
    
    container.querySelectorAll('.history-item').forEach(item => {
        item.addEventListener('click', () => {
            const result = JSON.parse(item.dataset.result);
            state.selectedResult = result;
            displayResult(result);
        });
    });
}

// ============================================================================
// Region Overlay
// ============================================================================

function renderRegions(regions) {
    const svg = document.getElementById('region-overlay');
    const img = document.getElementById('page-image');

    if (!state.imageScale || !regions.length) {
        svg.innerHTML = '';
        return;
    }

    const scale = state.imageScale;

    // Set SVG to match image displayed size exactly
    svg.setAttribute('width', scale.displayWidth);
    svg.setAttribute('height', scale.displayHeight);
    svg.style.width = scale.displayWidth + 'px';
    svg.style.height = scale.displayHeight + 'px';

    // Gemini outputs 0-1000 normalized coords, convert to display coords
    const scaleX = scale.displayWidth / 1000;
    const scaleY = scale.displayHeight / 1000;

    svg.innerHTML = regions.map((r, i) => {
        const bbox = r.bbox || {};
        const x = (bbox.x0 || 0) * scaleX;
        const y = (bbox.y0 || 0) * scaleY;
        const w = ((bbox.x1 || 0) - (bbox.x0 || 0)) * scaleX;
        const h = ((bbox.y1 || 0) - (bbox.y0 || 0)) * scaleY;
        
        const isSelected = state.editMode && state.selectedRegionIndex === i;
        const selectedClass = isSelected ? 'selected' : '';

        let handles = '';
        if (state.editMode && isSelected) {
            // Draw resize handles for selected region
            handles = `
                <rect class="handle nw" x="${x - 5}" y="${y - 5}" width="10" height="10" data-handle="nw" data-index="${i}"/>
                <rect class="handle ne" x="${x + w - 5}" y="${y - 5}" width="10" height="10" data-handle="ne" data-index="${i}"/>
                <rect class="handle sw" x="${x - 5}" y="${y + h - 5}" width="10" height="10" data-handle="sw" data-index="${i}"/>
                <rect class="handle se" x="${x + w - 5}" y="${y + h - 5}" width="10" height="10" data-handle="se" data-index="${i}"/>
                <rect class="handle n" x="${x + w/2 - 5}" y="${y - 5}" width="10" height="10" data-handle="n" data-index="${i}"/>
                <rect class="handle s" x="${x + w/2 - 5}" y="${y + h - 5}" width="10" height="10" data-handle="s" data-index="${i}"/>
                <rect class="handle e" x="${x + w - 5}" y="${y + h/2 - 5}" width="10" height="10" data-handle="e" data-index="${i}"/>
                <rect class="handle w" x="${x - 5}" y="${y + h/2 - 5}" width="10" height="10" data-handle="w" data-index="${i}"/>
            `;
        }

        return `
            <rect class="region-box ${r.type} ${selectedClass}" x="${x}" y="${y}" width="${w}" height="${h}" data-index="${i}"/>
            <text class="region-label" x="${x + 5}" y="${y + 15}">${r.label || r.type}</text>
            ${handles}
        `;
    }).join('');
    
    // Add event listeners for edit mode
    if (state.editMode) {
        initEditModeListeners();
    }
}

function clearRegions() {
    document.getElementById('region-overlay').innerHTML = '';
}

function highlightRegion(index) {
    const boxes = document.querySelectorAll('.region-box');
    boxes.forEach((box, i) => {
        box.style.opacity = i === index ? 1 : 0.3;
        if (i === index) {
            box.style.strokeWidth = '4';
        }
    });
}

function clearHighlight() {
    const boxes = document.querySelectorAll('.region-box');
    boxes.forEach(box => {
        box.style.opacity = 1;
        box.style.strokeWidth = '2';
    });
}

// ============================================================================
// BBox Editor
// ============================================================================

function enterEditMode() {
    if (!state.selectedResult || !state.selectedResult.regions) {
        showToast('No regions to edit. Process the page first.', 'error');
        return;
    }
    
    state.editMode = true;
    state.editedRegions = JSON.parse(JSON.stringify(state.selectedResult.regions)); // Deep copy
    state.selectedRegionIndex = null;
    
    // Update UI
    const editBtn = document.getElementById('edit-boxes-btn');
    const saveBtn = document.getElementById('save-boxes-btn');
    const cancelBtn = document.getElementById('cancel-edit-btn');
    const container = document.getElementById('page-modal').querySelector('.page-image-container');
    
    if (editBtn) editBtn.classList.add('hidden');
    if (saveBtn) saveBtn.classList.remove('hidden');
    if (cancelBtn) cancelBtn.classList.remove('hidden');
    if (container) container.classList.add('edit-mode');
    
    renderRegions(state.editedRegions);
    renderRegionsList(state.editedRegions);
    
    showToast('Edit mode: Click a box to select, drag edges to resize', 'info');
}

function exitEditMode() {
    state.editMode = false;
    state.editedRegions = null;
    state.selectedRegionIndex = null;
    state.dragState = null;
    
    // Update UI
    const editBtn = document.getElementById('edit-boxes-btn');
    const saveBtn = document.getElementById('save-boxes-btn');
    const cancelBtn = document.getElementById('cancel-edit-btn');
    const container = document.getElementById('page-modal')?.querySelector('.page-image-container');
    
    if (editBtn) editBtn.classList.remove('hidden');
    if (saveBtn) saveBtn.classList.add('hidden');
    if (cancelBtn) cancelBtn.classList.add('hidden');
    if (container) container.classList.remove('edit-mode');
    
    if (state.selectedResult) {
        renderRegions(state.selectedResult.regions || []);
        renderRegionsList(state.selectedResult.regions || []);
    }
}

async function saveEditedRegions() {
    if (!state.editedRegions || !state.selectedPage) return;
    
    const btn = document.getElementById('save-boxes-btn');
    btn.textContent = '⏳ Saving...';
    btn.disabled = true;
    
    try {
        await api.put(`/regions/${state.selectedPage.id}`, { regions: state.editedRegions });
        
        // Update local state
        state.selectedResult.regions = state.editedRegions;
        
        showToast('Regions saved!', 'success');
        exitEditMode();
        
        // Reload to get fresh data
        const resultData = await api.get(`/results/${state.selectedPage.id}`);
        if (resultData.results.length > 0) {
            state.selectedResult = resultData.results[0];
            displayResult(state.selectedResult);
        }
    } catch (err) {
        showToast('Failed to save: ' + err.message, 'error');
    } finally {
        btn.textContent = '💾 Save';
        btn.disabled = false;
    }
}

function selectRegion(index) {
    state.selectedRegionIndex = index;
    renderRegions(state.editedRegions);
    renderRegionsList(state.editedRegions);
}

function initEditModeListeners() {
    // Using event delegation on SVG - single listener handles all
    const svg = document.getElementById('region-overlay');
    
    // Remove old listener if exists
    svg.removeEventListener('mousedown', handleSvgMouseDown);
    svg.addEventListener('mousedown', handleSvgMouseDown);
}

function handleSvgMouseDown(e) {
    if (!state.editMode) return;
    
    const target = e.target;
    
    // Check if clicked on a handle (priority)
    if (target.classList.contains('handle')) {
        e.stopPropagation();
        e.preventDefault();
        const index = parseInt(target.dataset.index);
        const handleType = target.dataset.handle;
        
        console.log('Handle clicked:', handleType, 'for region', index);
        
        state.dragState = {
            type: 'resize',
            handle: handleType,
            index: index,
            startX: e.clientX,
            startY: e.clientY,
            originalBbox: { ...state.editedRegions[index].bbox }
        };
        return;
    }
    
    // Check if clicked on a box
    if (target.classList.contains('region-box')) {
        e.stopPropagation();
        const index = parseInt(target.dataset.index);
        
        console.log('Box clicked:', index);
        
        // Select the region
        selectRegion(index);
        
        // Start drag to move
        state.dragState = {
            type: 'move',
            index: index,
            startX: e.clientX,
            startY: e.clientY,
            originalBbox: { ...state.editedRegions[index].bbox }
        };
        return;
    }
    
    // Clicked on empty space - deselect
    if (target.tagName === 'svg') {
        state.selectedRegionIndex = null;
        renderRegions(state.editedRegions);
        renderRegionsList(state.editedRegions);
    }
}

function handleMouseMove(e) {
    if (!state.dragState || !state.editMode) return;
    
    const scale = state.imageScale;
    const scaleX = 1000 / scale.displayWidth;
    const scaleY = 1000 / scale.displayHeight;
    
    const dx = (e.clientX - state.dragState.startX) * scaleX;
    const dy = (e.clientY - state.dragState.startY) * scaleY;
    
    const region = state.editedRegions[state.dragState.index];
    const orig = state.dragState.originalBbox;
    
    if (state.dragState.type === 'move') {
        region.bbox.x0 = Math.max(0, Math.min(1000, orig.x0 + dx));
        region.bbox.y0 = Math.max(0, Math.min(1000, orig.y0 + dy));
        region.bbox.x1 = Math.max(0, Math.min(1000, orig.x1 + dx));
        region.bbox.y1 = Math.max(0, Math.min(1000, orig.y1 + dy));
    } else if (state.dragState.type === 'resize') {
        const h = state.dragState.handle;
        
        if (h.includes('n')) region.bbox.y0 = Math.max(0, Math.min(region.bbox.y1 - 10, orig.y0 + dy));
        if (h.includes('s')) region.bbox.y1 = Math.max(region.bbox.y0 + 10, Math.min(1000, orig.y1 + dy));
        if (h.includes('w')) region.bbox.x0 = Math.max(0, Math.min(region.bbox.x1 - 10, orig.x0 + dx));
        if (h.includes('e')) region.bbox.x1 = Math.max(region.bbox.x0 + 10, Math.min(1000, orig.x1 + dx));
    }
    
    renderRegions(state.editedRegions);
}

function handleMouseUp() {
    state.dragState = null;
}

// ============================================================================
// Processing
// ============================================================================

async function processCurrentPage() {
    if (!state.selectedPage) return;
    
    // Exit edit mode if active
    if (state.editMode) exitEditMode();
    
    const btn = document.getElementById('process-btn');
    btn.textContent = '⏳ Processing...';
    btn.disabled = true;
    
    try {
        await api.post(`/process/${state.selectedPage.id}`);
        showToast('Processing complete!', 'success');

        // Reload results from DB (gives us proper `id` field)
        const resultData = await api.get(`/results/${state.selectedPage.id}`);
        if (resultData.results.length > 0) {
            state.selectedResult = resultData.results[0];
            displayResult(state.selectedResult);
        }
        renderResultsHistory(resultData.results);
    } catch (err) {
        showToast('Processing failed: ' + err.message, 'error');
    } finally {
        btn.textContent = '🧠 Pass 1';
        btn.disabled = false;
    }
}

// ============================================================================
// Pass 2 - Enrichment
// ============================================================================

async function enrichCurrentPage() {
    if (!state.selectedPage) return;
    if (!state.selectedResult) {
        showToast('Run Pass 1 first before enriching', 'error');
        return;
    }
    
    const btn = document.getElementById('enrich-btn');
    btn.textContent = '⏳ Starting...';
    btn.disabled = true;
    
    try {
        const resultId = state.selectedResult.id || state.selectedResult.result_id;
        const result = await api.post(`/enrich/${resultId}`);
        showToast(`Started Pass 2 enrichment for ${result.region_count} regions`, 'success');
        
        // Switch to enrichments tab
        document.querySelector('[data-tab="enrichments"]').click();
        
        // Start polling for status
        startEnrichmentPolling(result.result_id);
    } catch (err) {
        showToast('Enrichment failed: ' + err.message, 'error');
        btn.textContent = '🔬 Pass 2';
        btn.disabled = false;
    }
}

async function enrichSingleRegion(resultId, regionIndex) {
    try {
        await api.post(`/enrich/region/${resultId}/${regionIndex}`);
        showToast(`Started Pass 2 for region ${regionIndex}`, 'success');
        startEnrichmentPolling(resultId);
    } catch (err) {
        showToast('Enrichment failed: ' + err.message, 'error');
    }
}

function startEnrichmentPolling(resultId) {
    if (state.enrichPollingInterval) {
        clearInterval(state.enrichPollingInterval);
    }
    
    const statusDiv = document.getElementById('enrichment-status');
    statusDiv.classList.remove('hidden');
    
    state.enrichPollingInterval = setInterval(async () => {
        try {
            const status = await api.get('/enrich/status');

            // Ignore status from a different result's enrichment
            if (status.result_id && status.result_id !== resultId) {
                return;
            }

            document.getElementById('enrich-current').textContent = status.current_region || '...';
            document.getElementById('enrich-completed').textContent = status.completed;
            document.getElementById('enrich-total').textContent = status.total;
            
            const progress = status.total > 0 ? (status.completed / status.total * 100) : 0;
            document.getElementById('enrich-progress').style.width = `${progress}%`;
            
            if (!status.active) {
                clearInterval(state.enrichPollingInterval);
                state.enrichPollingInterval = null;
                statusDiv.classList.add('hidden');
                
                document.getElementById('enrich-btn').textContent = '🔬 Pass 2';
                document.getElementById('enrich-btn').disabled = false;
                
                // Reload enrichments
                await loadEnrichments(resultId);
                showToast('Pass 2 enrichment complete!', 'success');
            }
        } catch (err) {
            console.error('Enrichment polling error:', err);
        }
    }, 1500);
}

async function loadEnrichments(resultId) {
    try {
        const data = await api.get(`/enrichments/${resultId}`);
        renderEnrichmentsList(data.enrichments, data.stats);
    } catch (err) {
        console.error('Failed to load enrichments:', err);
    }
}

function renderEnrichmentsList(enrichments, stats) {
    const container = document.getElementById('enrichments-list');
    
    if (!enrichments || enrichments.length === 0) {
        container.innerHTML = '<p class="placeholder">No enrichments yet. Click "🔬 Pass 2" to enrich regions.</p>';
        return;
    }
    
    // Stats header
    let html = `
        <div class="enrichment-stats">
            <span class="stat">✓ ${stats.complete} complete</span>
            ${stats.failed > 0 ? `<span class="stat error">✗ ${stats.failed} failed</span>` : ''}
            <span class="stat">⏱ ${Math.round(stats.avg_time_ms)}ms avg</span>
        </div>
    `;
    
    // Enrichment cards
    html += enrichments.map(e => `
        <div class="enrichment-card ${e.status}" data-region-index="${e.region_index}">
            <div class="enrichment-header">
                <span class="region-id">${e.region_id}</span>
                <span class="status-badge ${e.status}">${e.status === 'complete' ? '✓' : '✗'}</span>
                ${e.processing_time_ms ? `<span class="time">${e.processing_time_ms}ms</span>` : ''}
            </div>
            ${e.status === 'complete' ? `
                <div class="enrichment-content">
                    <div class="markdown-preview">${marked.parse(e.content_markdown || '')}</div>
                    ${e.cropped_png_url ? `<img class="cropped-preview" src="${e.cropped_png_url}" alt="Cropped region">` : ''}
                </div>
                <div class="enrichment-fields">
                    ${e.structured_fields.materials ? `<div class="field"><strong>Materials:</strong> ${e.structured_fields.materials.join(', ')}</div>` : ''}
                    ${e.structured_fields.dimensions ? `<div class="field"><strong>Dimensions:</strong> ${e.structured_fields.dimensions.join(', ')}</div>` : ''}
                    ${e.structured_fields.coordination_notes ? `<div class="field"><strong>Coordination:</strong> ${e.structured_fields.coordination_notes.join('; ')}</div>` : ''}
                </div>
            ` : `
                <div class="error-message">${e.error_message || 'Unknown error'}</div>
            `}
        </div>
    `).join('');
    
    container.innerHTML = html;
    
    // Add click handlers for region highlighting
    container.querySelectorAll('.enrichment-card').forEach(card => {
        card.addEventListener('mouseenter', () => {
            const idx = parseInt(card.dataset.regionIndex);
            highlightRegion(idx);
        });
        card.addEventListener('mouseleave', () => {
            clearHighlight();
        });
    });
}

// ============================================================================
// Prompts
// ============================================================================

async function loadPrompts() {
    try {
        const data = await api.get('/prompts');
        state.prompts = data.prompts;
        
        const container = document.getElementById('prompts-list');
        container.innerHTML = state.prompts.map(p => `
            <div class="prompt-item ${p.is_active ? 'active' : ''}" data-id="${p.id}">
                <div class="name">${p.name}${p.is_active ? ' ✓' : ''}</div>
                <div class="date">${new Date(p.created_at).toLocaleDateString()}</div>
            </div>
        `).join('');
        
        container.querySelectorAll('.prompt-item').forEach(item => {
            item.addEventListener('click', () => loadPromptForEdit(parseInt(item.dataset.id)));
        });
        
        // Load active prompt into editor
        const active = state.prompts.find(p => p.is_active);
        if (active) {
            loadPromptForEdit(active.id);
        }
    } catch (err) {
        showToast('Failed to load prompts: ' + err.message, 'error');
    }
}

async function loadPromptForEdit(promptId) {
    try {
        const prompt = await api.get(`/prompts/${promptId}`);
        state.currentPromptId = promptId;
        
        document.getElementById('prompt-name').value = prompt.name + ' (copy)';
        document.getElementById('prompt-text').value = prompt.prompt_text;
        
        // Update selection
        document.querySelectorAll('.prompt-item').forEach(item => {
            item.classList.toggle('selected', parseInt(item.dataset.id) === promptId);
        });
    } catch (err) {
        showToast('Failed to load prompt: ' + err.message, 'error');
    }
}

async function savePrompt() {
    const name = document.getElementById('prompt-name').value.trim();
    const text = document.getElementById('prompt-text').value.trim();
    
    if (!name || !text) {
        showToast('Please enter a name and prompt text', 'error');
        return;
    }
    
    try {
        await api.post('/prompts', {
            name,
            prompt_text: text,
            set_active: true
        });
        showToast('Prompt saved and activated!', 'success');
        loadPrompts();
    } catch (err) {
        showToast('Failed to save prompt: ' + err.message, 'error');
    }
}

// ============================================================================
// Stats
// ============================================================================

async function loadStats() {
    try {
        const stats = await api.get('/stats');
        
        // By discipline
        const discTable = document.getElementById('stats-by-discipline');
        if (stats.by_discipline && stats.by_discipline.length > 0) {
            discTable.innerHTML = `
                <table>
                    <thead>
                        <tr>
                            <th>Discipline</th>
                            <th>Pages</th>
                            <th>Processed</th>
                            <th>Avg Time</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${stats.by_discipline.map(d => `
                            <tr>
                                <td>${d.discipline}</td>
                                <td>${d.page_count}</td>
                                <td>${d.processed_count || 0}</td>
                                <td>${d.avg_time_ms ? Math.round(d.avg_time_ms) + 'ms' : '-'}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            `;
        }
        
        // By page type
        const typeTable = document.getElementById('stats-by-type');
        if (stats.by_page_type && stats.by_page_type.length > 0) {
            typeTable.innerHTML = `
                <table>
                    <thead>
                        <tr>
                            <th>Page Type</th>
                            <th>Count</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${stats.by_page_type.map(t => `
                            <tr>
                                <td>${t.page_type}</td>
                                <td>${t.count}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            `;
        }
    } catch (err) {
        showToast('Failed to load stats: ' + err.message, 'error');
    }
}

// ============================================================================
// Scanning & Batch Processing
// ============================================================================

async function scanPdfs() {
    const btn = document.getElementById('scan-btn');
    btn.textContent = '⏳ Scanning...';
    btn.disabled = true;
    
    try {
        const result = await api.get('/scan');
        showToast(`Found ${result.pdfs_found} PDFs, indexed ${result.pages_indexed} pages`, 'success');
        loadDashboard();
        loadPages();
    } catch (err) {
        showToast('Scan failed: ' + err.message, 'error');
    } finally {
        btn.textContent = '🔍 Scan PDFs';
        btn.disabled = false;
    }
}

function openBatchModal() {
    document.getElementById('batch-modal').classList.remove('hidden');
}

async function startBatchProcessing() {
    const selection = document.querySelector('input[name="batch-select"]:checked').value;
    let pageIds = [];
    
    try {
        let url = '/pages?limit=500';
        
        if (selection === 'unprocessed') {
            url += '&processed=false';
        } else if (selection === 'discipline') {
            const disc = document.getElementById('batch-discipline').value;
            url += `&discipline=${encodeURIComponent(disc)}&processed=false`;
        }
        
        const data = await api.get(url);
        pageIds = data.pages.map(p => p.id);
        
        if (selection === 'custom') {
            const count = parseInt(document.getElementById('batch-count').value) || 10;
            pageIds = pageIds.slice(0, count);
        }
        
        if (pageIds.length === 0) {
            showToast('No pages to process', 'error');
            return;
        }
        
        await api.post('/process/batch', { page_ids: pageIds });
        showToast(`Started processing ${pageIds.length} pages`, 'success');
        document.getElementById('batch-modal').classList.add('hidden');
        
        // Start polling for status
        startStatusPolling();
    } catch (err) {
        showToast('Failed to start batch: ' + err.message, 'error');
    }
}

function startStatusPolling() {
    if (state.pollingInterval) return;
    
    state.pollingInterval = setInterval(async () => {
        await updateBatchStatus();
        
        const status = await api.get('/process/status');
        if (!status.active) {
            clearInterval(state.pollingInterval);
            state.pollingInterval = null;
            loadDashboard();
        }
    }, 2000);
}

// ============================================================================
// Event Listeners
// ============================================================================

function initEventListeners() {
    // Scan button
    document.getElementById('scan-btn').addEventListener('click', scanPdfs);
    
    // Batch button
    document.getElementById('batch-btn').addEventListener('click', openBatchModal);
    document.getElementById('start-batch-btn').addEventListener('click', startBatchProcessing);
    
    // Page filters
    document.getElementById('filter-discipline').addEventListener('change', loadPages);
    document.getElementById('filter-processed').addEventListener('change', loadPages);
    
    // Modal close buttons
    document.querySelectorAll('.modal-close, .cancel-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.target.closest('.modal').classList.add('hidden');
            if (state.editMode) exitEditMode();
            if (state.enrichPollingInterval) {
                clearInterval(state.enrichPollingInterval);
                state.enrichPollingInterval = null;
            }
        });
    });

    // Click outside modal to close
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.classList.add('hidden');
                if (state.editMode) exitEditMode();
                if (state.enrichPollingInterval) {
                    clearInterval(state.enrichPollingInterval);
                    state.enrichPollingInterval = null;
                }
            }
        });
    });
    
    // Process button
    document.getElementById('process-btn').addEventListener('click', processCurrentPage);
    
    // Enrich button (Pass 2)
    document.getElementById('enrich-btn').addEventListener('click', enrichCurrentPage);
    
    // BBox editor buttons
    document.getElementById('edit-boxes-btn').addEventListener('click', enterEditMode);
    document.getElementById('save-boxes-btn').addEventListener('click', saveEditedRegions);
    document.getElementById('cancel-edit-btn').addEventListener('click', exitEditMode);
    
    // Toggle regions
    document.getElementById('toggle-regions').addEventListener('click', (e) => {
        state.showRegions = !state.showRegions;
        e.target.classList.toggle('active', state.showRegions);
        if (state.showRegions && state.selectedResult) {
            renderRegions(state.editMode ? state.editedRegions : state.selectedResult.regions || []);
        } else {
            clearRegions();
        }
    });
    
    // Result tabs
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const tab = btn.dataset.tab;
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b === btn));
            document.querySelectorAll('.tab-pane').forEach(p => p.classList.toggle('active', p.id === `tab-${tab}`));
        });
    });
    
    // Prompt buttons
    document.getElementById('new-prompt-btn').addEventListener('click', () => {
        document.getElementById('prompt-name').value = 'New Prompt';
        document.getElementById('prompt-text').value = '';
        state.currentPromptId = null;
    });
    
    document.getElementById('save-prompt-btn').addEventListener('click', savePrompt);
    
    // Handle image resize for region overlay
    window.addEventListener('resize', () => {
        if (state.selectedPage && state.selectedResult) {
            const img = document.getElementById('page-image');
            state.imageScale = {
                displayWidth: img.clientWidth,
                displayHeight: img.clientHeight,
                naturalWidth: state.selectedPage.width,
                naturalHeight: state.selectedPage.height,
            };
            renderRegions(state.editMode ? state.editedRegions : state.selectedResult.regions || []);
        }
    });
    
    // Global mouse events for drag
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
}

// ============================================================================
// Initialize
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initEventListeners();
    loadDashboard();
    
    // Check for active batch processing
    updateBatchStatus().then(async () => {
        const status = await api.get('/process/status');
        if (status.active) {
            startStatusPolling();
        }
    });
});
