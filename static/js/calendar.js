document.addEventListener("DOMContentLoaded", async () => {
    try {
        const res = await fetch("/api/calendar");
        const events = await res.json();
        console.log("Calendar events:", events);

        const container = document.getElementById("calendar");
        if (!container) return;

        if (!events.length) {
            container.innerHTML = "<p>No events yet. Add some to ClubCalendar.xlsx.</p>";
            return;
        }

        const list = document.createElement("ul");
        events.forEach(ev => {
            const li = document.createElement("li");
            li.textContent = `${ev.start} - ${ev.title} (${ev.type})`;
            list.appendChild(li);
        });
        container.appendChild(list);
    } catch (e) {
        console.error("Error loading calendar:", e);
    }
});
