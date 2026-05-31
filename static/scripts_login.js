document.addEventListener("DOMContentLoaded", () => {
    const form = document.querySelector("form");
    const alerts = document.querySelector(".alert");

    form.addEventListener("submit", (event) => {
        // Example of simple client-side validation
        const username = document.querySelector('input[name="username"]').value.trim();
        const password = document.querySelector('input[name="password"]').value.trim();

        if (!username || !password) {
            event.preventDefault(); // Prevent form submission
            showAlert("Please fill in all fields.", "error");
        }
    });

    function showAlert(message, type) {
        alerts.textContent = message;
        alerts.className = `alert ${type}`;
        alerts.style.display = "block";

        // Hide the alert after 3 seconds
        setTimeout(() => {
            alerts.style.display = "none";
        }, 3000);
    }
});