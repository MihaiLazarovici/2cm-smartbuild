document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('estimateForm');
    if (form) {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const response = await fetch('/calculate', {
                method: 'POST',
                body: formData
            });
            const data = await response.json();
            const estimates = data.estimates;

            // Update results table
            const tableBody = document.getElementById('resultsTable');
            tableBody.innerHTML = '';
            estimates.breakdown.forEach(item => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${item.element}</td>
                    <td>${item.quantity}</td>
                    <td>${item.unit}</td>
                    <td>£${item.cost}</td>
                    <td>${item.time_days}</td>
                    <td>${item.time_weeks}</td>
                    <td>${item.people}</td>
                `;
                tableBody.appendChild(row);
            });
            document.getElementById('totalCost').textContent = `£${estimates.total_cost}`;
            document.getElementById('totalDays').textContent = estimates.total_time_days;
            document.getElementById('totalWeeks').textContent = estimates.total_time_weeks;
            document.getElementById('totalPeople').textContent = estimates.total_people;
            document.getElementById('results').style.display = 'block';
            if (data.pdf_path) {
                document.getElementById('downloadLink').href = data.pdf_path;
            }

            // Cost Bar Chart
            const costCtx = document.getElementById('costChart').getContext('2d');
            new Chart(costCtx, {
                type: 'bar',
                data: {
                    labels: estimates.breakdown.map(item => item.element),
                    datasets: [{
                        label: 'Cost (£)',
                        data: estimates.breakdown.map(item => item.cost),
                        backgroundColor: 'rgba(0, 123, 255, 0.5)' // Blue
                    }]
                },
                options: { scales: { y: { beginAtZero: true } } }
            });

            // Time Bar Chart
            const timeCtx = document.getElementById('timeChart').getContext('2d');
            new Chart(timeCtx, {
                type: 'bar',
                data: {
                    labels: estimates.breakdown.map(item => item.element),
                    datasets: [{
                        label: 'Time (Days)',
                        data: estimates.breakdown.map(item => item.time_days),
                        backgroundColor: 'rgba(253, 126, 20, 0.5)' // Orange
                    }]
                },
                options: { scales: { y: { beginAtZero: true } } }
            });

            // Labor Histogram
            const laborCtx = document.getElementById('laborChart').getContext('2d');
            new Chart(laborCtx, {
                type: 'bar',
                data: {
                    labels: estimates.breakdown.map(item => item.element),
                    datasets: [{
                        label: 'Number of People',
                        data: estimates.breakdown.map(item => item.people),
                        backgroundColor: 'rgba(111, 66, 193, 0.5)' // Violet
                    }]
                },
                options: { scales: { y: { beginAtZero: true } } }
            });
        });
    } else {
        console.error('Form with ID "estimateForm" not found');
    }
});