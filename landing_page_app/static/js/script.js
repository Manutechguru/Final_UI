// Wait until DOM is ready
document.addEventListener("DOMContentLoaded", () => {
    console.log("🚀 Dashboard loaded successfully!");

    // -------------------- Counter Animation --------------------
    document.querySelectorAll(".counter").forEach(counter => {
        const target = +counter.dataset.target || 0;
        let count = 0;
        const duration = 1200; // total animation duration in ms
        const startTime = performance.now();

        const animate = (now) => {
            const progress = Math.min((now - startTime) / duration, 1);
            const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
            counter.textContent = Math.floor(eased * target);
            if (progress < 1) requestAnimationFrame(animate);
        };
        requestAnimationFrame(animate);
    });

    // -------------------- Table Row Highlight --------------------
    document.querySelectorAll("table tbody tr").forEach(row => {
        row.addEventListener("click", () => {
            document.querySelectorAll("table tbody tr").forEach(r => r.classList.remove("selected"));
            row.classList.add("selected");
        });
    });

    // -------------------- Pipeline Stage Tooltips --------------------
    document.querySelectorAll(".stage").forEach(stage => {
        let tooltip;
        const showTooltip = () => {
            tooltip = document.createElement("div");
            tooltip.className = "tooltip";
            tooltip.textContent = stage.dataset.info || stage.textContent;
            document.body.appendChild(tooltip);

            const rect = stage.getBoundingClientRect();
            const tooltipRect = tooltip.getBoundingClientRect();
            let left = rect.left + window.scrollX + rect.width / 2 - tooltipRect.width / 2;
            let top = rect.top + window.scrollY - tooltipRect.height - 8;

            // Prevent tooltip from going off screen
            left = Math.max(5, Math.min(left, window.innerWidth - tooltipRect.width - 5));
            if (top < 5) top = rect.bottom + window.scrollY + 8;

            tooltip.style.cssText = `
                position: absolute;
                left: ${left}px;
                top: ${top}px;
                padding: 4px 8px;
                background: rgba(0,0,0,0.85);
                color: #fff;
                border-radius: 4px;
                font-size: 0.85rem;
                pointer-events: none;
                z-index: 9999;
                opacity: 0;
                transition: opacity 0.2s ease-in-out;
            `;
            requestAnimationFrame(() => tooltip.style.opacity = "1");
        };

        const hideTooltip = () => tooltip?.remove();

        stage.addEventListener("mouseenter", showTooltip);
        stage.addEventListener("mouseleave", hideTooltip);
        stage.addEventListener("touchstart", showTooltip);
        stage.addEventListener("touchend", hideTooltip);
    });

    // -------------------- Smooth Scroll --------------------
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener("click", function (e) {
            e.preventDefault();
            document.querySelector(this.getAttribute("href"))?.scrollIntoView({ behavior: "smooth" });
        });
    });

    // -------------------- New Arrivals Fetch --------------------
    const newArrivalsTable = document.querySelector("#new-arrivals-table tbody");
    if (newArrivalsTable) {
        fetch("/landing/new-arrivals")
            .then(res => res.json())
            .then(data => {
                newArrivalsTable.innerHTML = "";
                data.slice(0, 5).forEach(client => {
                    const tr = document.createElement("tr");
                    tr.innerHTML = `
                        <td>${client.name}</td>
                        <td>${client.status}</td>
                        <td>${new Date(client.created_at).toLocaleDateString()}</td>
                    `;
                    newArrivalsTable.appendChild(tr);
                });
            })
            .catch(err => console.error("❌ Error loading new arrivals:", err));
    }

    // -------------------- Candidate Card Hover & Skill Tooltip --------------------
    document.querySelectorAll(".candidate-card").forEach(card => {
        card.addEventListener("mouseenter", () => card.classList.add("highlight"));
        card.addEventListener("mouseleave", () => card.classList.remove("highlight"));
        card.addEventListener("touchstart", () => card.classList.toggle("highlight"));
    });

    // -------------------- Skill Badge Tooltip --------------------
    document.querySelectorAll(".badge-skill").forEach(badge => {
        let tooltip;
        const showBadgeTooltip = () => {
            tooltip = document.createElement("div");
            tooltip.className = "tooltip";
            tooltip.textContent = badge.textContent;
            document.body.appendChild(tooltip);

            const rect = badge.getBoundingClientRect();
            const tooltipRect = tooltip.getBoundingClientRect();
            let left = rect.left + window.scrollX + rect.width / 2 - tooltipRect.width / 2;
            let top = rect.top + window.scrollY - tooltipRect.height - 6;

            left = Math.max(5, Math.min(left, window.innerWidth - tooltipRect.width - 5));
            if (top < 5) top = rect.bottom + window.scrollY + 6;

            tooltip.style.cssText = `
                position: absolute;
                left: ${left}px;
                top: ${top}px;
                padding: 2px 6px;
                background: rgba(0,0,0,0.75);
                color: #fff;
                border-radius: 4px;
                font-size: 0.75rem;
                pointer-events: none;
                z-index: 9999;
                opacity: 0;
                transition: opacity 0.15s ease-in-out;
            `;
            requestAnimationFrame(() => tooltip.style.opacity = "1");
        };

        const hideBadgeTooltip = () => tooltip?.remove();

        badge.addEventListener("mouseenter", showBadgeTooltip);
        badge.addEventListener("mouseleave", hideBadgeTooltip);
        badge.addEventListener("touchstart", showBadgeTooltip);
        badge.addEventListener("touchend", hideBadgeTooltip);
    });

    // -------------------- Resume/Profile Button Hover --------------------
    document.querySelectorAll(".candidate-card a.btn").forEach(btn => {
        btn.addEventListener("mouseenter", () => btn.style.transform = "translateY(-2px)");
        btn.addEventListener("mouseleave", () => btn.style.transform = "translateY(0)");
    });
});
