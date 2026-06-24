(function () {
	"use strict";

	const JSZIP_URL = "https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js";
	const FILESAVER_URL = "https://cdnjs.cloudflare.com/ajax/libs/FileSaver.js/2.0.5/FileSaver.min.js";
	const EXAM_TYPES = new Set(["insem", "endsem", "other", "all"]);
	const BUTTON_SELECTOR = "button[data-download]";
	const scriptCache = {};

	function getStatusElements() {
		return {
			container: document.getElementById("download-status-container"),
			status: document.getElementById("download-status"),
			progressFill: document.getElementById("download-progress-fill"),
			percentage: document.getElementById("download-percentage"),
		};
	}

	function showStatus(message, level, progress) {
		const elements = getStatusElements();
		if (!elements.container || !elements.status) return;

		elements.container.style.display = "flex";
		elements.status.textContent = message || "";
		elements.status.dataset.status = level || "info";

		if (!elements.progressFill) return;

		if (typeof progress === "number") {
			const percent = Math.max(0, Math.min(100, Math.round(progress)));
			elements.progressFill.style.width = `${percent}%`;
			elements.progressFill.dataset.status = level || "info";

			if (elements.percentage) {
				if (percent > 0 && percent < 100) {
					elements.percentage.textContent = `${percent}%`;
					elements.percentage.style.display = "inline";
				} else {
					elements.percentage.textContent = "";
					elements.percentage.style.display = "none";
				}
			}
		}
	}

	function resetStatus() {
		const elements = getStatusElements();
		if (elements.container) {
			elements.container.style.display = "none";
		}
		if (elements.status) {
			elements.status.textContent = "";
			delete elements.status.dataset.status;
		}
		if (elements.progressFill) {
			elements.progressFill.style.width = "0%";
			delete elements.progressFill.dataset.status;
		}
		if (elements.percentage) {
			elements.percentage.textContent = "";
			elements.percentage.style.display = "none";
		}
	}

	function loadScript(url) {
		if (scriptCache[url]) {
			return scriptCache[url];
		}

		scriptCache[url] = new Promise((resolve, reject) => {
			const existing = document.querySelector(`script[src="${url}"]`);
			if (existing) {
				if (existing.dataset.loaded === "true") {
					resolve();
					return;
				}
				existing.addEventListener("load", () => resolve(), { once: true });
				existing.addEventListener("error", () => reject(new Error(`Failed to load ${url}`)), { once: true });
				return;
			}

			const script = document.createElement("script");
			script.src = url;
			script.async = true;
			script.onload = () => {
				script.dataset.loaded = "true";
				resolve();
			};
			script.onerror = () => reject(new Error(`Failed to load ${url}`));
			document.head.appendChild(script);
		});

		return scriptCache[url];
	}

	function normalizeString(value) {
		return String(value || "").trim();
	}

	function normalizeBaseUrl(value) {
		return normalizeString(value).replace(/\/+$/, "");
	}

	function normalizeCanonicalPath(value) {
		let path = normalizeString(value).replace(/\\/g, "/");
		if (!path) return "";

		try {
			if (/^https?:\/\//i.test(path)) {
				const parsed = new URL(path);
				const papersIndex = parsed.pathname.indexOf("/papers/");
				path = papersIndex >= 0 ? parsed.pathname.slice(papersIndex + 1) : parsed.pathname.replace(/^\/+/, "");
			}
		} catch (_) {
			return "";
		}

		path = path.replace(/^\/+/, "");
		return path.toLowerCase().endsWith(".pdf") ? path : "";
	}

	function getFilename(value) {
		return normalizeString(value).split("/").pop() || "";
	}

	function classifyExamType(paper, filename) {
		const explicit = normalizeString(
			paper.examType ||
			paper.exam_type ||
			paper.exam ||
			(paper.source_metadata && paper.source_metadata.exam)
		).toLowerCase();
		if (EXAM_TYPES.has(explicit) && explicit !== "all") {
			return explicit;
		}

		const lowerName = normalizeString(filename).toLowerCase();
		if (lowerName.startsWith("insem_") || lowerName.startsWith("insem-") || lowerName === "insem.pdf") {
			return "insem";
		}
		if (lowerName.startsWith("endsem_") || lowerName.startsWith("endsem-") || lowerName === "endsem.pdf") {
			return "endsem";
		}
		return "other";
	}

	function readViewerPageData() {
		const node = document.getElementById("viewer-page-data");
		if (!node) return {};

		try {
			return JSON.parse(node.textContent || "{}") || {};
		} catch (error) {
			console.warn("Failed to parse viewer-page-data", error);
			return {};
		}
	}

	function getContext() {
		const viewerData = readViewerPageData();
		const runtime = window.paperDownloadContext || {};
		const papers = Array.isArray(runtime.papers)
			? runtime.papers
			: (Array.isArray(viewerData.papers) ? viewerData.papers : []);

		return {
			subjectLink: runtime.subjectLink || viewerData.subjectLink || getSubjectLinkFromPath(),
			subjectName: runtime.subjectName || viewerData.subjectName || "",
			branchName: runtime.branchName || viewerData.branchName || "",
			patternYear: runtime.patternYear || viewerData.patternYear || "",
			semester: runtime.semester || viewerData.semester || "",
			analyticsEndpoint: runtime.analyticsEndpoint || viewerData.analyticsEndpoint || "/api/notify-download",
			clientIdPromise: runtime.clientIdPromise || null,
			papers,
		};
	}

	function getSubjectLinkFromPath() {
		const parts = location.pathname.split("/").filter(Boolean);
		if (parts.length === 1) return parts[0];
		if (parts.length === 2 && /^\d{4}$/.test(parts[0])) return parts.join("/");
		return "";
	}

	function getClientId() {
		const context = getContext();
		if (context.clientIdPromise) {
			return Promise.resolve(context.clientIdPromise);
		}

		try {
			const storageKey = "client_id";
			const existing = window.localStorage.getItem(storageKey);
			if (existing) return Promise.resolve(existing);

			const generated = window.crypto && typeof window.crypto.randomUUID === "function"
				? window.crypto.randomUUID()
				: `client-${Date.now().toString(36)}`;
			window.localStorage.setItem(storageKey, generated);
			return Promise.resolve(generated);
		} catch (error) {
			console.warn("Unable to access client_id storage", error);
			return Promise.resolve("client-anon");
		}
	}

	function inferBaseUrl(papers) {
		for (const paper of papers) {
			const canonicalPath = normalizeCanonicalPath(
				paper.canonicalPath ||
				paper.canonical_path ||
				paper.canonical
			);
			const directUrl = normalizeString(
				paper.pdf_url ||
				paper.downloadUrl ||
				paper.url ||
				paper.link
			);

			if (!directUrl) continue;

			if (canonicalPath && directUrl.endsWith(canonicalPath)) {
				return normalizeBaseUrl(directUrl.slice(0, directUrl.length - canonicalPath.length));
			}

			try {
				const parsed = new URL(directUrl);
				return normalizeBaseUrl(`${parsed.origin}${parsed.pathname.substring(0, parsed.pathname.lastIndexOf("/"))}`);
			} catch (_) {
				// Keep searching for a usable direct URL.
			}
		}

		return "";
	}

	function buildDownloadUrl(baseUrl, paper, canonicalPath) {
		if (baseUrl && canonicalPath) {
			return `${baseUrl}/${canonicalPath}`;
		}
		return normalizeString(paper.pdf_url || paper.downloadUrl || paper.url || paper.link);
	}

	function sanitizePapers(rawPapers) {
		const papers = Array.isArray(rawPapers) ? rawPapers : [];
		const baseUrl = inferBaseUrl(papers);
		const seen = new Set();

		return papers
			.map((paper) => {
				const canonicalPath = normalizeCanonicalPath(
					paper.canonicalPath ||
					paper.canonical_path ||
					paper.canonical ||
					paper.pdf_url ||
					paper.downloadUrl ||
					paper.url ||
					paper.link
				);
				const fallbackName = paper.filename || paper.originalFilename || paper.name || "";
				const filename = getFilename(canonicalPath || fallbackName);
				const downloadUrl = buildDownloadUrl(baseUrl, paper, canonicalPath);

				if (!filename || !filename.toLowerCase().endsWith(".pdf") || !downloadUrl) {
					return null;
				}

				return {
					name: filename,
					canonicalPath,
					downloadUrl,
					examType: classifyExamType(paper, filename),
				};
			})
			.filter((paper) => {
				if (!paper) return false;
				const key = `${paper.canonicalPath}::${paper.name}`.toLowerCase();
				if (seen.has(key)) return false;
				seen.add(key);
				return true;
			});
	}

	function resolvePapersForDownload(examType) {
		const papers = sanitizePapers(getContext().papers);
		if (examType === "all") {
			return papers;
		}
		return papers.filter((paper) => paper.examType === examType);
	}

	function sanitizeZipPart(value) {
		return normalizeString(value || "papers")
			.toLowerCase()
			.replace(/[^a-z0-9]+/g, "_")
			.replace(/^_+|_+$/g, "") || "papers";
	}

	function getSubjectName() {
		const context = getContext();
		const node = document.getElementById("download-subject-name");
		return context.subjectName || (node && node.textContent) || "papers";
	}

	function setButtonsDisabled(disabled) {
		document.querySelectorAll(BUTTON_SELECTOR).forEach((button) => {
			button.disabled = !!disabled;
		});
	}

	async function ensureDownloadTools() {
		await Promise.all([loadScript(JSZIP_URL), loadScript(FILESAVER_URL)]);
		if (typeof window.JSZip === "undefined" || typeof window.saveAs === "undefined") {
			throw new Error("ZIP dependencies are unavailable");
		}
	}

	async function fetchPdfAsArrayBuffer(url) {
		const response = await fetch(url, { credentials: "omit" });
		if (!response.ok) {
			throw new Error(`HTTP ${response.status}`);
		}
		return response.arrayBuffer();
	}

	async function downloadIntoZip(zip, papers) {
		const concurrency = Math.max(1, Math.min(4, papers.length));
		let nextIndex = 0;
		let successCount = 0;
		let failureCount = 0;

		async function worker() {
			while (nextIndex < papers.length) {
				const current = papers[nextIndex++];
				try {
					const fileBuffer = await fetchPdfAsArrayBuffer(current.downloadUrl);
					zip.file(current.name, fileBuffer);
					successCount += 1;
				} catch (error) {
					failureCount += 1;
					console.error("Failed to download paper", current.name, current.downloadUrl, error);
				}

				const completed = successCount + failureCount;
				const progress = 40 + ((completed / papers.length) * 45);
				const failedSuffix = failureCount ? `, ${failureCount} failed` : "";
				showStatus(`Downloaded ${successCount} of ${papers.length}${failedSuffix}...`, failureCount ? "warning" : "info", progress);
			}
		}

		await Promise.all(Array.from({ length: concurrency }, worker));
		return { successCount, failureCount };
	}

	function notifyDownload(subjectLink, subjectName, examType, fileCount) {
		const context = getContext();
		const endpoint = normalizeString(context.analyticsEndpoint || "/api/notify-download");
		Promise.resolve(getClientId())
			.then((clientId) => fetch(endpoint, {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({
					client_id: clientId,
					subject_link: subjectLink,
					subject_name: subjectName,
					exam_type: examType,
					file_count: fileCount,
					pattern: context.patternYear || "",
					branch: context.branchName || "",
					semester: context.semester || "",
				}),
			}))
			.catch((error) => {
				console.warn("notify-download failed", error);
			});
	}

	async function handleClick(event, explicitButton) {
		if (event && typeof event.preventDefault === "function") {
			event.preventDefault();
		}

		const button = explicitButton || (event && event.currentTarget) || (event && event.target && event.target.closest && event.target.closest(BUTTON_SELECTOR));
		const examType = normalizeString(button && button.dataset && button.dataset.download).toLowerCase();

		if (!button || !EXAM_TYPES.has(examType) || examType === "other") {
			showStatus("Unable to determine which papers to download.", "error", 0);
			return;
		}

		try {
			setButtonsDisabled(true);
			resetStatus();
			showStatus("Preparing download...", "info", 5);

			const papers = resolvePapersForDownload(examType);
			if (!papers.length) {
				showStatus("No papers found for this download option.", "error", 0);
				return;
			}

			showStatus(`Found ${papers.length} paper${papers.length === 1 ? "" : "s"}. Loading download tools...`, "info", 20);
			await ensureDownloadTools();

			const zip = new window.JSZip();
			showStatus(`Downloading ${papers.length} PDF${papers.length === 1 ? "" : "s"}...`, "info", 40);
			const result = await downloadIntoZip(zip, papers);

			if (!result.successCount) {
				showStatus("All downloads failed. Please try again in a moment.", "error", 0);
				return;
			}

			showStatus("Creating ZIP archive...", "info", 88);
			const blob = await zip.generateAsync({ type: "blob" }, (metadata) => {
				const zipProgress = 88 + ((Number(metadata.percent) || 0) * 0.12);
				showStatus(`Creating ZIP file... ${Math.round(Number(metadata.percent) || 0)}%`, "info", zipProgress);
			});

			const subjectName = getSubjectName();
			const zipSuffix = examType === "all" ? "papers" : examType;
			const fileName = `${sanitizeZipPart(subjectName)}-${zipSuffix}.zip`;
			window.saveAs(blob, fileName);

			showStatus(
				result.failureCount
					? `ZIP ready. ${result.successCount} downloaded, ${result.failureCount} failed.`
					: "Download complete. Your ZIP file is ready.",
				result.failureCount ? "warning" : "success",
				100
			);

			window.setTimeout(resetStatus, 3500);
			notifyDownload(getContext().subjectLink || getSubjectLinkFromPath(), subjectName, examType, result.successCount);
		} catch (error) {
			console.error("Download flow failed", error);
			showStatus("Download failed. Please try again.", "error", 0);
		} finally {
			setButtonsDisabled(false);
		}
	}

	function bindButtons() {
		document.querySelectorAll(BUTTON_SELECTOR).forEach((button) => {
			if (button.dataset.downloadBound === "true") return;
			button.dataset.downloadBound = "true";
			button.addEventListener("click", handleClick);
		});
	}

	function init() {
		bindButtons();
	}

	init();

	window.DownloadPaper = {
		handleClick,
		init,
		resetStatus,
	};
})();
