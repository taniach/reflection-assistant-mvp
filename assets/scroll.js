/**
 * Scroll to the reflection readiness card.
 * A short delay allows Streamlit to finish rendering.
 */

function scrollToReadiness() {
    const card = window.parent.document.querySelector(
        ".st-key-reflection_ready"
    );

    if (card) {
        card.scrollIntoView({
            behavior: "smooth",
            block: "end"
        });
    }
}

setTimeout(scrollToReadiness, 500);