// Charts
document.addEventListener('DOMContentLoaded', () => {
  if (window.__monthlyChart) {
    const ctx = document.getElementById('monthlySales');
    new Chart(ctx, {type:'bar', data:{labels:__monthlyChart.labels, datasets:[{label:'Monthly Sales (₹)', data:__monthlyChart.data}]} });
  }
  if (window.__typeChart) {
    const ctx = document.getElementById('typeChart');
    new Chart(ctx, {type:'pie', data:{labels:__typeChart.labels, datasets:[{label:'Types', data:__typeChart.data}]} });
  }
  if (window.__donut) {
    new Chart(document.getElementById('donut'), {type:'doughnut', data:{labels:__donut.labels, datasets:[{label:'Amount (₹)', data:__donut.data}]} });
  }
  if (window.__monthlyPaid) {
    new Chart(document.getElementById('monthlyPaid'), {type:'bar', data:{labels:__monthlyPaid.labels, datasets:[{label:'Paid (₹)', data:__monthlyPaid.data}]} });
  }

  // Couple payment status & mode
  const statusSel = document.getElementById('payStatus');
  const modeSel = document.getElementById('payMode');
  if (statusSel && modeSel) {
    function sync() {
      if (statusSel.value === 'Pending') { modeSel.value = 'Pending'; modeSel.disabled = true; }
      else { if (modeSel.value==='Pending') modeSel.value='UPI'; modeSel.disabled = false; }
    }
    statusSel.addEventListener('change', sync);
    sync();
  }
});
