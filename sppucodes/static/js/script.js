// =============================================================================
// Configuration & Constants
// =============================================================================
const CONFIG = {
    COPY_FEEDBACK_DURATION: 3000,
    CACHE_ENABLED: true,
    LOG_LEVEL: 'info' // 'debug', 'info', 'warn', 'error'
};

// =============================================================================
// Logger Utility
// =============================================================================
const Logger = {
    levels: { debug: 0, info: 1, warn: 2, error: 3 },
    currentLevel: CONFIG.LOG_LEVEL,
    
    _shouldLog(level) {
        return this.levels[level] >= this.levels[this.currentLevel];
    },
    
    debug(message, ...args) {
        if (this._shouldLog('debug')) {
            console.debug(`[DEBUG] ${message}`, ...args);
        }
    },
    
    info(message, ...args) {
        if (this._shouldLog('info')) {
            console.info(`[INFO] ${message}`, ...args);
        }
    },
    
    warn(message, ...args) {
        if (this._shouldLog('warn')) {
            console.warn(`[WARN] ${message}`, ...args);
        }
    },
    
    error(message, ...args) {
        if (this._shouldLog('error')) {
            console.error(`[ERROR] ${message}`, ...args);
        }
    },
    
    group(label) {
        if (this._shouldLog('debug')) {
            console.group(label);
        }
    },
    
    groupEnd() {
        if (this._shouldLog('debug')) {
            console.groupEnd();
        }
    }
};



// =============================================================================
// Answer Cache Management
// =============================================================================
const AnswerCache = {
    _storage: window.sessionStorage,
    _stats: {
        hits: 0,
        misses: 0,
        total: 0
    },
    
    generateKey(subject, questionNo, fileIndex) {
        return `${subject}-${questionNo}-${fileIndex}`;
    },
    
    get(key) {
        this._stats.total++;
        try {
            const value = this._storage.getItem(key);
            if (value !== null) {
                this._stats.hits++;
                Logger.debug(`Cache HIT for key: ${key}`);
                return value;
            }
        } catch (error) {
            Logger.warn('Cache read failed', error);
        }
        this._stats.misses++;
        Logger.debug(`Cache MISS for key: ${key}`);
        return null;
    },
    
    set(key, value) {
        try {
            this._storage.setItem(key, value);
            Logger.debug(`Cache SET for key: ${key}, size: ${value.length} chars`);
        } catch (error) {
            Logger.warn('Cache write failed', error);
        }
    },
    
    clear() {
        try {
            this._storage.clear();
            Logger.info('Session cache cleared');
        } catch (error) {
            Logger.warn('Cache clear failed', error);
        }
    },
    
    getStats() {
        let size = 0;
        try {
            size = this._storage.length;
        } catch (error) {
            Logger.warn('Cache stats unavailable', error);
        }
        return {
            ...this._stats,
            hitRate: this._stats.total > 0 
                ? (this._stats.hits / this._stats.total * 100).toFixed(2) + '%'
                : '0%',
            size: size
        };
    },
    
    logStats() {
        const stats = this.getStats();
        Logger.group('Cache Statistics');
        Logger.info(`Total requests: ${stats.total}`);
        Logger.info(`Cache hits: ${stats.hits}`);
        Logger.info(`Cache misses: ${stats.misses}`);
        Logger.info(`Hit rate: ${stats.hitRate}`);
        Logger.info(`Cache size: ${stats.size} entries`);
        Logger.groupEnd();
    }
};

const ActiveRequests = {
    _requests: new Map(),

    get(key) {
        return this._requests.get(key) || null;
    },

    set(key, promise) {
        this._requests.set(key, promise);
        return promise;
    },

    delete(key) {
        this._requests.delete(key);
    }
};

const PrefetchManager = {
    _questionMeta: Array.isArray(window.subjectQuestionPrefetchMap) ? window.subjectQuestionPrefetchMap : [],
    _prefetchedQuestions: new Set(),

    prefetchNext(subject, currentQuestionNo) {
        const currentIndex = this._questionMeta.findIndex((item) => String(item) === String(currentQuestionNo));
        if (currentIndex === -1 || currentIndex >= this._questionMeta.length - 1) {
            return;
        }

        const nextQuestionNo = String(this._questionMeta[currentIndex + 1]);
        if (this._prefetchedQuestions.has(nextQuestionNo)) {
            return;
        }
        this._prefetchedQuestions.add(nextQuestionNo);

        fetchAnswerText(subject, nextQuestionNo, 1).catch((error) => {
            Logger.debug('Prefetch skipped after fetch error', error);
        });
    }
};

async function loadMarkedIfNeeded() {
    if (typeof marked !== 'undefined') {
        return;
    }

    Logger.info('marked.js not ready yet, loading on demand');
    await new Promise((resolve, reject) => {
        const existing = document.querySelector('script[data-marked-loader="true"]');
        if (existing) {
            existing.addEventListener('load', resolve, { once: true });
            existing.addEventListener('error', reject, { once: true });
            return;
        }

        const s = document.createElement('script');
        s.src = 'https://cdn.jsdelivr.net/npm/marked/marked.min.js';
        s.dataset.markedLoader = 'true';
        s.onload = resolve;
        s.onerror = reject;
        document.head.appendChild(s);
    });
}

async function fetchAnswerText(subject, questionNo, fileIndex) {
    const cacheKey = AnswerCache.generateKey(subject, questionNo, fileIndex);
    const cachedValue = CONFIG.CACHE_ENABLED ? AnswerCache.get(cacheKey) : null;
    if (cachedValue !== null) {
        return cachedValue;
    }

    const activeRequest = ActiveRequests.get(cacheKey);
    if (activeRequest) {
        Logger.debug(`Skipping duplicate request for key: ${cacheKey}`);
        return activeRequest;
    }

    const apiUrl = `/api/${subject}/${questionNo}?no_question=1&split=${fileIndex}`;
    Logger.debug(`Fetching from API: ${apiUrl}`);

    const requestPromise = fetch(apiUrl)
        .then((response) => {
            Logger.debug(`Response status: ${response.status} ${response.statusText}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            return response.text();
        })
        .then((text) => {
            const trimmedText = text.trim();
            if (CONFIG.CACHE_ENABLED) {
                AnswerCache.set(cacheKey, trimmedText);
            }
            return trimmedText;
        })
        .finally(() => {
            ActiveRequests.delete(cacheKey);
        });

    return ActiveRequests.set(cacheKey, requestPromise);
}

// =============================================================================
// Modal Management
// =============================================================================
const ModalManager = {
    _activeModal: null,
    _backdrop: null,
    
    init() {
        Logger.debug('Modal manager initialized');
    },
    
    show(answerBox) {
        if (!answerBox) {
            Logger.error('Cannot show modal: answerBox is null or undefined');
            return false;
        }
        
        if (!this._backdrop) {
            this._backdrop = document.createElement('div');
            this._backdrop.className = 'modal-backdrop';
            this._backdrop.setAttribute('role', 'presentation');
            this._backdrop.setAttribute('aria-hidden', 'true');
            document.body.appendChild(this._backdrop);
        }
        
        this._activeModal = answerBox;
        answerBox.style.display = 'block';
        answerBox.setAttribute('aria-hidden', 'false');
        
        if (this._backdrop) {
            this._backdrop.style.display = 'block';
            this._backdrop.setAttribute('aria-hidden', 'false');
        }
        
        document.body.style.overflow = 'hidden';
        Logger.info(`Modal opened: ${answerBox.id}`);
        return true;
    },
    
    hide(answerBox) {
        if (!answerBox) {
            Logger.error('Cannot hide modal: answerBox is null or undefined');
            return false;
        }
        
        answerBox.style.display = 'none';
        answerBox.setAttribute('aria-hidden', 'true');
        
        if (this._backdrop) {
            this._backdrop.style.display = 'none';
            this._backdrop.setAttribute('aria-hidden', 'true');
        }
        
        document.body.style.overflow = 'auto';
        this._activeModal = null;
        Logger.info(`Modal closed: ${answerBox.id}`);
        return true;
    },
    
    hideActive() {
        if (this._activeModal) {
            this.hide(this._activeModal);
        }
    }
};

// Initialize modal manager when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    ModalManager.init();
});

// =============================================================================
// Load Answer Function (API-driven with enhanced error handling)
// =============================================================================
function escapeNotebookHtml(value) {
    return String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

const PYTHON_KEYWORDS = new Set([
    'and', 'as', 'assert', 'async', 'await', 'break', 'class', 'continue', 'def',
    'del', 'elif', 'else', 'except', 'finally', 'for', 'from', 'global', 'if',
    'import', 'in', 'is', 'lambda', 'nonlocal', 'not', 'or', 'pass', 'raise',
    'return', 'try', 'while', 'with', 'yield'
]);
const PYTHON_CONSTANTS = new Set(['True', 'False', 'None']);

function highlightNotebookCode(source) {
    const tokens = String(source).match(/#[^\r\n]*|(?:[rRuUbBfF]{0,2})?(?:"""[\s\S]*?"""|'''[\s\S]*?'''|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b|\b[A-Za-z_]\w*\b|[\s\S]/g) || [];
    return tokens.map((token, index) => {
        let kind = '';
        if (token.startsWith('#')) kind = 'comment';
        else if (/^(?:[rRuUbBfF]{0,2})?["']/.test(token)) kind = 'string';
        else if (/^\d/.test(token)) kind = 'number';
        else if (PYTHON_KEYWORDS.has(token)) kind = 'keyword';
        else if (PYTHON_CONSTANTS.has(token)) kind = 'constant';
        else if (/^[A-Za-z_]\w*$/.test(token)) {
            let next = index + 1;
            while (next < tokens.length && /^\s+$/.test(tokens[next])) next++;
            if (tokens[next] === '(') kind = 'function';
        }
        const safe = escapeNotebookHtml(token);
        return kind ? `<span class="py-${kind}">${safe}</span>` : safe;
    }).join('');
}

function ensureNotebookOutputToggle(answerBox) {
    const existing = answerBox.querySelector('.notebook-output-toggle');
    if (existing) return existing;

    const footer = answerBox.querySelector('.copy-close-container');
    const downloadBtn = footer?.querySelector('.download-btn');
    if (!downloadBtn) return null;

    let actions = footer.querySelector('.download-actions');
    if (!actions) {
        actions = document.createElement('div');
        actions.className = 'download-actions';
        footer.insertBefore(actions, downloadBtn);
        actions.appendChild(downloadBtn);
    }

    const toggle = document.createElement('label');
    toggle.className = 'notebook-output-toggle';
    toggle.hidden = true;
    toggle.innerHTML = '<input type="checkbox" class="notebook-output-checkbox"><span class="notebook-output-switch" aria-hidden="true"></span><span>Show output</span>';
    actions.appendChild(toggle);
    return toggle;
}

async function loadAnswer(subject, questionNo, title, button, fileName, fileIndex) {
    Logger.group(`Loading Answer`);
    Logger.info(`Subject: ${subject}, Question: ${questionNo}, File: ${fileName}, Index: ${fileIndex}`);
    
    const startTime = performance.now();

    // Find the global answer box
    const answerBox = document.getElementById('globalAnswerBox');
    if (!answerBox) {
        Logger.error('Global answer box not found in DOM');
        Logger.groupEnd();
        return;
    }

    const questionTitle = document.getElementById('globalQuestionText');
    const codeContent = document.getElementById('globalCodeContent');
    const outputToggle = ensureNotebookOutputToggle(answerBox);
    const outputCheckbox = outputToggle?.querySelector('.notebook-output-checkbox');

    if (outputToggle) outputToggle.hidden = true;
    if (outputCheckbox) outputCheckbox.checked = false;
    answerBox.classList.remove('notebook-view');
    answerBox.notebookCode = null;

    if (!questionTitle || !codeContent) {
        Logger.error('Question title or code content element not found in global answer box');
        Logger.groupEnd();
        return;
    }

    // Show modal
    ModalManager.show(answerBox);

    // Set title and loading state
    questionTitle.textContent = title;
    codeContent.textContent = 'Loading...';
    codeContent.classList.add('loading');
    button.disabled = true;
    Logger.debug('Button disabled, loading state set');

    let trimmedText = '';

    try {
        trimmedText = await fetchAnswerText(subject, questionNo, fileIndex);
        Logger.debug(`Response received: ${trimmedText.length} characters`);

        const ext = fileName.split('.').pop().toLowerCase();

        if (ext === 'md' || ext === 'ipynb') {
            await loadMarkedIfNeeded();
        }

        let mediaContainer = answerBox.querySelector('.media-content');
        if (!mediaContainer) {
            mediaContainer = document.createElement('div');
            mediaContainer.className = 'media-content';
            mediaContainer.style.width = '100%';
            mediaContainer.style.marginTop = '15px';
            codeContent.parentElement.appendChild(mediaContainer);
        }

        const rawUrl = `/raw-answers/${subject}/${fileName}`;

        codeContent.style.display = 'none';
        mediaContainer.style.display = 'none';
        mediaContainer.innerHTML = '';
        
        const copyBtn = answerBox.querySelector('.copy-btn');
        if (copyBtn) copyBtn.style.display = 'flex'; // show by default

        const downloadBtn = answerBox.querySelector('.download-btn');
        if (downloadBtn) {
            downloadBtn.href = rawUrl;
            downloadBtn.setAttribute('download', fileName);
            downloadBtn.style.display = 'inline-flex';
        }

        if (['pdf'].includes(ext)) {
            mediaContainer.style.display = 'block';
            mediaContainer.innerHTML = `<iframe src="${rawUrl}" width="100%" height="600px" style="border:none; border-radius:8px; background: white;"></iframe>`;
            if (copyBtn) copyBtn.style.display = 'none';
            codeContent.textContent = '';
        } else if (['jpg', 'jpeg', 'png', 'gif', 'svg', 'webp'].includes(ext)) {
            mediaContainer.style.display = 'block';
            mediaContainer.innerHTML = `<div class="answer-image-container"><img src="${rawUrl}" alt="Answer Image" class="answer-image"></div>`;
            if (copyBtn) copyBtn.style.display = 'none';
            codeContent.textContent = '';
        } else if (ext === 'md') {
            if (typeof marked !== 'undefined') {
                mediaContainer.style.display = 'block';
                mediaContainer.innerHTML = `<div class="markdown-body">${marked.parse(trimmedText)}</div>`;
                codeContent.textContent = trimmedText;
            } else {
                codeContent.style.display = 'block';
                codeContent.textContent = trimmedText;
            }
        } else if (ext === 'ipynb') {
            try {
                const ipynb = JSON.parse(trimmedText);
                let html = '<div class="ipynb-notebook">';
                let codeCellNumber = 0;
                const codeCells = [];
                for (const cell of ipynb.cells) {
                    const source = Array.isArray(cell.source) ? cell.source.join('') : (cell.source || '');
                    if (cell.cell_type === 'markdown') {
                        html += `<div class="ipynb-markdown markdown-body">${typeof marked !== 'undefined' ? marked.parse(source) : '<pre>'+escapeNotebookHtml(source)+'</pre>'}</div>`;
                    } else if (cell.cell_type === 'code') {
                        codeCellNumber++;
                        codeCells.push(`# cell ${codeCellNumber}\n${source.replace(/(?:\r?\n)+$/, '')}`);
                        let cellId = 'cell-' + Math.random().toString(36).substr(2, 9);
                        html += `<div class="ipynb-code-container">`;
                        html += `<div class="ipynb-cell-header"><span>Code Cell ${codeCellNumber}</span><button class="cell-copy-btn" onclick="copyCell('${cellId}', this)">Copy</button></div>`;
                        html += `<div class="ipynb-code"><pre id="${cellId}">${highlightNotebookCode(source)}</pre></div>`;
                        if (cell.outputs && cell.outputs.length > 0) {
                            html += `<div class="ipynb-outputs">`;
                            for (const output of cell.outputs) {
                                if (output.text) {
                                    const outText = Array.isArray(output.text) ? output.text.join('') : output.text;
                                    html += `<pre class="ipynb-output-text">${escapeNotebookHtml(outText.replace(/\x1b\[[0-9;]*[a-zA-Z]/g, ""))}</pre>`;
                                } else if (output.data) {
                                    if (output.data["image/png"]) {
                                        const outImg = Array.isArray(output.data["image/png"]) ? output.data["image/png"].join('') : output.data["image/png"];
                                        html += `<img src="data:image/png;base64,${outImg}" class="ipynb-output-image">`;
                                    }
                                    if (output.data["text/plain"]) {
                                        const outText = Array.isArray(output.data["text/plain"]) ? output.data["text/plain"].join('') : output.data["text/plain"];
                                        html += `<pre class="ipynb-output-text">${escapeNotebookHtml(outText.replace(/\x1b\[[0-9;]*[a-zA-Z]/g, ""))}</pre>`;
                                    }
                                }
                            }
                            html += `</div>`;
                        }
                        html += `</div>`;
                    }
                }
                html += '</div>';
                mediaContainer.style.display = 'block';
                mediaContainer.innerHTML = html;
                answerBox.notebookCode = codeCells.join('\n\n');
                answerBox.classList.add('notebook-view');
                if (outputToggle && outputCheckbox) {
                    outputToggle.hidden = false;
                    outputCheckbox.onchange = () => {
                        mediaContainer.querySelector('.ipynb-notebook')?.classList.toggle('show-outputs', outputCheckbox.checked);
                    };
                }
                codeContent.textContent = trimmedText; 
            } catch (e) {
                codeContent.style.display = 'block';
                codeContent.textContent = trimmedText;
            }
        } else {
            codeContent.style.display = 'block';
            codeContent.textContent = trimmedText;
        }

        codeContent.classList.remove('loading');
        PrefetchManager.prefetchNext(subject, questionNo);
        


        const loadTime = (performance.now() - startTime).toFixed(2);
        Logger.info(`Answer loaded successfully in ${loadTime}ms`);

    } catch (error) {
        Logger.error('Failed to load answer', error);
        codeContent.textContent = `Error: Failed to load answer.\n\nDetails: ${error.message}\n\nPlease try again or check the GitHub repository.`;
        codeContent.style.display = 'block';
        codeContent.classList.remove('loading');
        codeContent.classList.add('error');
    } finally {
        button.disabled = false;
        Logger.debug('Button re-enabled');
        Logger.groupEnd();
    }
}

// =============================================================================
// Copy Code Function (Enhanced with better feedback)
// =============================================================================
function copyCode(elementId) {
    Logger.group('Copy Code');
    Logger.info(`Copying content from element: ${elementId}`);
    
    const codeElement = document.getElementById(elementId);
    if (!codeElement) {
        Logger.error(`Element not found: ${elementId}`);
        Logger.groupEnd();
        return;
    }

    const answerBox = codeElement.closest('.answer-box');
    
    if (!answerBox) {
        Logger.error('Answer box not found for copy button');
        Logger.groupEnd();
        return;
    }

    const text = answerBox.classList.contains('notebook-view')
        ? answerBox.notebookCode
        : (codeElement.innerText || codeElement.textContent);
    
    const btn = answerBox.querySelector('.copy-btn');
    
    if (!btn) {
        Logger.error('Copy button not found');
        Logger.groupEnd();
        return;
    }

    Logger.debug(`Text length: ${text.length} characters`);

    // Use modern clipboard API
    navigator.clipboard.writeText(text)
        .then(() => {
            Logger.info('Text copied to clipboard successfully');
            
            // Update button state
            const originalText = btn.textContent;
            btn.textContent = 'Copied!';
            btn.classList.add('copied');
            btn.disabled = true;

            // Reset button after delay
            setTimeout(() => {
                btn.textContent = originalText;
                btn.classList.remove('copied');
                btn.disabled = false;
                Logger.debug('Copy button state reset');
            }, CONFIG.COPY_FEEDBACK_DURATION);
        })
        .catch((error) => {
            Logger.error('Failed to copy text to clipboard', error);
            
            // Fallback: show manual copy instruction
            alert('Copy failed. Please select the text manually and press Ctrl+C (or Cmd+C on Mac).');
            
            // Try to select the text for manual copying
            try {
                const range = document.createRange();
                range.selectNodeContents(codeElement);
                const selection = window.getSelection();
                selection.removeAllRanges();
                selection.addRange(range);
                Logger.info('Text selected for manual copying');
            } catch (selectError) {
                Logger.error('Failed to select text', selectError);
            }
        })
        .finally(() => {
            Logger.groupEnd();
        });
}

// =============================================================================
// Copy Cell Function (Jupyter Notebooks)
// =============================================================================
function copyCell(elementId, btn) {
    Logger.group('Copy Cell (Jupyter)');
    const codeElement = document.getElementById(elementId);
    if (!codeElement) {
        Logger.error(`Element not found: ${elementId}`);
        Logger.groupEnd();
        return;
    }
    const text = codeElement.innerText || codeElement.textContent;
    navigator.clipboard.writeText(text).then(() => {
        Logger.info('Cell copied to clipboard');
        const originalText = btn.textContent;
        btn.textContent = 'Copied!';
        btn.style.color = '#fff';
        btn.style.backgroundColor = '#238636';
        btn.style.borderColor = '#238636';
        setTimeout(() => {
            btn.textContent = originalText;
            btn.style.color = '';
            btn.style.backgroundColor = '';
            btn.style.borderColor = '';
        }, CONFIG.COPY_FEEDBACK_DURATION || 2000);
    }).catch(err => {
        Logger.error("Failed to copy cell:", err);
        alert("Copy failed. Please select text manually.");
    }).finally(() => {
        Logger.groupEnd();
    });
}

// =============================================================================
// Close Modal Function (Enhanced)
// =============================================================================
function closeBox(boxId) {
    Logger.info(`Closing modal: ${boxId}`);
    
    const box = document.getElementById(boxId);
    if (!box) {
        Logger.error(`Modal not found: ${boxId}`);
        return;
    }

    ModalManager.hide(box);
}

// =============================================================================
// Global Event Listeners
// =============================================================================
(function setupGlobalListeners() {
    Logger.debug('Setting up global event listeners');
    
    // Escape key handler
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            Logger.debug('Escape key pressed');
            ModalManager.hideActive();
        }
    });

    // Backdrop click handler
    document.addEventListener('click', (event) => {
        if (event.target.classList.contains('modal-backdrop')) {
            Logger.debug('Backdrop clicked');
            ModalManager.hideActive();
        }
    });
    
    Logger.info('Global event listeners set up successfully');
})();

// =============================================================================
// Performance Monitoring (Development)
// =============================================================================
if (window.PerformanceNavigationTiming) {
    window.addEventListener('load', () => {
        setTimeout(() => {
            const entries = performance.getEntriesByType('navigation');
            if (entries.length > 0) {
                const entry = entries[0];
                Logger.group('Performance Metrics');
                Logger.info(`Page load time: ${Math.round(entry.loadEventEnd)}ms`);
                Logger.info(`DOM ready time: ${Math.round(entry.domContentLoadedEventEnd)}ms`);
                Logger.groupEnd();
            }
        }, 0);
    });
}

// =============================================================================
// Expose utilities to window for debugging
// =============================================================================
if (CONFIG.LOG_LEVEL === 'debug') {
    window.AnswerCache = AnswerCache;
    window.ModalManager = ModalManager;
    window.Logger = Logger;
    Logger.info('Debug utilities exposed to window object');
}

// =============================================================================
// Service initialization log
// =============================================================================
Logger.info('Script initialized successfully');
Logger.info(`Cache enabled: ${CONFIG.CACHE_ENABLED}`);
Logger.info(`Log level: ${CONFIG.LOG_LEVEL}`);
