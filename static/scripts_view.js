document.addEventListener('DOMContentLoaded', () => {
    // Function to confirm deletion of a course
    const deleteButtons = document.querySelectorAll('.delete-button');

    deleteButtons.forEach(button => {
        button.addEventListener('click', (event) => {
            const confirmation = confirm('Êtes-vous sûr de vouloir supprimer ce cours ?');
            if (!confirmation) {
                event.preventDefault(); // Prevents form submission if not confirmed
            }
        });
    });
});
