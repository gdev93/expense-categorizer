/**
 * Smart back button functionality.
 * If the previous page in history is the same as the current page (e.g., after a redirect or reload),
 * it goes back one more step.
 */
(function() {
    try {
        const lastBackPath = sessionStorage.getItem('lastBackPath');
        if (lastBackPath) {
            if (lastBackPath === window.location.pathname) {
                window.history.back();
                // If we are still here, navigation didn't happen
                setTimeout(() => {
                    if (window.location.pathname === lastBackPath) {
                        sessionStorage.removeItem('lastBackPath');
                    }
                }, 500);
            } else {
                sessionStorage.removeItem('lastBackPath');
            }
        }
    } catch (e) {}
})();

function smartBack() {
    const currentPath = window.location.pathname;
    try {
        sessionStorage.setItem('lastBackPath', currentPath);
    } catch (e) {}
    window.history.back();

    // Fallback: clear after a short delay if navigation didn't happen (no unload)
    setTimeout(() => {
        if (window.location.pathname === currentPath) {
            try {
                sessionStorage.removeItem('lastBackPath');
            } catch (e) {}
        }
    }, 500);
}

/**
 * Debounced form submission to prevent double invocation.
 */
let isFormSubmitting = false;
function debounceFormSubmit(form) {
    if (isFormSubmitting || !form) return;
    isFormSubmitting = true;
    form.submit();

    // Reset after a timeout just in case the navigation doesn't happen
    setTimeout(() => {
        isFormSubmitting = false;
    }, 2000);
}

document.addEventListener('DOMContentLoaded', function() {
    const menuToggle = document.getElementById('menuToggle');
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('overlay');

    // Function to open/close menu
    function toggleMenu() {
        const isClosed = !sidebar.classList.contains('active');

        if (isClosed) {
            sidebar.classList.add('active');
            overlay.classList.add('active');
            // Optional: Prevent body scrolling when menu is open
            document.body.style.overflow = 'hidden';
        } else {
            sidebar.classList.remove('active');
            overlay.classList.remove('active');
            document.body.style.overflow = '';
        }
    }

    // Event Listeners
    if (menuToggle) {
        menuToggle.addEventListener('click', toggleMenu);
    }

    if (overlay) {
        overlay.addEventListener('click', toggleMenu);
    }

    // Close menu when pressing ESC key
    document.addEventListener('keydown', function(event) {
        if (event.key === "Escape" && sidebar.classList.contains('active')) {
            toggleMenu();
        }
    });

    // Logout functionality
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', function() {
            const logoutForm = document.getElementById('logout-form');
            if (logoutForm) {
                logoutForm.submit();
            }
        });
    }
});
// Set active nav item based on current page
function setActiveNavItem() {
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll('.nav-link');

    navLinks.forEach(link => {
        link.classList.remove('active');
        const linkPath = link.getAttribute('data-page') || link.getAttribute('href');

        if (currentPath === linkPath) {
            link.classList.add('active');
        }
    });
}

// Handle nav link clicks
document.querySelectorAll('.nav-link').forEach(link => {
    link.addEventListener('click', function (e) {
        // Remove active class from all links
        document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));

        // Add active class to clicked link
        this.classList.add('active');

        // Close sidebar on mobile
        if (window.innerWidth < 768) {
            sidebar.classList.remove('active');
            overlay.classList.remove('active');
        }

        // Store active page in sessionStorage
        const href = this.getAttribute('href');
        sessionStorage.setItem('activeNavItem', href);
    });
});

// Set active item on page load
setActiveNavItem();

/**
 * Category Dropdown Menu logic
 */
function toggleCategoryMenu(span) {
    const container = span.closest('.category-pill-container');
    const menu = span.nextElementSibling;
    if (!menu || !container) return;

    // Close all other menus first
    document.querySelectorAll('.category-dropdown-menu.show').forEach(m => {
        if (m !== menu) {
            m.classList.remove('show');
            const otherContainer = m.closest('.category-pill-container');
            if (otherContainer) otherContainer.classList.remove('is-open');
        }
    });

    const isOpening = !menu.classList.contains('show');
    menu.classList.toggle('show');
    container.classList.toggle('is-open', isOpening);
}

// Close menus when clicking outside
document.addEventListener('click', function(event) {
    if (!event.target.closest('.category-pill-container')) {
        document.querySelectorAll('.category-dropdown-menu.show').forEach(menu => {
            menu.classList.remove('show');
            const container = menu.closest('.category-pill-container');
            if (container) container.classList.remove('is-open');
        });
    }
});
