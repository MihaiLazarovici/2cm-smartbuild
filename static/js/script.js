document.addEventListener('DOMContentLoaded', () => {
         const estimateForm = document.getElementById('estimateForm');
         const progressForm = document.getElementById('progressForm');

         if (estimateForm) {
             estimateForm.addEventListener('submit', async (e) => {
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
                 const progressInputs = document.getElementById('progressInputs');
                 if (progressInputs) progressInputs.innerHTML = '';

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
                         <td>${item.allocated_days || '-'}</td>
                     `;
                     tableBody.appendChild(row);

                     // Add progress inputs for logged-in users
                     if (progressInputs) {
                         const inputDiv = document.createElement('div');
                         inputDiv.className = 'form-group';
                         inputDiv.innerHTML = `
                             <label for="progress_${item.element}">${item.element} Actual Days:</label>
                             <input type="number" id="progress_${item.element}" name="${item.element}" min="0" step="0.1" value="0">
                         `;
                         progressInputs.appendChild(inputDiv);
                     }
                 });

                 document.getElementById('totalCost').textContent = `£${estimates.total_cost}`;
                 document.getElementById('totalDays').textContent = estimates.total_time_days;
                 document.getElementById('totalWeeks').textContent = estimates.total_time_weeks;
                 document.getElementById('totalPeople').textContent = estimates.total_people;
                 document.getElementById('totalTimeFrame').textContent = estimates.total_time_days;
                 document.getElementById('maxSimultaneousWorkers').textContent = `Maximum Simultaneous Workers: ${estimates.max_simultaneous_people}`;
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

                 // Store estimate ID for progress updates
                 if (progressForm && data.estimate_id) {
                     progressForm.dataset.estimateId = data.estimate_id;
                 }
             });
         }

         if (progressForm) {
             progressForm.addEventListener('submit', async (e) => {
                 e.preventDefault();
                 const estimateId = progressForm.dataset.estimateId;
                 if (!estimateId) return alert('No estimate selected');
                 const formData = new FormData(e.target);
                 const response = await fetch(`/update_progress/${estimateId}`, {
                     method: 'POST',
                     body: formData
                 });
                 const data = await response.json();
                 if (data.success) {
                     alert('Progress updated successfully!');
                 } else {
                     alert('Error updating progress: ' + data.message);
                 }
             });
         }
     });