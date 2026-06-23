// Lazy Download + Zip client for question-papers (vanilla JS)
// Exposes: window.DownloadPaper.handleClick(event, button)

(function () {
	"use strict";

	const REPO_OWNER = "AlbatrossC";
	const REPO_NAME = "sppu-academics";
	const REPO_BRANCH = "sppu-pyqs";
	const RAW_BASE_URL = `https://raw.githubusercontent.com/${REPO_OWNER}/${REPO_NAME}/${REPO_BRANCH}`;
	const GITHUB_CONTENTS_BASE_URL = `https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/contents`;
	const JSZIP_URL = "https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js";
	const FILESAVER_URL = "https://cdnjs.cloudflare.com/ajax/libs/FileSaver.js/2.0.5/FileSaver.min.js";
	const EXAM_TYPES = new Set(["insem", "endsem", "other", "all"]);

	const scriptCache = {};

	function setStatus(msg, level = "info", progress = null) {
		const statusEl = document.getElementById("download-status");
		const containerEl = document.getElementById("download-status-container");
		const progressFillEl = document.getElementById("download-progress-fill");
		const percentageEl = document.getElementById("download-percentage");

		if (!statusEl || !containerEl) return;

		if (containerEl.style.display === "none") {
			containerEl.style.display = "flex";
		}

		statusEl.textContent = msg;
		statusEl.dataset.status = level;

		if (progress !== null && progressFillEl) {
			const progressPercent = Math.min(Math.max(Math.round(progress), 0), 100);
			progressFillEl.style.width = progressPercent + "%";
			progressFillEl.dataset.status = level;

			if (percentageEl) {
				if (progressPercent > 0 && progressPercent < 100) {
					percentageEl.textContent = progressPercent + "%";
					percentageEl.style.display = "inline";
				} else {
					percentageEl.style.display = "none";
				}
			}
		}
	}

	function resetStatus() {
		const containerEl = document.getElementById("download-status-container");
		const progressFillEl = document.getElementById("download-progress-fill");
		const percentageEl = document.getElementById("download-percentage");

		if (containerEl) containerEl.style.display = "none";
		if (progressFillEl) {
			progressFillEl.style.width = "0%";
			delete progressFillEl.dataset.status;
		}
		if (percentageEl) {
			percentageEl.textContent = "";
			percentageEl.style.display = "none";
		}
	}

	function loadScript(url) {
		if (scriptCache[url]) return scriptCache[url];

		scriptCache[url] = new Promise((resolve, reject) => {
			const script = document.createElement("script");
			script.src = url;
			script.async = true;
			script.onload = () => resolve();
			script.onerror = () => reject(new Error("Failed to load " + url));
			document.head.appendChild(script);
		});

		return scriptCache[url];
	}

	function getSubjectLinkFromPath() {
		const parts = location.pathname.split("/").filter(Boolean);
		if (parts.length === 1) return parts[0];
		if (parts.length === 2 && /^\d{4}$/.test(parts[0])) return parts.join("/");
		return "";
	}

	function sanitizeZipPart(value) {
		return String(value || "papers")
			.trim()
			.toLowerCase()
			.replace(/[^a-z0-9]+/g, "_")
			.replace(/^_+|_+$/g, "") || "papers";
	}

	function normalizeCanonicalPath(value) {
		if (!value) return "";

		let path = String(value).trim().replace(/\\/g, "/");
		try {
			if (/^https?:\/\//i.test(path)) {
				const url = new URL(path);
				const papersIndex = url.pathname.indexOf("/papers/");
				path = papersIndex >= 0 ? url.pathname.slice(papersIndex + 1) : "";
			}
		} catch (_) {
			path = "";
		}

		path = path.replace(/^\/+/, "");
		return path.startsWith("papers/") && path.toLowerCase().endsWith(".pdf") ? path : "";
	}

	function getFilename(pathOrName) {
		return String(pathOrName || "").split("/").pop() || "";
	}

	function getFolderPath(canonicalPath) {
		const parts = String(canonicalPath || "").split("/");
		parts.pop();
		return parts.join("/");
	}

	function classifyExamType(paper, filename) {
		const explicit = String(
			paper.examType ||
			paper.exam_type ||
			paper.exam ||
			(paper.source_metadata && paper.source_metadata.exam) ||
			""
		).toLowerCase();

		if (EXAM_TYPES.has(explicit) && explicit !== "all") return explicit;

		const name = String(filename || "").toLowerCase();
		if (name.startsWith("insem_") || name.startsWith("insem-") || name === "insem.pdf") return "insem";
		if (name.startsWith("endsem_") || name.startsWith("endsem-") || name === "endsem.pdf") return "endsem";
		return "other";
	}

	function getQuestionModalData() {
		const existing = window.paperDownloadContext && Array.isArray(window.paperDownloadContext.papers)
			? window.paperDownloadContext
			: null;
		if (existing) return existing;

		const node = document.getElementById("question-modal-data");
		if (!node) return {};

		try {
			return JSON.parse(node.textContent) || {};
		} catch (error) {
			console.warn("Failed to parse question modal data", error);
			return {};
		}
	}

	function getClientId() {
		try {
			const key = "client_id";
			const cached = window.localStorage.getItem(key);
			if (cached) return Promise.resolve(cached);
			const generated = window.crypto && typeof window.crypto.randomUUID === "function"
				? window.crypto.randomUUID()
				: "client-" + Date.now().toString(36);
			window.localStorage.setItem(key, generated);
			return Promise.resolve(generated);
		} catch (error) {
			console.warn("client_id unavailable", error);
			return Promise.resolve("client-anon");
		}
	}

	function normalizeRenderedPapers() {
		const context = getQuestionModalData();
		const papers = Array.isArray(context.papers) ? context.papers : [];

		return papers
			.map((paper) => {
				const canonicalPath = normalizeCanonicalPath(
					paper.canonicalPath ||
					paper.canonical_path ||
					paper.canonical ||
					paper.url ||
					paper.link ||
					paper.pdf_url
				);
				const filename = getFilename(canonicalPath || paper.filename || paper.originalFilename || paper.name);
				if (!filename.toLowerCase().endsWith(".pdf")) return null;

				return {
					name: filename,
					canonicalPath,
					folderPath: getFolderPath(canonicalPath),
					examType: classifyExamType(paper, filename),
					downloadUrl: canonicalPath ? `${RAW_BASE_URL}/${canonicalPath}` : (paper.url || paper.link || paper.pdf_url || "")
				};
			})
			.filter((paper) => paper && paper.downloadUrl);
	}

	function uniqueByName(papers) {
		const seen = new Set();
		return papers.filter((paper) => {
			const key = `${paper.folderPath}/${paper.name}`.toLowerCase();
			if (seen.has(key)) return false;
			seen.add(key);
			return true;
		});
	}

	function filterByExamType(papers, examType) {
		if (examType === "all") return papers;
		return papers.filter((paper) => paper.examType === examType);
	}

	async function fetchJson(url) {
		const response = await fetch(url);
		if (!response.ok) {
			const error = new Error(`HTTP ${response.status}`);
			error.status = response.status;
			throw error;
		}
		return response.json();
	}

	async function fetchGitHubFolder(folderPath) {
		if (!folderPath) return [];

		const encodedPath = folderPath.split("/").map(encodeURIComponent).join("/");
		const url = `${GITHUB_CONTENTS_BASE_URL}/${encodedPath}?ref=${encodeURIComponent(REPO_BRANCH)}`;
		const items = await fetchJson(url);

		if (!Array.isArray(items)) return [];

		return items
			.filter((item) => item.type === "file" && String(item.name || "").toLowerCase().endsWith(".pdf"))
			.map((item) => {
				const canonicalPath = normalizeCanonicalPath(item.path || `${folderPath}/${item.name}`);
				return {
					name: item.name,
					canonicalPath,
					folderPath,
					examType: classifyExamType(item, item.name),
					downloadUrl: canonicalPath ? `${RAW_BASE_URL}/${canonicalPath}` : item.download_url
				};
			});
	}

	async function resolvePapersForDownload(examType) {
		const renderedPapers = uniqueByName(normalizeRenderedPapers());
		if (renderedPapers.length) {
			return filterByExamType(renderedPapers, examType);
		}

		const context = getQuestionModalData();
		const subjectLink = context.subjectLink || getSubjectLinkFromPath();
		if (!subjectLink) return [];

		const list = await fetchJson("/static/search.1.json");
		const meta = Array.isArray(list) && list.find((item) => item.subject_link === subjectLink);
		const folderPath = normalizeCanonicalPath(meta && meta.canonical_path);
		const folderPapers = await fetchGitHubFolder(getFolderPath(folderPath));
		return filterByExamType(uniqueByName(folderPapers), examType);
	}

	function getSubjectName() {
		const context = getQuestionModalData();
		const subjectEl = document.getElementById("download-subject-name");
		return context.subjectName ||
			(window.paperDownloadContext && window.paperDownloadContext.subjectName) ||
			(subjectEl && subjectEl.textContent) ||
			"papers";
	}

	function notifyDownload(subjectLink, subjectName, examType, downloaded) {
		try {
			const context = window.paperDownloadContext || {};
			const clientIdPromise = context.clientIdPromise || getClientId();

			Promise.resolve(clientIdPromise)
				.then((clientId) => fetch("/api/notify-download", {
					method: "POST",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify({
						client_id: clientId,
						subject_link: subjectLink,
						subject_name: subjectName,
						exam_type: examType,
						file_count: downloaded,
						pattern: context.patternYear || "",
						branch: context.branchName || "",
						semester: context.semester || ""
					})
				}))
				.catch((error) => {
					console.warn("notify-download failed", error);
				});
		} catch (error) {
			console.warn("notify-download error", error);
		}
	}

	async function downloadIntoZip(zip, papers) {
		const concurrency = Math.min(4, papers.length);
		let index = 0;
		let downloaded = 0;
		let failed = 0;
		const totalFiles = papers.length;
		const startProgress = 40;
		const endProgress = 85;

		async function worker() {
			while (index < papers.length) {
				const current = papers[index++];
				try {
					const response = await fetch(current.downloadUrl);
					if (!response.ok) throw new Error(`HTTP ${response.status}`);

					zip.file(current.name, await response.arrayBuffer());
					downloaded++;
				} catch (error) {
					failed++;
					console.error("Download error", current.name, error);
				}

				const completed = downloaded + failed;
				const progress = startProgress + ((completed / totalFiles) * (endProgress - startProgress));
				const level = failed ? "warning" : "info";
				const failedText = failed ? `, ${failed} failed` : "";
				setStatus(`Downloaded ${downloaded} of ${totalFiles}${failedText}...`, level, progress);
			}
		}

		await Promise.all(Array.from({ length: concurrency }, worker));
		return { downloaded, failed };
	}

	async function handleClick(event, button) {
		const buttons = document.querySelectorAll("button[data-download]");

		try {
			event && event.preventDefault && event.preventDefault();

			const source = button || (event && event.currentTarget) || (event && event.target);
			const examType = String(source && source.dataset && source.dataset.download || "").toLowerCase();
			if (!EXAM_TYPES.has(examType) || examType === "other") {
				setStatus("Unable to determine download type. Please try again.", "error", 0);
				return;
			}

			buttons.forEach((item) => { item.disabled = true; });
			resetStatus();
			setStatus("Preparing download...", "info", 5);

			setStatus("Finding available papers...", "info", 15);
			let pdfItems;
			try {
				pdfItems = await resolvePapersForDownload(examType);
			} catch (error) {
				console.error("Paper lookup failed", error);
				setStatus("Unable to retrieve paper list. Please try again later.", "error", 0);
				return;
			}

			if (!pdfItems.length) {
				setStatus("No papers found for this download option.", "error", 0);
				return;
			}

			setStatus(`Found ${pdfItems.length} paper${pdfItems.length === 1 ? "" : "s"}. Loading tools...`, "info", 30);
			try {
				await Promise.all([loadScript(JSZIP_URL), loadScript(FILESAVER_URL)]);
			} catch (error) {
				console.error("Download tools failed", error);
				setStatus("Failed to initialize download tools. Please refresh and try again.", "error", 0);
				return;
			}

			if (typeof JSZip === "undefined" || typeof saveAs === "undefined") {
				setStatus("Download tools not available. Please refresh and try again.", "error", 0);
				return;
			}

			const zip = new JSZip();
			setStatus(`Downloading ${pdfItems.length} paper${pdfItems.length === 1 ? "" : "s"}...`, "info", 40);
			const result = await downloadIntoZip(zip, pdfItems);

			if (result.downloaded === 0) {
				setStatus("All downloads failed. Please check your connection and try again.", "error", 0);
				return;
			}

			setStatus("Creating ZIP archive...", "info", 85);
			const blob = await zip.generateAsync({ type: "blob" }, (metadata) => {
				const zipProgress = 85 + ((metadata.percent || 0) * 0.1);
				setStatus(`Creating ZIP file... ${Math.round(metadata.percent || 0)}%`, "info", zipProgress);
			});

			const subjectName = getSubjectName();
			const suffix = examType === "all" ? "papers" : examType;
			const zipName = `${sanitizeZipPart(subjectName)}-${suffix}.zip`;
			saveAs(blob, zipName);
			setStatus("Download complete. Your ZIP file is ready.", result.failed ? "warning" : "success", 100);

			setTimeout(resetStatus, 3000);
			notifyDownload(getSubjectLinkFromPath(), subjectName, examType, result.downloaded);
		} catch (error) {
			console.error(error);
			setStatus("An unexpected error occurred. Please try again.", "error", 0);
		} finally {
			buttons.forEach((item) => { item.disabled = false; });
		}
	}

	window.DownloadPaper = {
		handleClick,
		_resolvePapersForDownload: resolvePapersForDownload
	};
})();
