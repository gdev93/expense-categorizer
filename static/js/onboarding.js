document.addEventListener('DOMContentLoaded', function() {
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    function updateOnboardingStep(step) {
        fetch('/onboarding/update-step/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: `step=${step}`
        }).then(response => {
            if (response.ok) {
                if (step >= 5) {
                    const modal = document.getElementById('onboarding-modal-container');
                    if (modal) modal.remove();
                    window.location.reload();
                } else if (step === 1) {
                    window.location.reload();
                }
            }
        });
    }

    // Event delegation for all onboarding clicks
    document.addEventListener('click', function(e) {
        // 1. Skip or Finish onboarding
        const onboardingTarget = e.target.closest('#onboarding-skip-btn, #onboarding-finish-btn');
        if (onboardingTarget) {
            updateOnboardingStep(5);
            return;
        }

        // 2. Show Replay Modal (Sidebar link)
        if (e.target.closest('#replay-onboarding')) {
            e.preventDefault();
            const modal = document.getElementById('replay-modal');
            if (modal) modal.style.display = 'flex';
            return;
        }

        // 3. Confirm Replay button
        if (e.target.closest('#replay-confirm')) {
            updateOnboardingStep(1);
            return;
        }

        // 4. Cancel Replay button or click on backdrop
        const replayModal = document.getElementById('replay-modal');
        if (replayModal) {
            if (e.target.closest('#replay-cancel') || e.target === replayModal) {
                replayModal.style.display = 'none';
                return;
            }
        }
    });

    let touchstartX = 0;
    let touchendX = 0;

    function handleGesture() {
        const threshold = 50;
        const currentStepEl = document.querySelector('.onboarding-step-content');
        if (!currentStepEl) return;
        
        const stepMatch = currentStepEl.id.match(/onboarding-step-(\d+)/);
        if (!stepMatch) return;
        const step = parseInt(stepMatch[1]);

        if (touchendX < touchstartX - threshold) {
            const nextArrow = document.querySelector('.arrow-right');
            if (nextArrow) {
                nextArrow.click();
            } else if (step === 4) {
                updateOnboardingStep(5);
            }
        }
        if (touchendX > touchstartX + threshold) {
            const prevArrow = document.querySelector('.arrow-left');
            if (prevArrow) prevArrow.click();
        }
    }

    document.addEventListener('touchstart', function(e) {
        if (e.target.closest('#onboarding-modal')) {
            touchstartX = e.changedTouches[0].screenX;
        }
    }, {passive: true});

    document.addEventListener('touchend', function(e) {
        if (e.target.closest('#onboarding-modal')) {
            touchendX = e.changedTouches[0].screenX;
            handleGesture();
        }
    }, {passive: true});
});
