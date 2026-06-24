// SPPU PYQs - Search and Navigation
document.addEventListener('DOMContentLoaded', function () {
    const searchInput = document.getElementById('paper-search');
    const mobileSearchToggle = document.querySelector('.mobile-search-toggle');
    const searchContainer = document.getElementById('searchContainer');
    const searchDropdown = document.getElementById('searchDropdown');
    const backNavContainer = document.getElementById('backNavContainer');
    const backButton = document.getElementById('backButton');
    const backButtonText = document.getElementById('backButtonText');
    const patternSelects = document.querySelectorAll('.pattern-select');

    patternSelects.forEach((select) => {
        select.addEventListener('change', function () {
            if (this.value && this.value !== window.location.pathname) {
                window.location.href = this.value;
            }
        });
    });

    // Mobile search toggle
    if (mobileSearchToggle) {
        mobileSearchToggle.addEventListener('click', () => {
            searchContainer.classList.toggle('active');
            mobileSearchToggle.classList.toggle('active');
            if (searchContainer.classList.contains('active')) {
                searchInput.focus();
            }
        });
    }

    if (window.SPPUSearch && searchInput && searchDropdown) {
        window.SPPUSearch.attachDropdown({
            input: searchInput,
            dropdown: searchDropdown,
            container: searchContainer,
            limit: 10
        });
    }

    // Responsive search bar visibility
    function updateSearchBarVisibility() {
        if (window.innerWidth >= 900) {
            searchContainer.classList.add('active');
            searchContainer.style.display = 'flex';
        } else if (!searchContainer.classList.contains('active')) {
            searchContainer.style.display = '';
        }
    }

    updateSearchBarVisibility();
    window.addEventListener('resize', updateSearchBarVisibility);

    // Navigation
    function clearActive() {
        document.querySelectorAll('.nav-level').forEach(el => el.classList.remove('active'));
    }

    function updateBackNavigation(path) {
        if (!backNavContainer || !backButton || !backButtonText) return;
        if (path.length < 2) {
            backNavContainer.hidden = true;
            return;
        }
        backNavContainer.hidden = false;
        
        const parent = path[path.length - 2];
        backButtonText.textContent = `Back to ${parent.name}`;
        backButton.onclick = () => showLevel(parent.target_id);
    }

    window.showLevel = function (levelId) {
        clearActive();
        const level = document.getElementById(levelId);
        if (!level) return;
        level.classList.add('active');
        let path = [];
        try {
            path = JSON.parse(level.getAttribute('data-breadcrumbs') || '[]');
        } catch (_error) {
            path = [];
        }
        updateBackNavigation(path);
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    window.showBranches = function () {
        showLevel('root');
    };

    updateBackNavigation([]);

    // Custom Dropdown Logic
    function setupCustomDropdown(dropdownId, selectedId, optionsId) {
        const dropdown = document.getElementById(dropdownId);
        const selected = document.getElementById(selectedId);
        const optionsContainer = document.getElementById(optionsId);
        if (!dropdown || !selected || !optionsContainer) return;

        selected.addEventListener('click', (e) => {
            e.stopPropagation();
            optionsContainer.classList.toggle('show');
            selected.classList.toggle('open');
        });

        const options = optionsContainer.querySelectorAll('.dropdown-option');
        options.forEach(opt => {
            opt.addEventListener('click', (e) => {
                e.stopPropagation();
                const val = opt.getAttribute('data-value');
                if (val && val !== window.location.pathname) {
                    window.location.href = val;
                } else {
                    optionsContainer.classList.remove('show');
                    selected.classList.remove('open');
                }
            });
        });
    }

    setupCustomDropdown('customPatternDropdown', 'dropdownSelected', 'dropdownOptions');
    setupCustomDropdown('mobilePatternDropdown', 'mobileDropdownSelected', 'mobileDropdownOptions');

    // Close dropdowns on outside click
    document.addEventListener('click', () => {
        document.querySelectorAll('.dropdown-options.show').forEach(el => el.classList.remove('show'));
        document.querySelectorAll('.dropdown-selected.open').forEach(el => el.classList.remove('open'));
    });
});
