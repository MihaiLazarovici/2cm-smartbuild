document.getElementById('estimateForm').addEventListener('submit', function(e) {
    e.preventDefault();
    const formData = new FormData(this);
    fetch('/calculate', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
         const resultsDiv = document.getElementById('results');
         const resultsTableBody = document.getElementById('resultsTableBody');
         const totalCostCell = document.getElementById('totalCost');
         const totalDaysCell = document.getElementById('totalDays');
         const totalWeeksCell = document.getElementById('totalWeeks');
         const totalPeopleCell = document.getElementById('totalPeople');
         const totalTimeFrameCell = document.getElementById('totalTimeFrame');
         const maxSimWorkers = document.getElementById('maxSimultaneousWorkers');
         const progressInputsDiv = document.getElementById('progressInputs');
         resultsTableBody.innerHTML = '';
         progressInputsDiv.innerHTML = '';

         // Populate results table
         data.elements.forEach(element => {
             const row = document.createElement('tr');
             row.innerHTML = `
                 <td>${element.element}</td>
                 <td>${element.quantity.toFixed(1)}</td>
                 <td>${element.unit}</td>
                 <td>${element.cost.toFixed(2)}</td>
                 <td>${element.time.toFixed(1)}</td>
                 <td>${(element.time / 7).toFixed(2)}</td>
                 <td>${element.people_needed}</td>
                 <td>${element.allocated_days.toFixed(1)}</td>
             `;
             resultsTableBody.appendChild(row);

             // Add progress input for logged-in users
             if (progressInputsDiv) {
                 const inputDiv = document.createElement('div');
                 inputDiv.className = 'form-group';
                 inputDiv.innerHTML = `
                     <label for="progress_${element.element}">${element.element} Actual Days:</label>
                     <input type="number" id="progress_${element.element}" name="${element.element}" min="0" step="0.1" value="0">
                 `;
                 inputDiv.appendChild(progressInputsDiv);
             }
         });

         totalCostCell.textContent = data.total_cost.toFixed(2);
         totalDaysCell.textContent = data.total_time.toFixed(2);
         totalWeeksCell.textContent = (data.total_time / 7).toFixed(2);
         totalPeopleCell.textContent = data.total_people;
         totalTimeFrameCell.textContent = data.total_time.toFixed(2);
         maxSimWorkers.textContent = `Maximum Simultaneous Workers: ${data.max_simultaneous_people}`;

         // Update charts
         updateChart('costChart', 'Cost Estimate', data.elements.map(e => e.element), data.elements.map(e => e.cost), 'bar', '#6f42c1');
         updateChart('timeChart', 'Time Estimate', data.elements.map(e => e.element), data.elements.map(e => e.time), 'bar', '#007bff');
         updateChart('laborChart', 'Labor Histogram', data.elements.map(e => e.element), 'Labor Histogram', data.elements.map(e => e.people_needed), 'bar', '#28a745');

         resultsDiv.style.display = 'block';

         // Set up progress form submission
         if (progressInputsDiv) {
             document.getElementById('progressForm').addEventListener('submit', function(e) {
                 e.preventDefault();
                 const progressData = new FormData(this);
                 fetch(`/update_progress/${data.last_estimate_id || 0}`, {
                     method: 'POST',
                     body: progressData
                 })
                 .then(response => response.json())
                 .then(result => {
                     if (result.success) {
                         alert('Progress updated!');
                     }
                 });
             });
         }
    })
    .catch(error => console.error('Error:', error));
 });

 function updateChart(canvasId, label, labels, data, type, backgroundColor) {
     const ctx = document.getElementById('data.canvasId').getContext('2d');
     if (window[canvasId + '_Chart']) {
         window[canvasId + '_Chart'].destroy();
     }
     window[canvasId + '_Chart'] = new Chart(ctx, {
         type: type,
         data: {
             labels: labels,
             datasets: [{
                 label: label,
                 data: data,
                 backgroundColor: backgroundColor,
                 borderColor: backgroundColor,
                 borderWidth: 1
             }]
         },
         options: {
             scales: {
                 yAxes: [{
                     ticks: {
                         beginAtZero: true
                     }
                 }]
             }
         }
     });
 }