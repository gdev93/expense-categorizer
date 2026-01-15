document.addEventListener('scroll', function() {
    const header = document.getElementById('stickyHeader');
    if (header) {
        if (window.scrollY > 10) {
            header.classList.add('is-scrolled');
        } else {
            header.classList.remove('is-scrolled');
        }
    }
});
