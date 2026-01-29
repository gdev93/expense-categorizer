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
            m.classList.remove('open-above');
            const otherContainer = m.closest('.category-pill-container');
            if (otherContainer) otherContainer.classList.remove('is-open');
        }
    });

    const isOpening = !menu.classList.contains('show');
    
    if (isOpening) {
        // Reset positioning before calculating
        menu.classList.remove('open-above');
        menu.classList.add('show');

        const rect = menu.getBoundingClientRect();
        const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
        
        // If the menu overflows the bottom of the viewport
        if (rect.bottom > viewportHeight) {
            const spanRect = span.getBoundingClientRect();
            // And if there's more space above the span than below it
            if (spanRect.top > viewportHeight - spanRect.bottom) {
                menu.classList.add('open-above');
            }
        }
    } else {
        menu.classList.remove('show');
        menu.classList.remove('open-above');
    }

    container.classList.toggle('is-open', isOpening);
}

/**
 * Toggles the visibility of the collapsible filter section.
 */
function toggleFilters() {
    const collapsible = document.getElementById('filter-collapsible');
    if (collapsible) {
        collapsible.classList.toggle('show');
    }
}

/**
 * Updates the visual state of filter toggle buttons based on whether filters are active.
 */
function updateFilterButtonsState() {
    document.querySelectorAll('.filters').forEach(form => {
        const toggleBtn = form.querySelector('.filter-toggle-btn');
        if (!toggleBtn) return;

        let hasActiveFilters = false;

        // Check text/search inputs (search, amount)
        form.querySelectorAll('input[type="text"], input[type="search"], input[type="number"]').forEach(input => {
            if (input.value.trim() !== '') {
                hasActiveFilters = true;
            }
        });

        // Check select elements
        form.querySelectorAll('select').forEach(select => {
            // We ignore structural/contextual fields
            if (select.name === 'year' || select.id === 'year' || select.name === 'view_type' || select.name === 'amount_operator') return;

            if (select.multiple) {
                if (Array.from(select.selectedOptions).some(opt => opt.value !== '')) {
                    hasActiveFilters = true;
                }
            } else {
                if (select.value !== '') {
                    hasActiveFilters = true;
                }
            }
        });

        if (hasActiveFilters) {
            toggleBtn.classList.add('filters-active');
        } else {
            toggleBtn.classList.remove('filters-active');
        }
    });
}

/**
 * Truly clears all filter inputs in a form and updates the visual state.
 * @param {string} formId - The ID of the form to clear.
 */
function clearFilters(formId) {
    const form = document.getElementById(formId);
    if (!form) return;

    // form.elements includes all controls belonging to the form (even via form attribute)
    Array.from(form.elements).forEach(el => {
        // We preserve structural filters like year and view_type
        if (el.name === 'view_type' || el.name === 'year' || el.id === 'year' || el.type === 'hidden') {
            return;
        }

        if (el.tagName === 'INPUT') {
            if (['text', 'search', 'number', 'date'].includes(el.type)) {
                el.value = '';
            }
        } else if (el.tagName === 'SELECT') {
            if (el.multiple) {
                Array.from(el.options).forEach(opt => opt.selected = false);
            } else {
                el.selectedIndex = 0;
            }

            // Specific case for amount_operator which might default to 'eq'
            if (el.name === 'amount_operator') {
                el.value = 'eq';
            }
        }
    });

    // Update the filter button visual state
    updateFilterButtonsState();
}

// Initial check and HTMX integration
document.addEventListener('DOMContentLoaded', () => {
    updateFilterButtonsState();
    
    // Update after any HTMX swap to catch changes from the server or user interaction
    document.body.addEventListener('htmx:afterSwap', () => {
        updateFilterButtonsState();
    });
});

// Close menus when clicking outside
document.addEventListener('click', function(event) {
    if (!event.target.closest('.category-pill-container')) {
        document.querySelectorAll('.category-dropdown-menu.show').forEach(menu => {
            menu.classList.remove('show');
            menu.classList.remove('open-above');
            const container = menu.closest('.category-pill-container');
            if (container) container.classList.remove('is-open');
        });
    }
});
