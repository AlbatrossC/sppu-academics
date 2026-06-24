(function () {
'use strict';

// Logger utility with clean formatting
var Logger = {
    prefix: '[PDF Viewer]',
    info: function (msg, data) {
        console.log(this.prefix + ' ' + msg, data !== undefined ? data : '');
    },
    warn: function (msg, data) {
        console.warn(this.prefix + ' ' + msg, data !== undefined ? data : '');
    },
    error: function (msg, data) {
        console.error(this.prefix + ' ' + msg, data !== undefined ? data : '');
    },
    debug: function (msg, data) {
        if (window.location.search.includes('debug=true')) {
            console.log(this.prefix + ' [DEBUG] ' + msg, data !== undefined ? data : '');
        }
    }
};

function readViewerPageData() {
    var node = document.getElementById('viewer-page-data');
    if (!node) {
        return { parseError: true, papers: [], pdfFiles: [] };
    }
    try {
        var parsed = JSON.parse(node.textContent);
        return parsed && typeof parsed === 'object' ? parsed : { parseError: true, papers: [], pdfFiles: [] };
    } catch (error) {
        Logger.error('Failed to parse viewer page data', error);
        return { parseError: true, papers: [], pdfFiles: [] };
    }
}

function createClientIdPromise() {
    return Promise.resolve().then(function () {
        try {
            var key = 'client_id';
            var cachedClientId = window.localStorage.getItem(key);
            if (cachedClientId) {
                return cachedClientId;
            }
            var generated = window.crypto && typeof window.crypto.randomUUID === 'function'
                ? window.crypto.randomUUID()
                : 'client-' + Date.now().toString(36);
            window.localStorage.setItem(key, generated);
            return generated;
        } catch (storageError) {
            console.warn('client_id storage failed.', storageError);
            return 'client-anon';
        }
    });
}

var viewerPageData = readViewerPageData();
var initialPdfDataFromServer = Array.isArray(viewerPageData.pdfFiles) ? viewerPageData.pdfFiles : [];
var subjectNameFromServer = viewerPageData.subjectName || '';
var subjectLinkFromServer = viewerPageData.subjectLink || '';
var questionModalDataFromServer = {
    subjectLink: subjectLinkFromServer,
    subjectName: subjectNameFromServer,
    papers: Array.isArray(viewerPageData.papers) ? viewerPageData.papers : [],
    initialPaperId: viewerPageData.initialPaperId || ''
};

window.paperDownloadContext = {
    subjectLink: subjectLinkFromServer,
    subjectName: subjectNameFromServer,
    branchName: viewerPageData.branchName || '',
    patternYear: viewerPageData.patternYear || '',
    semester: viewerPageData.semester || '',
    analyticsEndpoint: viewerPageData.analyticsEndpoint || '/api/notify-download',
    papers: questionModalDataFromServer.papers || [],
    clientIdPromise: createClientIdPromise()
};

function getDownloadExamType(paper) {
    var explicit = String(
        paper.examType ||
        paper.exam_type ||
        paper.exam ||
        (paper.source_metadata && paper.source_metadata.exam) ||
        ''
    ).toLowerCase();

    if (explicit === 'insem' || explicit === 'endsem' || explicit === 'other') {
        return explicit;
    }

    var path = String(
        paper.canonicalPath ||
        paper.canonical_path ||
        paper.filename ||
        paper.originalFilename ||
        paper.url ||
        paper.link ||
        paper.pdf_url ||
        ''
    ).toLowerCase();
    var filename = path.split('/').pop();

    if (filename.indexOf('insem_') === 0 || filename.indexOf('insem-') === 0) return 'insem';
    if (filename.indexOf('endsem_') === 0 || filename.indexOf('endsem-') === 0) return 'endsem';
    return 'other';
}

function setDownloadOptionVisible(buttonId, visible) {
    var button = document.getElementById(buttonId);
    var option = button && button.closest ? button.closest('.download-option') : null;
    if (option) {
        option.style.display = visible ? '' : 'none';
    }
}

function configureDownloadOptions() {
    var papers = questionModalDataFromServer.papers || [];
    var available = papers.reduce(function (set, paper) {
        set[getDownloadExamType(paper)] = true;
        return set;
    }, {});

    var hasInsem = !!available.insem;
    var hasEndsem = !!available.endsem;
    var allTitle = document.querySelector('#download-all-btn')
        && document.querySelector('#download-all-btn').closest('.download-option')
        && document.querySelector('#download-all-btn').closest('.download-option').querySelector('.download-option-title');
    var allDesc = document.querySelector('#download-all-btn')
        && document.querySelector('#download-all-btn').closest('.download-option')
        && document.querySelector('#download-all-btn').closest('.download-option').querySelector('.download-option-desc');

    setDownloadOptionVisible('download-insem-btn', hasInsem);
    setDownloadOptionVisible('download-endsem-btn', hasEndsem);
    setDownloadOptionVisible('download-all-btn', papers.length > 0);

    if (allTitle) {
        allTitle.textContent = hasInsem || hasEndsem ? 'All Papers' : 'Download Papers';
    }
    if (allDesc) {
        allDesc.textContent = hasInsem || hasEndsem
            ? 'Download all available question papers as ZIP'
            : 'Download available question papers as ZIP';
    }
}

// Custom Dropdown Component with improved logic
var CustomDropdown = {
    activeDropdown: null,

    init: function (element, onChange) {
        var self = this;
        var selected = element.querySelector('.dropdown-selected');
        var options = element.querySelector('.dropdown-options');
        var allOptions = element.querySelectorAll('.dropdown-option');

        element._getValue = function () {
            return element.getAttribute('data-value');
        };

        element._setValue = function (value, triggerChange) {
            var option = element.querySelector('.dropdown-option[data-value="' + value + '"]');
            if (option && !option.classList.contains('disabled')) {
                element.setAttribute('data-value', value);
                element.querySelector('.dropdown-text').textContent = option.textContent;
                allOptions.forEach(function (opt) { opt.classList.remove('selected'); });
                option.classList.add('selected');
                if (triggerChange && onChange) {
                    onChange(value);
                }
            }
        };

        element._setDisabled = function (value, disabled) {
            var option = element.querySelector('.dropdown-option[data-value="' + value + '"]');
            if (option) {
                if (disabled) {
                    option.classList.add('disabled');
                } else {
                    option.classList.remove('disabled');
                }
            }
        };

        selected.addEventListener('click', function (e) {
            e.stopPropagation();
            var isOpen = element.classList.contains('open');
            self.closeAll();
            if (!isOpen) {
                element.classList.add('open');
                self.activeDropdown = element;
                Logger.debug('Dropdown opened', element.id);
            }
        });

        allOptions.forEach(function (option) {
            option.addEventListener('click', function (e) {
                e.stopPropagation();
                var value = option.getAttribute('data-value');
                if (option.classList.contains('disabled')) {
                    // For exam-type dropdowns, still fire the change so the
                    // inline empty state can be shown (applyExamType handles it).
                    // For other dropdowns (layout, paper) disabled means truly blocked.
                    if (onChange) onChange(value);
                    element.classList.remove('open');
                    self.activeDropdown = null;
                    return;
                }
                element._setValue(value, true);
                element.classList.remove('open');
                self.activeDropdown = null;
                Logger.debug('Dropdown option selected', { dropdown: element.id, value: value });
            });
        });

        return element;
    },

    closeAll: function () {
        document.querySelectorAll('.custom-dropdown.open').forEach(function (dd) {
            dd.classList.remove('open');
        });
        this.activeDropdown = null;
        Logger.debug('All dropdowns closed');
    }
};

// Close dropdowns when clicking anywhere outside
document.addEventListener('click', function (e) {
    if (!e.target.closest('.custom-dropdown')) {
        CustomDropdown.closeAll();
    }
});

var DOM = {
    pdfContainer: document.getElementById('pdf-container'),
    subjectDisplay: document.getElementById('subject-display'),
    pdfCountDropdown: null,
    examTypeButtons: null,
    fullscreenBtn: document.getElementById('fullscreen-btn'),
    backBtn: document.getElementById('back-btn'),
    watermarkBtn: document.getElementById('watermarkGlobalToggle'),
    watermarkLabel: document.getElementById('watermarkGlobalToggleLabel'),
    downloadBtn: document.getElementById('download-btn'),
    downloadModal: document.getElementById('download-modal'),
    downloadModalOverlay: document.getElementById('download-modal-overlay'),
    downloadModalClose: document.getElementById('download-modal-close'),
    downloadSubjectName: document.getElementById('download-subject-name'),
    downloadActionButtons: document.querySelectorAll('button[data-download]'),
    questionsBtn: document.getElementById('questions-btn'),
    questionsModal: document.getElementById('questions-modal'),
    questionsModalOverlay: document.getElementById('questions-modal-overlay'),
    questionsModalClose: document.getElementById('questions-modal-close'),
    questionsPaperDropdown: null,
    questionsTabs: document.querySelectorAll('.questions-tab'),
    questionsPaperPanels: document.getElementById('questions-paper-panels'),
    mobileControlBar: document.getElementById('mobile-control-bar'),
    mobileExamDropdown: null,
    mobilePaperDropdown: null
};

// Single source of truth for default exam type
var DEFAULT_EXAM_TYPE = viewerPageData.defaultExamType || 'insem';

var state = {
    pdfFiles: [],
    isRendering: false,
    renderQueue: Promise.resolve(),
    pdfViewerBase: viewerPageData.pdfViewerBase || '/static/pdfjs/web/viewer',
    watermarkHidden: false,
    currentLayout: '1',
    currentExamType: DEFAULT_EXAM_TYPE,
    activeRenderToken: 0,
    iframeLoadTokens: new WeakMap(),
    nextIframeLoadToken: 0,
    currentQuestionsPaperId: questionModalDataFromServer.initialPaperId || '',
    currentQuestionsTab: 'questions'
};

function debounce(func, wait) {
    var timeout;
    return function () {
        var args = arguments;
        var context = this;
        clearTimeout(timeout);
        timeout = setTimeout(function () {
            func.apply(context, args);
        }, wait);
    };
}

function loadPdfIntoIframe(iframe, pdfUrl, loader, retryCount, options) {
    retryCount = retryCount || 0;
    options = options || {};
    var renderToken = typeof options.renderToken === 'number' ? options.renderToken : state.activeRenderToken;
    state.nextIframeLoadToken++;
    var iframeLoadToken = state.nextIframeLoadToken;
    state.iframeLoadTokens.set(iframe, iframeLoadToken);

    if (!isValidUrl(pdfUrl)) {
        showPdfError(iframe, loader, 'Invalid PDF URL');
        Logger.error('Invalid PDF URL', pdfUrl);
        return Promise.resolve(false);
    }

    var fileName = pdfUrl.split('/').pop();
    var viewerUrl = state.pdfViewerBase + '?file=' + encodeURIComponent(pdfUrl) + '&locale=en-US';
    Logger.debug('Loading PDF: ' + fileName);

    return new Promise(function (resolve, reject) {
        var settled = false;

        function finish(success) {
            if (settled) {
                return;
            }
            settled = true;
            resolve(success);
        }

        iframe.onload = function () {
            if (state.iframeLoadTokens.get(iframe) !== iframeLoadToken || renderToken !== state.activeRenderToken) {
                finish(false);
                return;
            }
            if (loader && loader.parentNode) {
                loader.remove();
            }
            Logger.debug('PDF loaded successfully: ' + fileName);

            if (state.watermarkHidden) {
                setTimeout(function () {
                    WatermarkManager.sendCommandToIframe(iframe, 'remove');
                }, 500);
            }
            finish(true);
        };

        iframe.onerror = function () {
            if (state.iframeLoadTokens.get(iframe) !== iframeLoadToken) {
                finish(false);
                return;
            }
            reject(new Error('PDF viewer load error'));
        };

        iframe.src = viewerUrl;
    }).catch(function (error) {
        if (retryCount < 2) {
            Logger.warn('Retrying PDF load (' + (retryCount + 1) + '): ' + fileName);
            return new Promise(function (resolve) {
                setTimeout(function () {
                    resolve(loadPdfIntoIframe(iframe, pdfUrl, loader, retryCount + 1, options));
                }, 1000);
            });
        }
        showPdfError(iframe, loader, 'Error loading PDF. Please check your network connection.');
        Logger.error('Failed to load PDF after ' + (retryCount + 1) + ' attempts: ' + fileName);
        return false;
    });
}

function showPdfError(iframe, loader, message) {
    if (loader && loader.parentNode) {
        loader.remove();
    }
    if (iframe.parentElement) {
        var errorMsg = document.createElement('div');
        errorMsg.className = 'no-pdf-message error-message';
        errorMsg.textContent = message;
        iframe.parentElement.innerHTML = '';
        iframe.parentElement.appendChild(errorMsg);
    }
}

function isValidUrl(url) {
    try {
        var parsed = new URL(url);
        return parsed.pathname.toLowerCase().endsWith('.pdf');
    } catch (e) {
        return false;
    }
}

function updateSubjectDisplay() {
    DOM.subjectDisplay.textContent = subjectNameFromServer || "Subject";
}

function filterPDFs(examType) {
    var key = String(examType || '').toLowerCase();
    var result = state.pdfFiles.filter(function (file) {
        var explicit = String(file.examType || file.exam_type || '').toLowerCase();
        if (explicit) {
            return explicit === key;
        }
        return file.originalFilename.toLowerCase().includes(key);
    });
    Logger.debug('Filter applied', { examType: examType, count: result.length });
    return result;
}

function renderPDFs() {
    if (state.isRendering) {
        Logger.debug('Render already in progress, skipping');
        return;
    }
    state.isRendering = true;
    state.activeRenderToken++;
    var renderToken = state.activeRenderToken;

    state.renderQueue = state.renderQueue.then(function () {
        return new Promise(function (resolve) {
            var count = parseInt(DOM.pdfCountDropdown._getValue(), 10);
            // CRITICAL: Read exam type from state (single source of truth)
            var examType = state.currentExamType;

            state.currentLayout = count.toString();

            // Reset watermark state on render
            WatermarkManager.resetState();

            var filteredData = filterPDFs(examType);

            Logger.info('Rendering PDFs', {
                layout: count,
                examType: examType,
                availablePdfs: filteredData.length
            });

            DOM.pdfContainer.querySelectorAll('iframe').forEach(function (iframe) {
                iframe.remove();
            });

            DOM.pdfContainer.className = 'grid-' + count;

            if (!filteredData.length) {
                var otherType = examType === 'insem' ? 'endsem' : 'insem';
                var otherLabel = otherType.toUpperCase();
                var thisLabel = examType.toUpperCase();
                var otherHasPapers = filterPDFs(otherType).length > 0;

                var switchBtn = otherHasPapers
                    ? '<button type="button" class="empty-state-switch-btn" data-switch-exam="' + otherType + '">View ' + otherLabel + ' papers</button>'
                    : '';


                DOM.pdfContainer.innerHTML =
                    '<div class="empty-state">' +
                    '<div class="empty-state-icon">' +
                    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">' +
                    '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>' +
                    '<polyline points="14 2 14 8 20 8"></polyline>' +
                    '<line x1="9" y1="15" x2="15" y2="15"></line>' +
                    '<line x1="9" y1="11" x2="15" y2="11"></line>' +
                    '</svg>' +
                    '</div>' +
                    '<h3 class="empty-state-title">No ' + thisLabel + ' papers available</h3>' +
                    '<p class="empty-state-desc">There are no ' + thisLabel + ' question papers for this subject.</p>' +
                    switchBtn +
                    '</div>';

                state.isRendering = false;
                Logger.info('No PDFs match current filter');
                resolve();
                return;
            }

            DOM.pdfContainer.innerHTML = '';
            var fragment = document.createDocumentFragment();
            var maxRender = Math.min(count, filteredData.length);
            var visibleEntries = [];

            for (var i = 0; i < count; i++) {
                var div = document.createElement('div');
                div.className = 'pdf-viewer';

                if (i < maxRender) {
                    var loader = document.createElement('div');
                    loader.className = 'loader-container';
                    loader.innerHTML = '<div class="loader"></div>';
                    div.appendChild(loader);

                    var selector = createPaperSelector(filteredData, i, 'viewer-' + i);
                    div.appendChild(selector);

                    var iframe = document.createElement('iframe');
                    iframe.title = 'PDF Viewer ' + (i + 1) + ' - ' + filteredData[i].originalFilename;
                    iframe.setAttribute('data-viewer-index', i);
                    iframe.loading = i === 0 ? 'eager' : 'lazy';
                    iframe.setAttribute('fetchpriority', i === 0 ? 'high' : 'auto');
                    div.appendChild(iframe);
                    visibleEntries.push({
                        iframe: iframe,
                        loader: loader,
                        pdfUrl: filteredData[i].link,
                        originalFilename: filteredData[i].originalFilename
                    });

                } else {
                    div.innerHTML = '<div class="no-more-papers">No additional paper for this slot.</div>';
                }
                fragment.appendChild(div);
            }
            DOM.pdfContainer.appendChild(fragment);
            if (visibleEntries.length > 0) {
                var firstLoadPromise = loadPdfIntoIframe(
                    visibleEntries[0].iframe,
                    visibleEntries[0].pdfUrl,
                    visibleEntries[0].loader,
                    0,
                    { renderToken: renderToken }
                );
                var backgroundUrls = filteredData.slice(maxRender, maxRender + 2).map(function (file) {
                    return file.link;
                });
                firstLoadPromise.then(function () {
                    queueBackgroundPdfLoads(visibleEntries.slice(1), backgroundUrls, renderToken);
                });
            }
            state.isRendering = false;
            Logger.info('Render complete', { viewersCreated: maxRender });
            resolve();
        });
    });
}


function queueBackgroundPdfLoads(visibleEntries, backgroundUrls, renderToken) {
    var visibleTasks = [];

    visibleEntries.forEach(function (entry) {
        visibleTasks.push(function () {
            if (renderToken !== state.activeRenderToken) {
                return Promise.resolve(false);
            }
            return loadPdfIntoIframe(entry.iframe, entry.pdfUrl, entry.loader, 0, { renderToken: renderToken });
        });
    });

    function runTasks(tasks, concurrency) {
        var index = 0;
        concurrency = Math.min(concurrency, tasks.length);

        if (!concurrency) {
            return Promise.resolve();
        }

        function worker() {
            if (renderToken !== state.activeRenderToken || index >= tasks.length) {
                return Promise.resolve();
            }
            var task = tasks[index++];
            return task().catch(function (error) {
                Logger.warn('Background PDF load failed', error && error.message ? error.message : error);
            }).then(worker);
        }

        return Promise.all(Array.from({ length: concurrency }, worker));
    }

    return runTasks(visibleTasks, 2).then(function () {
        if (!backgroundUrls.length || renderToken !== state.activeRenderToken) {
            return;
        }

        scheduleIdleWork(function () {
            prewarmPdfUrls(backgroundUrls, renderToken);
        });
    });
}

function prewarmPdfUrls(pdfUrls, renderToken) {
    var index = 0;
    var concurrency = Math.min(2, pdfUrls.length);

    function worker() {
        if (renderToken !== state.activeRenderToken || index >= pdfUrls.length) {
            return Promise.resolve();
        }

        var pdfUrl = pdfUrls[index++];
        return fetch(pdfUrl, {
            cache: 'force-cache',
            mode: 'cors',
            credentials: 'omit'
        }).catch(function (error) {
            Logger.debug('PDF prewarm skipped', error && error.message ? error.message : error);
        }).then(worker);
    }

    return Promise.all(Array.from({ length: concurrency }, worker));
}

function scheduleIdleWork(callback) {
    if (typeof window.requestIdleCallback === 'function') {
        window.requestIdleCallback(callback, { timeout: 2500 });
        return;
    }
    window.setTimeout(callback, 1200);
}

function createPaperSelector(data, initialIndex, viewerId) {
    var selectorContainer = document.createElement('div');
    selectorContainer.className = 'paper-selector';

    var label = document.createElement('label');
    label.className = 'paper-selector-label';
    label.textContent = 'Paper:';

    var dropdown = document.createElement('div');
    dropdown.className = 'custom-dropdown paper-dropdown';
    dropdown.setAttribute('data-value', initialIndex);

    var selectedDiv = document.createElement('div');
    selectedDiv.className = 'dropdown-selected';
    selectedDiv.innerHTML = '<span class="dropdown-text">' + data[initialIndex].date + '</span><svg class="dropdown-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>';

    var optionsDiv = document.createElement('div');
    optionsDiv.className = 'dropdown-options';

    data.forEach(function (item, idx) {
        var option = document.createElement('div');
        option.className = 'dropdown-option' + (idx === initialIndex ? ' selected' : '');
        option.setAttribute('data-value', idx);
        option.textContent = item.date;
        optionsDiv.appendChild(option);
    });

    dropdown.appendChild(selectedDiv);
    dropdown.appendChild(optionsDiv);

    CustomDropdown.init(dropdown, function (idx) {
        idx = parseInt(idx, 10);
        var pdfUrl = data[idx].link;
        var viewerDiv = selectorContainer.closest('.pdf-viewer');
        var iframe = viewerDiv.querySelector('iframe');
        if (!iframe) {
            return;
        }

        iframe.title = 'PDF Viewer ' + (parseInt(viewerId.split('-')[1]) + 1) + ' - ' + data[idx].originalFilename;

        var existingLoader = viewerDiv.querySelector('.loader-container');
        if (existingLoader) {
            existingLoader.remove();
        }
        var loader = document.createElement('div');
        loader.className = 'loader-container';
        loader.innerHTML = '<div class="loader"></div>';
        viewerDiv.insertBefore(loader, iframe);

        Logger.info('Paper changed', { viewer: viewerId, paper: data[idx].date });
        loadPdfIntoIframe(iframe, pdfUrl, loader);
    });

    selectorContainer.appendChild(label);
    selectorContainer.appendChild(dropdown);
    return selectorContainer;
}

function toggleFullscreen() {
    if (document.fullscreenElement) {
        document.exitFullscreen().catch(function (err) {
            Logger.error('Error exiting fullscreen', err.message);
        });
    } else {
        document.documentElement.requestFullscreen({ navigationUI: 'hide' }).catch(function (err) {
            Logger.error('Error entering fullscreen', err.message);
        });
    }
}

function updateFullscreenButton() {
    var isFullscreen = !!document.fullscreenElement;
    var icon = isFullscreen ?
        '<svg class="icon" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" viewBox="0 0 24 24"><path d="M4 14h6m0 0v6m0-6l-7 7m17-11h-6m0 0V4m0 6l7-7"/></svg>' :
        '<svg class="icon" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" viewBox="0 0 24 24"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3"/></svg>';
    var text = isFullscreen ? 'Exit Fullscreen' : 'Fullscreen';

    DOM.fullscreenBtn.innerHTML = icon + '<span class="btn-text">' + text + '</span>';
    Logger.debug('Fullscreen toggled', { isFullscreen: isFullscreen });
}

// Enhanced Watermark Manager with consistent state
var WatermarkManager = {
    sendCommandToIframe: function (iframe, cmd) {
        try {
            var cw = iframe.contentWindow;
            if (!cw) {
                return false;
            }

            if (typeof cw.removeWatermarkFull === 'function') {
                if (cmd === 'remove') {
                    try {
                        cw.removeWatermarkFull();
                        Logger.debug('Watermark removed via direct call');
                    } catch (e) {
                        Logger.warn('Direct watermark removal failed', e.message);
                    }
                } else if (cmd === 'restore') {
                    try {
                        cw.location.reload();
                        Logger.debug('Watermark restored via reload');
                    } catch (e) {
                        try {
                            cw.postMessage({ type: 'watermark', command: 'restore' }, location.origin);
                        } catch (e2) {
                            Logger.warn('Watermark restore failed', e2.message);
                        }
                    }
                }
                return true;
            }

            try {
                cw.postMessage({ type: 'watermark', command: cmd }, location.origin);
                Logger.debug('Watermark command sent via postMessage', cmd);
                return true;
            } catch (e) {
                Logger.warn('postMessage failed', e.message);
                return false;
            }
        } catch (e) {
            Logger.warn('Watermark command error', e.message);
            return false;
        }
    },

    getAllViewerIframes: function () {
        return Array.from(document.querySelectorAll('#pdf-container iframe'));
    },

    applyToAll: function (cmd) {
        var iframes = this.getAllViewerIframes();
        Logger.info('Applying watermark command to all viewers', { command: cmd, count: iframes.length });

        iframes.forEach(function (iframe) {
            var ok = WatermarkManager.sendCommandToIframe(iframe, cmd);
            if (!ok) {
                var handler = function () {
                    try {
                        WatermarkManager.sendCommandToIframe(iframe, cmd);
                    } catch (e) {
                        Logger.warn('Delayed watermark command failed', e.message);
                    }
                    iframe.removeEventListener('load', handler);
                };
                iframe.addEventListener('load', handler);
            }
        });
    },

    setButtonState: function (hidden) {
        if (!DOM.watermarkBtn) {
            return;
        }

        state.watermarkHidden = hidden;
        DOM.watermarkBtn.setAttribute('aria-pressed', hidden ? 'true' : 'false');

        if (hidden) {
            DOM.watermarkBtn.classList.add('active');
            DOM.watermarkLabel.textContent = 'Show watermark';
        } else {
            DOM.watermarkBtn.classList.remove('active');
            DOM.watermarkLabel.textContent = 'Hide watermark';
        }

        Logger.info('Watermark state changed', { hidden: hidden });
    },

    resetState: function () {
        this.setButtonState(false);
        Logger.debug('Watermark state reset to default');
    },

    toggle: function () {
        var pressed = DOM.watermarkBtn.getAttribute('aria-pressed') === 'true';
        if (!pressed) {
            this.setButtonState(true);
            this.applyToAll('remove');
        } else {
            this.setButtonState(false);
            this.applyToAll('restore');
        }
    }
};


function loadDownloadHelper(button, event) {
    if (window.DownloadPaper) {
        if (typeof window.DownloadPaper.init === 'function') {
            window.DownloadPaper.init();
        }
        window.DownloadPaper.handleClick(event, button);
        return;
    }

    var scriptUrl = viewerPageData.downloadScriptUrl || '/static/js/download-paper.js';
    var existing = document.querySelector('script[data-download-helper]');

    function fail() {
        var status = document.getElementById('download-status');
        if (status) {
            status.textContent = 'Failed to load download helper.';
        }
    }

    if (existing) {
        existing.addEventListener('load', function () {
            if (window.DownloadPaper) {
                if (typeof window.DownloadPaper.init === 'function') {
                    window.DownloadPaper.init();
                }
                window.DownloadPaper.handleClick(event, button);
            } else {
                fail();
            }
        }, { once: true });
        existing.addEventListener('error', fail, { once: true });
        return;
    }

    var script = document.createElement('script');
    script.src = scriptUrl;
    script.async = true;
    script.dataset.downloadHelper = 'true';
    script.onload = function () {
        if (window.DownloadPaper) {
            if (typeof window.DownloadPaper.init === 'function') {
                window.DownloadPaper.init();
            }
            window.DownloadPaper.handleClick(event, button);
        } else {
            fail();
        }
    };
    script.onerror = fail;
    document.head.appendChild(script);
}

function openDownloadModal() {
    if (DOM.downloadModal && DOM.downloadSubjectName) {
        DOM.downloadSubjectName.textContent = subjectNameFromServer || 'Subject';
        configureDownloadOptions();
        DOM.downloadModal.classList.add('active');
        document.body.style.overflow = 'hidden';
        Logger.info('Download modal opened');
    }
}

function closeDownloadModal() {
    if (DOM.downloadModal) {
        DOM.downloadModal.classList.remove('active');
        document.body.style.overflow = '';

        // Reset download status when modal closes
        var statusContainer = document.getElementById('download-status-container');
        var progressFill = document.getElementById('download-progress-fill');
        var percentage = document.getElementById('download-percentage');
        if (statusContainer) statusContainer.style.display = 'none';
        if (progressFill) {
            progressFill.style.width = '0%';
            delete progressFill.dataset.status;
        }
        if (percentage) {
            percentage.textContent = '';
            percentage.style.display = 'none';
        }

        Logger.info('Download modal closed');
    }
}

function setQuestionsTab(tabName) {
    state.currentQuestionsTab = tabName === 'metadata' ? 'metadata' : 'questions';

    DOM.questionsTabs.forEach(function (tabButton) {
        var isActive = tabButton.getAttribute('data-tab') === state.currentQuestionsTab;
        tabButton.classList.toggle('active', isActive);
        tabButton.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });

    document.querySelectorAll('.questions-paper-panel').forEach(function (panel) {
        panel.querySelectorAll('.questions-panel').forEach(function (tabPanel) {
            var isActive = tabPanel.getAttribute('data-tab-panel') === state.currentQuestionsTab;
            tabPanel.classList.toggle('active', isActive);
        });
    });
}

function setQuestionsPaper(paperId) {
    state.currentQuestionsPaperId = paperId || state.currentQuestionsPaperId;

    document.querySelectorAll('.questions-paper-panel').forEach(function (panel) {
        var isActive = panel.getAttribute('data-paper-id') === state.currentQuestionsPaperId;
        panel.classList.toggle('active', isActive);
    });
}

function openQuestionsModal() {
    if (!DOM.questionsModal) {
        return;
    }
    DOM.questionsModal.classList.add('active');
    document.body.style.overflow = 'hidden';
    setQuestionsPaper(state.currentQuestionsPaperId);
    setQuestionsTab(state.currentQuestionsTab);
    Logger.info('Questions modal opened', { paperId: state.currentQuestionsPaperId });
}

function closeQuestionsModal() {
    if (!DOM.questionsModal) {
        return;
    }
    DOM.questionsModal.classList.remove('active');
    document.body.style.overflow = '';
    Logger.info('Questions modal closed');
}

function updateMobilePaperDropdown() {
    var dropdown = document.getElementById('mobile-paper-dropdown');
    if (!dropdown) return;

    var filteredData = filterPDFs(state.currentExamType);
    var optionsDiv = dropdown.querySelector('.dropdown-options');
    var textSpan = dropdown.querySelector('.dropdown-text');

    if (!optionsDiv) return;

    // Clear existing options
    optionsDiv.innerHTML = '';

    if (!filteredData || filteredData.length === 0) {
        optionsDiv.innerHTML = '<div class="dropdown-option disabled">No papers available</div>';
        if (textSpan) textSpan.textContent = 'No papers';
        dropdown.setAttribute('data-value', '');
        return;
    }

    // Add new options with click handlers
    filteredData.forEach(function (item, idx) {
        var option = document.createElement('div');
        option.className = 'dropdown-option' + (idx === 0 ? ' selected' : '');
        option.setAttribute('data-value', idx);
        option.textContent = item.date;

        // Add click handler for each option
        option.addEventListener('click', function (e) {
            e.stopPropagation();
            if (option.classList.contains('disabled')) return;

            // Update selected state in dropdown
            optionsDiv.querySelectorAll('.dropdown-option').forEach(function (opt) {
                opt.classList.remove('selected');
            });
            option.classList.add('selected');
            dropdown.setAttribute('data-value', idx);
            if (textSpan) textSpan.textContent = item.date;

            // Close dropdown
            dropdown.classList.remove('open');

            // Load the selected paper
            var pdfUrl = filteredData[idx].link;
            var viewerDiv = document.querySelector('.pdf-viewer');
            if (!viewerDiv) return;

            var iframe = viewerDiv.querySelector('iframe');
            if (!iframe) return;

            iframe.title = 'PDF Viewer 1 - ' + filteredData[idx].originalFilename;

            var existingLoader = viewerDiv.querySelector('.loader-container');
            if (existingLoader) {
                existingLoader.remove();
            }
            var loader = document.createElement('div');
            loader.className = 'loader-container';
            loader.innerHTML = '<div class="loader"></div>';
            viewerDiv.insertBefore(loader, iframe);

            Logger.info('Mobile paper changed', { paper: filteredData[idx].date });
            loadPdfIntoIframe(iframe, pdfUrl, loader);
        });

        optionsDiv.appendChild(option);
    });

    // Set first paper as selected
    dropdown.setAttribute('data-value', '0');
    if (textSpan) {
        textSpan.textContent = filteredData[0].date;
    }

    Logger.debug('Mobile paper dropdown updated', { count: filteredData.length });
}

function syncMobileExamDropdown() {
    var dropdown = document.getElementById('mobile-exam-dropdown');
    if (!dropdown) return;

    var examType = state.currentExamType;
    dropdown.setAttribute('data-value', examType);

    var textSpan = dropdown.querySelector('.dropdown-text');
    if (textSpan) {
        textSpan.textContent = examType.toUpperCase();
    }

    // Update selected option
    var options = dropdown.querySelectorAll('.dropdown-option');
    options.forEach(function (opt) {
        opt.classList.remove('selected');
        if (opt.getAttribute('data-value') === examType) {
            opt.classList.add('selected');
        }
    });

    Logger.debug('Mobile exam dropdown synced', { examType: examType });
}

// Unified function to apply exam type - single pipeline for all changes
function applyExamType(examType) {
    // Update state (single source of truth)
    state.currentExamType = examType;

    // Sync desktop buttons
    document.querySelectorAll('.exam-toggle-btn').forEach(function (btn) {
        if (btn.getAttribute('data-value') === examType) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });

    // Sync mobile dropdown
    syncMobileExamDropdown();

    // Render PDFs with new exam type
    renderPDFs();

    // Update mobile paper dropdown after render completes
    setTimeout(function () {
        updateMobilePaperDropdown();
    }, 300);

    Logger.info('Exam type applied', { examType: examType });
}


function setupEventListeners() {

    var debouncedRender = debounce(renderPDFs, 250);

    var onLayoutChange = function (val) {
        if (window.IS_MOBILE_DEVICE && val === '2') {
            checkOrientation();
        }
        debouncedRender();
    };

    DOM.pdfCountDropdown = CustomDropdown.init(
        document.getElementById('pdf-count-dropdown'),
        onLayoutChange
    );

    var questionsPaperDropdownEl = document.getElementById('questions-paper-dropdown');
    if (questionsPaperDropdownEl) {
        DOM.questionsPaperDropdown = CustomDropdown.init(questionsPaperDropdownEl, function (paperId) {
            setQuestionsPaper(paperId);
        });
    }

    DOM.questionsTabs.forEach(function (tabButton) {
        tabButton.addEventListener('click', function () {
            setQuestionsTab(tabButton.getAttribute('data-tab'));
        });
    });

    // Setup exam type toggle buttons — disabled buttons still switch to that
    // type so the inline empty state is shown instead of a popup
    var examToggleButtons = document.querySelectorAll('.exam-toggle-btn');
    examToggleButtons.forEach(function (btn) {
        btn.addEventListener('click', function () {
            var examType = btn.getAttribute('data-value');
            applyExamType(examType);
        });
    });

    DOM.examTypeButtons = examToggleButtons;

    DOM.fullscreenBtn.addEventListener('click', toggleFullscreen);
    DOM.backBtn.addEventListener('click', function () {
        Logger.info('Navigating back to question papers list');
        window.location.href = '/';
    });

    if (DOM.downloadBtn) {
        DOM.downloadBtn.addEventListener('click', openDownloadModal);
    }

    if (DOM.downloadActionButtons && DOM.downloadActionButtons.length) {
        DOM.downloadActionButtons.forEach(function (button) {
            button.addEventListener('click', function (event) {
                loadDownloadHelper(button, event);
            });
        });
    }

    if (DOM.questionsBtn) {
        DOM.questionsBtn.addEventListener('click', openQuestionsModal);
    }

    if (DOM.downloadModalOverlay) {
        DOM.downloadModalOverlay.addEventListener('click', closeDownloadModal);
    }

    if (DOM.downloadModalClose) {
        DOM.downloadModalClose.addEventListener('click', closeDownloadModal);
    }

    if (DOM.questionsModalOverlay) {
        DOM.questionsModalOverlay.addEventListener('click', closeQuestionsModal);
    }

    if (DOM.questionsModalClose) {
        DOM.questionsModalClose.addEventListener('click', closeQuestionsModal);
    }

    if (DOM.watermarkBtn) {
        DOM.watermarkBtn.addEventListener('click', function () {
            WatermarkManager.toggle();
        });
    }

    document.addEventListener('fullscreenchange', updateFullscreenButton);

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            CustomDropdown.closeAll();
            if (DOM.downloadModal && DOM.downloadModal.classList.contains('active')) {
                closeDownloadModal();
            } else if (DOM.questionsModal && DOM.questionsModal.classList.contains('active')) {
                closeQuestionsModal();
            } else if (document.fullscreenElement) {
                document.exitFullscreen().catch(function (err) {
                    Logger.error('Error exiting fullscreen on escape', err.message);
                });
            }
        }
    });

    // Observe container for new iframes to apply watermark state
    var container = document.getElementById('pdf-container');
    if (container) {
        var mo = new MutationObserver(function () {
            try {
                if (state.watermarkHidden) {
                    setTimeout(function () {
                        WatermarkManager.applyToAll('remove');
                    }, 500);
                }
            } catch (e) {
                Logger.warn('MutationObserver error', e.message);
            }
        });
        mo.observe(container, { childList: true, subtree: true });
    }

    // Setup mobile control bar dropdowns
    var mobileExamDropdownEl = document.getElementById('mobile-exam-dropdown');
    if (mobileExamDropdownEl) {
        DOM.mobileExamDropdown = CustomDropdown.init(mobileExamDropdownEl, function (examType) {
            // Use unified pipeline for all exam type changes
            applyExamType(examType);
        });
    }

    var mobilePaperDropdownEl = document.getElementById('mobile-paper-dropdown');
    if (mobilePaperDropdownEl) {
        // Just initialize for open/close functionality - option clicks handled in updateMobilePaperDropdown
        DOM.mobilePaperDropdown = CustomDropdown.init(mobilePaperDropdownEl, function () {
            // Options handle their own click events
        });
    }

    Logger.info('Event listeners initialized');
}

function checkOrientation() {
    var prompt = document.getElementById('rotation-prompt');
    if (window.innerHeight > window.innerWidth) {
        prompt.style.display = 'flex';
        Logger.debug('Rotation prompt displayed');
    } else {
        prompt.style.display = 'none';
    }
}

function init() {
    Logger.info('Initializing PDF Viewer...');

    updateSubjectDisplay();
    setupEventListeners();
    if (!state.currentQuestionsPaperId && questionModalDataFromServer.papers && questionModalDataFromServer.papers.length) {
        state.currentQuestionsPaperId = questionModalDataFromServer.papers[0].pdf_id || '';
    }
    if (DOM.questionsPaperDropdown && state.currentQuestionsPaperId) {
        DOM.questionsPaperDropdown._setValue(state.currentQuestionsPaperId, false);
    }
    setQuestionsPaper(state.currentQuestionsPaperId);
    setQuestionsTab(state.currentQuestionsTab);

    if (window.IS_MOBILE_DEVICE) {
        Logger.info('Mobile device detected, adjusting layout options');
        var layoutDropdown = document.getElementById('pdf-count-dropdown');
        var options = layoutDropdown.querySelectorAll('.dropdown-option');
        options.forEach(function (opt) {
            var val = opt.getAttribute('data-value');
            if (val === '3' || val === '4') {
                opt.style.display = 'none';
            }
        });

        window.addEventListener('resize', debounce(function () {
            if (DOM.pdfCountDropdown && DOM.pdfCountDropdown._getValue() === '2') {
                if (window.innerWidth > window.innerHeight) {
                    document.getElementById('rotation-prompt').style.display = 'none';
                }
            }
        }, 100));

        document.getElementById('dismiss-rotation').addEventListener('click', function () {
            document.getElementById('rotation-prompt').style.display = 'none';
            Logger.debug('Rotation prompt dismissed');
        });
    }

    if (viewerPageData.parseError) {
        DOM.pdfContainer.innerHTML = '<div class="no-pdf-message error-message">We could not load this viewer data. Please refresh the page.</div>';
        DOM.subjectDisplay.textContent = subjectNameFromServer || 'Subject';
        Logger.error('Viewer data payload is malformed');
        return;
    }

    if (initialPdfDataFromServer && initialPdfDataFromServer.length > 0) {
        state.pdfFiles = initialPdfDataFromServer
            .map(function (pdfObject) {
                if (!pdfObject || typeof pdfObject.filename !== 'string' ||
                    typeof pdfObject.url !== 'string' || !isValidUrl(pdfObject.url)) {
                    Logger.warn('Invalid PDF object', pdfObject);
                    return null;
                }
                return {
                    date: pdfObject.date || pdfObject.filename,
                    link: pdfObject.url || pdfObject.link || pdfObject.downloadUrl,
                    originalUrl: pdfObject.url,
                    originalFilename: pdfObject.filename,
                    paperId: pdfObject.paperId || '',
                    examType: pdfObject.examType || pdfObject.exam_type || '',
                    canonicalPath: pdfObject.canonicalPath || pdfObject.canonical_path || '',
                    downloadUrl: pdfObject.downloadUrl || pdfObject.url || pdfObject.link || ''
                };
            })
            .filter(function (item) { return item !== null; })
            .sort(function (a, b) { return b.date.localeCompare(a.date); });

        var hasInsem = state.pdfFiles.some(function (file) {
            return file.examType === 'insem' || file.originalFilename.toLowerCase().includes('insem');
        });
        var hasEndsem = state.pdfFiles.some(function (file) {
            return file.examType === 'endsem' || file.originalFilename.toLowerCase().includes('endsem');
        });

        var insemBtn = document.querySelector('.exam-toggle-btn[data-value="insem"]');
        var endsemBtn = document.querySelector('.exam-toggle-btn[data-value="endsem"]');

        if (insemBtn) {
            insemBtn.classList.toggle('disabled', !hasInsem);
        }

        if (endsemBtn) {
            endsemBtn.classList.toggle('disabled', !hasEndsem);
        }

        var defaultHasPapers = (DEFAULT_EXAM_TYPE === 'insem' && hasInsem) ||
            (DEFAULT_EXAM_TYPE === 'endsem' && hasEndsem);

        var initialExamType;
        if (defaultHasPapers) {
            initialExamType = DEFAULT_EXAM_TYPE;
        } else if (hasInsem) {
            initialExamType = 'insem';
        } else if (hasEndsem) {
            initialExamType = 'endsem';
        } else {
            initialExamType = DEFAULT_EXAM_TYPE;
        }

        Logger.info('Loaded ' + state.pdfFiles.length + ' papers for ' +
            (subjectNameFromServer || 'this subject'), {
            hasInsem: hasInsem,
            hasEndsem: hasEndsem
        });

        var mobileExamDropdown = document.getElementById('mobile-exam-dropdown');
        if (mobileExamDropdown) {
            var insemOpt = mobileExamDropdown.querySelector('.dropdown-option[data-value="insem"]');
            var endsemOpt = mobileExamDropdown.querySelector('.dropdown-option[data-value="endsem"]');

            if (insemOpt) {
                insemOpt.classList.toggle('disabled', !hasInsem);
            }
            if (endsemOpt) {
                endsemOpt.classList.toggle('disabled', !hasEndsem);
            }
        }

        applyExamType(initialExamType);
    } else {
        DOM.pdfContainer.innerHTML = '<div class="no-pdf-message">No question papers found for this subject.</div>';
        DOM.subjectDisplay.textContent = subjectNameFromServer || 'No Subject';
        Logger.warn('No PDF data available from server');
    }
}


if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}

(function () {
    'use strict';

    var lastDropdownInteractionTime = 0;

    function init() {
        // Record recent interaction with dropdowns/paper-selector to prevent window blur close-race.
        var recordInteraction = function (e) {
            if (e.target.closest('.custom-dropdown') || e.target.closest('.paper-selector')) {
                lastDropdownInteractionTime = Date.now();
            }
        };
        document.addEventListener('mousedown', recordInteraction, true);
        document.addEventListener('touchstart', recordInteraction, true);

        // Close paper selector dropdowns when clicking on an option
        document.addEventListener('click', function (e) {
            var dropdownOption = e.target.closest('.paper-selector .dropdown-option');

            if (dropdownOption) {
                var dropdown = dropdownOption.closest('.custom-dropdown');
                if (dropdown) {
                    setTimeout(function () {
                        dropdown.classList.remove('open');
                    }, 100);
                }
            }
        });

        // Close paper selector dropdowns when clicking outside
        document.addEventListener('click', function (e) {
            if (!e.target.closest('.paper-selector')) {
                document.querySelectorAll('.paper-selector .custom-dropdown.open').forEach(function (dropdown) {
                    dropdown.classList.remove('open');
                });
            }
        });

        // Close all open dropdowns when an iframe steals focus (clicking on PDF viewer area).
        // Iframe clicks don't bubble to document, so we detect them via window blur.
        window.addEventListener('blur', function () {
            // When focus moves to an iframe, window blurs.
            // Use a short delay to avoid racing with intentional dropdown interactions.
            setTimeout(function () {
                if (Date.now() - lastDropdownInteractionTime < 400) {
                    // Do not close dropdowns if user recently interacted with one.
                    return;
                }
                if (document.activeElement && document.activeElement.tagName === 'IFRAME') {
                    CustomDropdown.closeAll();
                }
            }, 50);
        });

        // Also close on mousedown on the container background (gap between iframes)
        var pdfContainer = document.getElementById('pdf-container');
        if (pdfContainer) {
            pdfContainer.addEventListener('mousedown', function (e) {
                if ((e.target === pdfContainer || e.target.closest('.pdf-viewer')) && !e.target.closest('.paper-selector')) {
                    CustomDropdown.closeAll();
                }
            });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();

})();
