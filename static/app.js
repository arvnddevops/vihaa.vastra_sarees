// Charts
document.addEventListener('DOMContentLoaded', () => {

  // --- helper: % labels for pie/donut ---
  const percentOpts = {
    plugins: {
      datalabels: {
        formatter: (value, ctx) => {
          const data = ctx.chart.data.datasets[0].data || [];
          const total = data.reduce((a, b) => a + b, 0);
          const pct = total ? (value * 100 / total) : 0;
          // show for slices >= 3% (tweak if you want)
          return pct >= 3 ? pct.toFixed(1) + '%' : '';
        },
        anchor: 'end',
        align: 'start',
        offset: 10,
        clamp: true
      },
      tooltip: {
        callbacks: {
          label: (context) => {
            const data = context.dataset.data || [];
            const total = data.reduce((a,b)=>a+b,0);
            const val = context.parsed;
            const pct = total ? (val*100/total).toFixed(1) : 0;
            return `${context.label}: ${val} (${pct}%)`;
          }
        }
      }
    }
  };

  // --- Monthly Sales (bar) ---
  if (window.__monthlyChart) {
    const ctx = document.getElementById('monthlySales');
    new Chart(ctx, {type:'bar', data:{labels:__monthlyChart.labels, datasets:[{label:'Monthly Sales (₹)', data:__monthlyChart.data}]} });
  }

  // --- Saree Types (pie) with % ---
  if (window.__typeChart) {
  const ctx = document.getElementById('typeChart');
  new Chart(ctx, {
    type: 'pie',
    data: { labels: __typeChart.labels, datasets: [{ label: 'Types', data: __typeChart.data }] },
    options: {
      plugins: {
        datalabels: { display: false },   // hide on-slice labels
        legend: {
          labels: {
            generateLabels(chart) {
              const data = chart.data.datasets[0].data || [];
              const total = data.reduce((a,b)=>a+b,0);
              const meta = chart.getDatasetMeta(0);
              return chart.data.labels.map((label, i) => {
                const val = data[i] ?? 0;
                const pct = total ? (val*100/total).toFixed(1) : 0;
                const style = meta.controller.getStyle(i);
                return {
                  text: `${label} — ${pct}% (${val})`,
                  fillStyle: style.backgroundColor,
                  strokeStyle: style.borderColor,
                  lineWidth: style.borderWidth,
                  hidden: isNaN(val) || meta.data[i].hidden,
                  index: i
                };
              });
            }
          }
        },
        tooltip: {
          callbacks: {
            label(ctx) {
              const data = ctx.dataset.data;
              const total = data.reduce((a,b)=>a+b,0);
              const val = ctx.parsed;
              const pct = total ? (val*100/total).toFixed(1) : 0;
              return `${ctx.label}: ${val} (${pct}%)`;
            }
          }
        }
      }
    },
    plugins: (typeof ChartDataLabels !== 'undefined') ? [ChartDataLabels] : []
  });
}

  // --- Payments (donut) with % ---
  if (window.__donut) {
    new Chart(document.getElementById('donut'), {
      type:'doughnut',
      data:{labels:__donut.labels, datasets:[{label:'Amount (₹)', data:__donut.data}]},
      options: percentOpts,
      plugins: (typeof ChartDataLabels !== 'undefined') ? [ChartDataLabels] : []
    });
  }

  // --- Monthly Paid (bar) ---
  if (window.__monthlyPaid) {
    new Chart(document.getElementById('monthlyPaid'), {type:'bar', data:{labels:__monthlyPaid.labels, datasets:[{label:'Paid (₹)', data:__monthlyPaid.data}]} });
  }

  // Couple payment status & mode (enable mode only if Paid)
  const statusSel = document.getElementById('payStatus');
  const modeSel = document.getElementById('payMode');

  if (statusSel && modeSel) {
    function sync() {
      if (statusSel.value === 'Paid') {
        modeSel.disabled = false;
      } else {
        modeSel.value = "";
        modeSel.disabled = true;
      }
    }
    statusSel.addEventListener('change', sync);
    sync();
  }

});
