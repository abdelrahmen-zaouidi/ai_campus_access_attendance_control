document.addEventListener('DOMContentLoaded', () => {
    const editForm = document.querySelector('form');

    // Simple form validation
    editForm.addEventListener('submit', (event) => {
        const firstName = document.getElementById('first_name').value.trim();
        const lastName = document.getElementById('last_name').value.trim();
        const roomName = document.getElementById('nom_salle').value.trim();
        const courseDate = document.getElementById('date_cours').value;
        const startTime = document.getElementById('heure_debut').value;
        const endTime = document.getElementById('heure_fin').value;

        if (!firstName || !lastName || !roomName || !courseDate || !startTime || !endTime) {
            alert('Veuillez remplir tous les champs requis.');
            event.preventDefault();
        }

        if (startTime >= endTime) {
            alert('L\'heure de début doit être avant l\'heure de fin.');
            event.preventDefault();
        }
    });
});
