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
 * Also handles duplicate form parameters by disabling all but one element with the same name.
 */
let isFormSubmitting = false;

// Global listener to sync elements with the same name associated with the same form
document.addEventListener('change', function(e) {
    const el = e.target;
    if (!el.name) return;

    // We only care about elements that are part of a form (via form property or form attribute)
    const formId = el.getAttribute('form') || (el.form ? el.form.id : null);
    if (!formId) return;

    // Find other elements with the same name associated with the same form
    // either via the 'form' attribute or by being descendants of the form
    const escapedName = CSS.escape(el.name);
    const escapedFormId = CSS.escape(formId);
    const otherEls = document.querySelectorAll(`[name="${escapedName}"][form="${escapedFormId}"], #${escapedFormId} [name="${escapedName}"]`);
    
    otherEls.forEach(other => {
        if (other === el) return;
        
        if (el.type === 'radio' || el.type === 'checkbox') {
            if (other.value === el.value) {
                other.checked = el.checked;
            }
        } else if (el.tagName === 'SELECT' && el.multiple) {
            const selectedValues = Array.from(el.options).filter(opt => opt.selected).map(opt => opt.value);
            Array.from(other.options).forEach(opt => {
                opt.selected = selectedValues.includes(opt.value);
            });
        } else {
            other.value = el.value;
        }
    });
});

function debounceFormSubmit(form) {
    if (isFormSubmitting || !form) return;
    isFormSubmitting = true;

    // To prevent duplicate parameters in the URL (e.g., year=2024&year=2024)
    // which happens when we have both desktop and mobile versions of the same filter
    // both associated with the same form via the 'form' attribute.
    const elementsArray = Array.from(form.elements);
    if (form.id) {
        const externalElements = document.querySelectorAll(`[form="${form.id}"]`);
        externalElements.forEach(el => {
            if (!elementsArray.includes(el)) {
                elementsArray.push(el);
            }
        });
    }

    const namedElements = elementsArray.filter(el =>
        el.name &&
        el.name !== 'csrfmiddlewaretoken' &&
        !el.disabled
    );

    const disabledByUs = [];
    const grouped = {};
    namedElements.forEach(el => {
        if (!grouped[el.name]) grouped[el.name] = [];
        grouped[el.name].push(el);
    });

    for (const name in grouped) {
        const els = grouped[name];
        if (els.length > 1) {
            // Find the "best" element to keep.
            // We use a heuristic for visibility that handles styled radio buttons (which are often display:none).
            const isVisible = el => (el.offsetWidth > 0 || el.offsetHeight > 0) || 
                                   (el.parentElement && (el.parentElement.offsetWidth > 0 || el.parentElement.offsetHeight > 0));

            let best = els.find(el => isVisible(el) && el.checked) ||
                       els.find(el => isVisible(el) && el.type !== 'radio' && el.type !== 'checkbox') ||
                       els.find(el => el.checked) ||
                       els.find(el => isVisible(el)) ||
                       els[0];

            els.forEach(el => {
                if (el !== best) {
                    el.disabled = true;
                    disabledByUs.push(el);
                }
            });
        }
    }

    form.submit();

    // Reset after a timeout just in case the navigation doesn't happen
    // and re-enable elements we disabled
    setTimeout(() => {
        disabledByUs.forEach(el => el.disabled = false);
        isFormSubmitting = false;
    }, 2000);
}

document.addEventListener('DOMContentLoaded', function() {
    // Global listener for main-filter-form to handle deduplication on manual submit
    document.addEventListener('submit', function(e) {
        if (e.target && e.target.id === 'main-filter-form') {
            if (isFormSubmitting) {
                e.preventDefault();
                return;
            }
            e.preventDefault();
            debounceFormSubmit(e.target);
        }
    });

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
