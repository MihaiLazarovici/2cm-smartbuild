document.addEventListener('DOMContentLoaded', function() {
    const ctx = document.createElement('canvas');
    document.body.appendChild(ctx);
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['Sample'],
            datasets: [{
                label: 'Labor Histogram',
                data: [0],
                backgroundColor: 'rgba(75, 192, 192, 0.2)',
                borderColor: 'rgba(75, 192, 192, 1)',
                borderWidth: 1
            }]
        },
        options: {
            scales: {
                y: {
                    beginAtZero: true
                }
            }
        }
    });
});