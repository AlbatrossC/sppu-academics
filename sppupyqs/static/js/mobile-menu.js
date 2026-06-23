// Mobile Menu Functionality
document.addEventListener('DOMContentLoaded', function() {
    const menuBtn = document.querySelector('.mobile-menu-toggle');
    const mobileMenu = document.getElementById('mobileMenu');
    const closeBtn = document.getElementById('closeMenuBtn');
    const body = document.body;

    if (!menuBtn || !mobileMenu) return;

    function closeMenu() {
        mobileMenu.classList.remove('open');
        menuBtn.classList.remove('active');
        body.style.overflow = '';
    }

    function openMenu() {
        mobileMenu.classList.add('open');
        menuBtn.classList.add('active');
        body.style.overflow = 'hidden';
    }

    function toggleMenu() {
        if (mobileMenu.classList.contains('open')) {
            closeMenu();
        } else {
            openMenu();
        }
    }

    menuBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        toggleMenu();
    });

    if (closeBtn) {
        closeBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            closeMenu();
        });
    }

    mobileMenu.querySelectorAll('a').forEach(link => {
        link.addEventListener('click', closeMenu);
    });

    document.addEventListener('click', function(e) {
        if (mobileMenu.classList.contains('open') &&
            !mobileMenu.contains(e.target) &&
            !menuBtn.contains(e.target)) {
            closeMenu();
        }
    });

    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && mobileMenu.classList.contains('open')) {
            closeMenu();
        }
    });

    window.addEventListener('resize', function() {
        if (window.innerWidth >= 900 && mobileMenu.classList.contains('open')) {
            closeMenu();
        }
    });
});
