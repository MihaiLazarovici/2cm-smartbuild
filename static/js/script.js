document.getElementById('estimateForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = {
        projectName: document.getElementById('projectName').value,
        timeFrameDays: document.getElementById('timeFrameDays').value,
        country: 'UK'
    };
    document.querySelectorAll('[id^="quantity_"]').forEach(input => {
        if (input.value) formData[input.id] = input.value;
    });
    document.querySelectorAll('[id^="people_"]').forEach(input => {
        if (input.value) formData[input.id] = input.value;
    });
    const response = await fetch('/calculate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData)
    });
    const data = await response.json();
    console.log("Calculation result:", data);
    const tableBody = document.getElementById('resultsTable').getElementsByTagName('tbody')[0];
    tableBody.innerHTML = '';
    data.breakdown.forEach(item => {
        const row = document.createElement('tr');
        row.innerHTML = `<td>${item.element}</td><td>${item.quantity}</td><td>${item.unit}</td><td>£${item.cost}</td><td>${item.time_days}</td><td>${item.time_weeks}</td><td>${item.people}</td><td>${item.allocated_days || '-'}</td>`;
        tableBody.appendChild(row);
    });
    document.getElementById('totalCost').textContent = `£${data.total_cost}`;
    document.getElementById('maxWorkers').textContent = data.max_people;
    if (data.pdf_path) document.getElementById('downloadLink').href = data.pdf_path;
    document.getElementById('results').style.display = 'block';
    // Chart setup (simplified)
    new Chart(document.getElementById('costChart'), { type: 'bar', data: { labels: data.breakdown.map(d => d.element), datasets: [{ label: 'Cost', data: data.breakdown.map(d => d.cost) }] } });
    new Chart(document.getElementById('timeChart'), { type: 'bar', data: { labels: data.breakdown.map(d => d.element), datasets: [{ label: 'Time', data: data.breakdown.map(d => d.time_days) }] } });
    new Chart(document.getElementById('laborChart'), { type: 'bar', data: { labels: data.breakdown.map(d => d.element), datasets: [{ label: 'People', data: data.breakdown.map(d => d.people) }] } });
});

function updateProgress() {
    // Placeholder for progress update
    alert('Progress update functionality to be implemented');
}