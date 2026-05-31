document.addEventListener('DOMContentLoaded', () => {
    const courseForm = document.getElementById('courseForm');

    // Basic form validation before submission
    courseForm.addEventListener('submit', (event) => {
        const firstName = document.getElementById('first_name').value.trim();
        const lastName = document.getElementById('last_name').value.trim();
        const roomName = document.getElementById('nom_salle').value.trim();
        const courseDate = document.getElementById('date_cours').value;
        const startTime = document.getElementById('heure_debut').value;
        const endTime = document.getElementById('heure_fin').value;

        // Simple validation
        if (!firstName || !lastName || !roomName || !courseDate || !startTime || !endTime) {
            alert('Veuillez remplir tous les champs requis.');
            event.preventDefault(); // Stops form submission if validation fails
        }

        // Check if start time is before end time
        if (startTime >= endTime) {
            alert('L\'heure de début doit être avant l\'heure de fin.');
            event.preventDefault();
        }
    });
});