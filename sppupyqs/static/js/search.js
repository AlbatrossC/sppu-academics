// Shared client-side subject search for SPPU PYQs.
(function () {
    var searchPromise = null;
    var engine = null;
    var MIN_TRIGRAM_SCORE = 0.15;
    var MIN_SHORT_QUERY_SCORE = 0.08;

    function normalize(value) {
        return String(value || "")
            .toLowerCase()
            .replace(/[_\-\/]+/g, " ")
            .replace(/&/g, " and ")
            .replace(/[^a-z0-9 ]+/g, " ")
            .replace(/\s+/g, " ")
            .trim();
    }

    function unique(values) {
        var seen = Object.create(null);
        var output = [];
        values.forEach(function (value) {
            if (!value || seen[value]) {
                return;
            }
            seen[value] = true;
            output.push(value);
        });
        return output;
    }

    function trigrams(value) {
        var text = " " + normalize(value) + " ";
        var grams = [];
        if (text.trim().length < 2) {
            return grams;
        }
        for (var i = 0; i <= text.length - 3; i += 1) {
            grams.push(text.slice(i, i + 3));
        }
        return unique(grams);
    }

    function tokenSimilarity(a, b) {
        var gramsA = trigrams(a);
        var gramsB = trigrams(b);
        var setB = Object.create(null);
        var shared = 0;

        if (!gramsA.length || !gramsB.length) {
            return 0;
        }
        gramsB.forEach(function (gram) {
            setB[gram] = true;
        });
        gramsA.forEach(function (gram) {
            if (setB[gram]) {
                shared += 1;
            }
        });
        return shared / (gramsA.length + gramsB.length - shared);
    }

    function buildEngine(records) {
        var trigramIndex = Object.create(null);
        var abbreviationMap = Object.create(null);
        var branchMap = Object.create(null);
        var branchCodes = Object.create(null);
        var prepared = records.map(function (record, index) {
            var item = {
                raw: record,
                index: index,
                subjectName: normalize(record.subject_name),
                abbreviation: normalize(record.abbreviation),
                branchCode: normalize(record.branch_code),
                subjectTokens: normalize(record.subject_name).split(" ").filter(Boolean),
                subjectTrigrams: trigrams(record.subject_name)
            };

            item.subjectTrigrams.forEach(function (gram) {
                if (!trigramIndex[gram]) {
                    trigramIndex[gram] = [];
                }
                trigramIndex[gram].push(item);
            });

            if (item.abbreviation) {
                if (!abbreviationMap[item.abbreviation]) {
                    abbreviationMap[item.abbreviation] = [];
                }
                abbreviationMap[item.abbreviation].push(item);
            }

            if (item.branchCode) {
                branchCodes[item.branchCode] = true;
                if (!branchMap[item.branchCode]) {
                    branchMap[item.branchCode] = [];
                }
                branchMap[item.branchCode].push(item);
            }

            return item;
        });

        return {
            records: prepared,
            trigramIndex: trigramIndex,
            abbreviationMap: abbreviationMap,
            branchMap: branchMap,
            branchCodes: branchCodes
        };
    }

    function patternRank(item) {
        return String(item && item.pattern_year || "") === "2019" ? 0 : 1;
    }

    function displayScore(entry) {
        var score = entry.score;
        if (String(entry.item && entry.item.pattern_year || "") === "2019") {
            score += 0.035;
        }
        return score;
    }

    function sortResults(a, b) {
        return displayScore(b) - displayScore(a)
            || patternRank(a.item) - patternRank(b.item)
            || String(a.item.subject_name).localeCompare(String(b.item.subject_name));
    }

    function load() {
        if (engine) {
            return Promise.resolve(engine);
        }
        if (!searchPromise) {
            searchPromise = fetch("__SPPUPYQS_SEARCH_INDEX_URL__")
                .then(function (response) {
                    if (!response.ok) {
                        throw new Error("Search index failed to load");
                    }
                    return response.json();
                })
                .then(function (records) {
                    engine = buildEngine(Array.isArray(records) ? records : []);
                    return engine;
                });
        }
        return searchPromise;
    }

    function destinationFor(item) {
        return item.public_url || (item.subject_link ? "/" + item.subject_link : "/");
    }

    function labelFor(item) {
        var parts = [];
        if (item.sem_no) {
            parts.push(item.branch_name + " - Sem " + item.sem_no);
        } else {
            if (item.branch_name) {
                parts.push(item.branch_name);
            }
            if (item.year_label) {
                parts.push(item.year_label);
            }
        }
        if (item.pattern_year) {
            parts.push(item.pattern_year + " Pattern");
        }
        return parts.join(" - ");
    }

    function subjectCardMeta(item) {
        var parts = [];
        if (item.pattern_year) {
            parts.push(item.pattern_year + " Pattern");
        }
        if (item.year_label) {
            parts.push(item.year_label);
        }
        if (item.branch_name) {
            parts.push(item.branch_name);
        }
        if (item.sem_no) {
            parts.push("Sem " + item.sem_no);
        }
        return parts.join(" - ");
    }

    function isShortFormQuery(query) {
        var normalized = normalize(query);
        return normalized.length > 0 && normalized.length <= 5 && normalized.indexOf(" ") === -1;
    }

    function shortFormSearch(searchEngine, query) {
        var normalized = normalize(query);
        var exact = searchEngine.abbreviationMap[normalized];
        if (exact && exact.length) {
            exact.sort(function (a, b) {
                return patternRank(a.raw) - patternRank(b.raw)
                    || String(a.raw.subject_name).localeCompare(String(b.raw.subject_name));
            });
            return [{ item: exact[0].raw, score: 1, priority: "abbreviation-exact" }];
        }

        var prefixMatches = [];
        Object.keys(searchEngine.abbreviationMap).forEach(function (abbr) {
            if (abbr.indexOf(normalized) === 0) {
                searchEngine.abbreviationMap[abbr].forEach(function (item) {
                    prefixMatches.push({ item: item.raw, score: 1, priority: "abbreviation-prefix" });
                });
            }
        });
        if (prefixMatches.length) {
            return prefixMatches.sort(sortResults);
        }

        var branchMatches = searchEngine.branchMap[normalized];
        if (branchMatches && branchMatches.length) {
            return branchMatches.map(function (item) {
                return { item: item.raw, score: 1, priority: "branch-code" };
            }).sort(sortResults);
        }

        return [];
    }

    function extractBranchFilter(searchEngine, query) {
        var normalized = normalize(query);
        var queryTokens = normalized.split(" ").filter(Boolean);
        var branchCode = "";
        var remainingTokens = [];

        queryTokens.forEach(function (token) {
            if (!branchCode && searchEngine.branchCodes[token]) {
                branchCode = token;
                return;
            }
            remainingTokens.push(token);
        });

        return {
            branchCode: branchCode,
            query: remainingTokens.join(" ")
        };
    }

    function lexicalBoost(item, query) {
        var queryTokens = normalize(query).split(" ").filter(Boolean);

        if (!queryTokens.length) {
            return 0;
        }
        if (item.subjectName === query) {
            return 1;
        }
        if (item.subjectName.indexOf(query) === 0) {
            return 0.75;
        }
        if (item.subjectName.indexOf(query) !== -1) {
            return 0.55;
        }

        if (queryTokens.length === 1) {
            for (var i = 0; i < item.subjectTokens.length; i += 1) {
                if (item.subjectTokens[i].indexOf(queryTokens[0]) === 0) {
                    return 0.42;
                }
            }
            return 0;
        }

        var matchedTokens = 0;
        queryTokens.forEach(function (queryToken) {
            for (var i = 0; i < item.subjectTokens.length; i += 1) {
                if (
                    item.subjectTokens[i].indexOf(queryToken) === 0
                    || (item.subjectTokens[i].length > 2 && queryToken.indexOf(item.subjectTokens[i]) === 0)
                    || (
                        Math.abs(queryToken.length - item.subjectTokens[i].length) <= 2
                        && tokenSimilarity(queryToken, item.subjectTokens[i]) >= 0.7
                    )
                ) {
                    matchedTokens += 1;
                    return;
                }
            }
        });

        if (matchedTokens === queryTokens.length) {
            return 0.38 + (0.03 * matchedTokens);
        }
        return 0;
    }

    function trigramSearch(searchEngine, query, options) {
        var normalized = normalize(query);
        var queryTrigrams = trigrams(normalized);
        var candidateCounts = Object.create(null);
        var candidateItems = Object.create(null);
        var candidatePool = options && options.candidatePool ? options.candidatePool : null;
        var allowed = null;

        if (candidatePool) {
            allowed = Object.create(null);
            candidatePool.forEach(function (item) {
                allowed[item.index] = true;
            });
        }

        if (queryTrigrams.length === 0) {
            return [];
        }

        searchEngine.records.forEach(function (item) {
            if (allowed && !allowed[item.index]) {
                return;
            }
            if (lexicalBoost(item, normalized) > 0) {
                candidateCounts[item.index] = candidateCounts[item.index] || 0;
                candidateItems[item.index] = item;
            }
        });

        queryTrigrams.forEach(function (gram) {
            var matches = searchEngine.trigramIndex[gram] || [];
            matches.forEach(function (item) {
                if (allowed && !allowed[item.index]) {
                    return;
                }
                candidateCounts[item.index] = (candidateCounts[item.index] || 0) + 1;
                candidateItems[item.index] = item;
            });
        });

        return Object.keys(candidateCounts)
            .map(function (key) {
                var item = candidateItems[key];
                var shared = candidateCounts[key];
                var denominator = queryTrigrams.length + item.subjectTrigrams.length - shared;
                var score = denominator > 0 ? shared / denominator : 0;
                var lexicalScore = lexicalBoost(item, normalized);
                score += lexicalScore;

                return { item: item.raw, score: score, lexicalScore: lexicalScore, priority: "subject-name" };
            })
            .filter(function (entry) {
                var threshold = normalized.length <= 5 ? MIN_SHORT_QUERY_SCORE : MIN_TRIGRAM_SCORE;
                return entry.score >= threshold;
            })
            .filter(function (entry, _index, entries) {
                return !entries.some(function (candidate) {
                    return candidate.lexicalScore >= 0.38;
                }) || entry.lexicalScore > 0;
            })
            .sort(sortResults);
    }

    function searchSync(searchEngine, query, options) {
        var normalized = normalize(query);
        var branchFilter;
        var candidatePool = null;
        var searchableQuery = normalized;
        var results;

        if (normalized.length < 2) {
            return [];
        }

        if (isShortFormQuery(normalized)) {
            results = shortFormSearch(searchEngine, normalized);
            if (results.length) {
                return results.slice(0, options && options.limit ? options.limit : 10);
            }
        }

        branchFilter = extractBranchFilter(searchEngine, normalized);
        if (branchFilter.branchCode && branchFilter.query) {
            candidatePool = searchEngine.branchMap[branchFilter.branchCode] || [];
            searchableQuery = branchFilter.query;
        }

        results = trigramSearch(searchEngine, searchableQuery, { candidatePool: candidatePool });
        return results.slice(0, options && options.limit ? options.limit : 10);
    }

    function search(query, options) {
        return load().then(function (searchEngine) {
            return searchSync(searchEngine, query, options || {});
        });
    }

    function debounce(callback, delay) {
        var timer = null;
        return function () {
            var args = arguments;
            clearTimeout(timer);
            timer = setTimeout(function () {
                callback.apply(null, args);
            }, delay);
        };
    }

    function attachDropdown(config) {
        var input = config.input;
        var dropdown = config.dropdown;
        var container = config.container || input.parentElement;
        var limit = config.limit || 10;
        var showNoResults = config.showNoResults !== false;
        var activeIndex = -1;
        var searchSerial = 0;

        if (!input || !dropdown) {
            return;
        }

        function clearDropdown() {
            dropdown.innerHTML = "";
            dropdown.style.display = "none";
            activeIndex = -1;
        }

        function updateActiveRow() {
            Array.prototype.forEach.call(dropdown.querySelectorAll(".search-result-row"), function (row, index) {
                row.classList.toggle("active", index === activeIndex);
            });
        }

        function createRow(entry, index) {
            var item = entry.item;
            var row = document.createElement("div");
            var subject = document.createElement("span");
            var branch = document.createElement("span");

            row.className = "search-result-row";
            row.setAttribute("role", "option");
            subject.className = "result-subject";
            branch.className = "result-branch";
            subject.textContent = item.subject_name || "Untitled subject";
            branch.textContent = labelFor(item);

            row.appendChild(subject);
            row.appendChild(branch);
            row.addEventListener("click", function () {
                window.location.href = destinationFor(item);
            });
            row.addEventListener("mouseenter", function () {
                activeIndex = index;
                updateActiveRow();
            });
            return row;
        }

        function renderResults(results) {
            dropdown.innerHTML = "";
            activeIndex = -1;

            if (!results.length) {
                if (showNoResults) {
                    var empty = document.createElement("div");
                    empty.className = "search-no-results";
                    empty.textContent = 'No result found for "' + input.value.trim() + '"';
                    dropdown.appendChild(empty);
                    dropdown.style.display = "block";
                } else {
                    clearDropdown();
                }
                return;
            }

            results.forEach(function (entry, index) {
                dropdown.appendChild(createRow(entry, index));
            });
            dropdown.style.display = "block";
        }

        var runSearch = debounce(function () {
            var query = input.value.trim();
            if (normalize(query).length < 2) {
                clearDropdown();
                return;
            }
            searchSerial += 1;
            var currentSerial = searchSerial;
            search(query, { limit: limit }).then(function (results) {
                if (currentSerial === searchSerial) {
                    renderResults(results);
                }
            }).catch(function () {
                if (currentSerial === searchSerial) {
                    clearDropdown();
                }
            });
        }, 60);

        input.addEventListener("input", runSearch);
        input.addEventListener("keydown", function (event) {
            var rows = dropdown.querySelectorAll(".search-result-row");
            if (!rows.length) {
                return;
            }
            if (event.key === "ArrowDown") {
                event.preventDefault();
                activeIndex = (activeIndex + 1) % rows.length;
                updateActiveRow();
            } else if (event.key === "ArrowUp") {
                event.preventDefault();
                activeIndex = activeIndex <= 0 ? rows.length - 1 : activeIndex - 1;
                updateActiveRow();
            } else if (event.key === "Enter") {
                event.preventDefault();
                if (activeIndex < 0) {
                    activeIndex = 0;
                }
                rows[activeIndex].click();
            }
        });
        input.addEventListener("focus", function () {
            if (dropdown.children.length) {
                dropdown.style.display = "block";
            }
        });
        document.addEventListener("click", function (event) {
            if (container && !container.contains(event.target)) {
                dropdown.style.display = "none";
            }
        });
    }

    window.SPPUSearch = {
        load: load,
        search: search,
        attachDropdown: attachDropdown,
        normalize: normalize,
        destinationFor: destinationFor,
        labelFor: labelFor,
        subjectCardMeta: subjectCardMeta
    };
})();
