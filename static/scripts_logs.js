// Refresh the table every 60 seconds
setInterval(() => {
    window.location.reload();
}, 60000);

// Optional: Add sorting logic (if needed)
document.querySelectorAll("th").forEach((header, index) => {
    header.addEventListener("click", () => {
        const table = header.closest("table");
        const rows = Array.from(table.querySelectorAll("tbody tr"));

        const sortedRows = rows.sort((a, b) => {
            const aText = a.cells[index].innerText;
            const bText = b.cells[index].innerText;

            return aText.localeCompare(bText, undefined, { numeric: true });
        });

        rows.forEach(row => row.parentNode.removeChild(row));
        sortedRows.forEach(row => table.querySelector("tbody").appendChild(row));
    });
});
