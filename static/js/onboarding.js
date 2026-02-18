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
    document.addEventListener('click', function(e) {
        const target = e.target.closest('#onboarding-skip-btn, #onboarding-finish-btn');
        if (target) {
            updateOnboardingStep(5);
        }
    });
    let touchstartX = 0;
    let touchendX = 0;
    function handleGesture() {
        const threshold = 50;
        const currentStepEl = document.querySelector('.onboarding-step-content');
        if (!currentStepEl) return;
        const step = parseInt(currentStepEl.id.split('-').pop());
        if (touchendX < touchstartX - threshold) {
            const nextArrow = document.querySelector('.arrow-right');
            if (nextArrow) {
                nextArrow.click();
            } else if (step === 4) {
                const finishBtn = document.getElementById('onboarding-finish-btn');
                if (finishBtn) finishBtn.click();
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
    const replayBtn = document.getElementById('replay-onboarding');
    const replayModal = document.getElementById('replay-modal');
    const replayConfirmBtn = document.getElementById('replay-confirm');
    const replayCancelBtn = document.getElementById('replay-cancel');
    if (replayBtn && replayModal) {
        replayBtn.addEventListener('click', function(e) {
            e.preventDefault();
            replayModal.style.display = 'flex';
        });
        if (replayConfirmBtn) {
            replayConfirmBtn.addEventListener('click', function() {
                updateOnboardingStep(1);
            });
        }
        if (replayCancelBtn) {
            replayCancelBtn.addEventListener('click', function() {
                replayModal.style.display = 'none';
            });
        }
        replayModal.addEventListener('click', function(e) {
            if (e.target === replayModal) {
                replayModal.style.display = 'none';
            }
        });
    }
});
