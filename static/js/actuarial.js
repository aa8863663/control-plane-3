// Actuarial Dashboard JavaScript
// Chart rendering and interactivity

let expandedRow = null;

// Model card drill-down
async function toggleModelDetail(modelName, row) {
    if (expandedRow && expandedRow !== row) {
        expandedRow.nextElementSibling?.remove();
        expandedRow.classList.remove('expanded');
    }

    if (expandedRow === row) {
        row.nextElementSibling?.remove();
        row.classList.remove('expanded');
        expandedRow = null;
        return;
    }

    const response = await fetch(`/api/actuarial/model-detail/${encodeURIComponent(modelName)}`);
    const data = await response.json();

    const detailRow = document.createElement('tr');
    detailRow.classList.add('detail-row');
    detailRow.innerHTML = `
        <td colspan="6" style="padding: 2rem; background: var(--surface2);">
            <h3 style="margin-bottom: 1rem; font-family: 'DM Serif Display', serif;">${data.model}</h3>

            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 2rem;">
                <div>
                    <h4 style="margin-bottom: 0.5rem; font-size: 0.9rem; color: var(--muted);">Temperature Performance</h4>
                    <canvas id="temp-chart-${modelName.replace(/[^a-zA-Z0-9]/g, '')}"></canvas>
                </div>

                <div>
                    <h4 style="margin-bottom: 0.5rem; font-size: 0.9rem; color: var(--muted);">Recent Runs</h4>
                    <table style="width: 100%; font-size: 0.75rem; border-collapse: collapse;">
                        <thead>
                            <tr style="border-bottom: 1px solid var(--border);">
                                <th style="text-align: left; padding: 0.5rem;">Date</th>
                                <th style="text-align: center; padding: 0.5rem;">Temp</th>
                                <th style="text-align: center; padding: 0.5rem;">BIS</th>
                                <th style="text-align: center; padding: 0.5rem;">Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${data.recent_runs.map(run => `
                                <tr style="border-bottom: 1px solid var(--border);">
                                    <td style="padding: 0.5rem;">${new Date(run.created_at).toLocaleDateString()}</td>
                                    <td style="text-align: center; padding: 0.5rem;">${run.temperature}</td>
                                    <td style="text-align: center; padding: 0.5rem;">${run.bis?.toFixed(1) || 'N/A'}%</td>
                                    <td style="text-align: center; padding: 0.5rem;">${run.status}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>

            <div style="margin-top: 1.5rem;">
                <a href="/evidence-pack/${encodeURIComponent(modelName)}"
                   style="display: inline-block; padding: 0.75rem 1.5rem; background: var(--accent); color: #fff; text-decoration: none; border-radius: 4px; font-weight: 600; font-size: 0.75rem;">
                    📥 Download Evidence Pack
                </a>
            </div>
        </td>
    `;

    row.after(detailRow);
    row.classList.add('expanded');
    expandedRow = row;

    renderTempChart(modelName.replace(/[^a-zA-Z0-9]/g, ''), data.temperature_performance);
}

// Temperature performance chart
function renderTempChart(canvasId, tempData) {
    const ctx = document.getElementById(`temp-chart-${canvasId}`).getContext('2d');
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: tempData.map(t => `T=${t.temperature}`),
            datasets: [{
                label: 'Pass Rate (%)',
                data: tempData.map(t => t.pass_rate),
                backgroundColor: '#2563eb',
                borderColor: '#1d4ed8',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    ticks: {
                        color: '#64748b',
                        callback: v => v + '%'
                    },
                    grid: {
                        color: '#e2e8f0'
                    }
                },
                x: {
                    ticks: {
                        color: '#64748b'
                    },
                    grid: {
                        color: '#e2e8f0'
                    }
                }
            },
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        label: (ctx) => ` ${ctx.parsed.y.toFixed(1)}%`
                    }
                }
            }
        }
    });
}

// Provider risk matrix
async function renderProviderRiskMatrix() {
    const response = await fetch('/api/actuarial/provider-risk-matrix');
    const providers = await response.json();

    const ctx = document.getElementById('risk-matrix-chart').getContext('2d');

    new Chart(ctx, {
        type: 'scatter',
        data: {
            datasets: [{
                label: 'Providers',
                data: providers.map(p => ({
                    x: parseFloat(p.avg_bis),
                    y: parseFloat(p.tsi),
                    label: p.provider
                })),
                backgroundColor: providers.map(p => {
                    const bis = parseFloat(p.avg_bis);
                    const tsi = parseFloat(p.tsi);
                    if (bis >= 80 && tsi >= 90) return '#16a34a';
                    if (bis < 70 || tsi < 80) return '#991b1b';
                    return '#d97706';
                }),
                pointRadius: 10,
                pointHoverRadius: 12
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            scales: {
                x: {
                    title: {
                        display: true,
                        text: 'Average BIS (%)',
                        color: '#64748b'
                    },
                    min: 40,
                    max: 100,
                    ticks: {
                        color: '#64748b'
                    },
                    grid: {
                        color: '#e2e8f0'
                    }
                },
                y: {
                    title: {
                        display: true,
                        text: 'TSI (Stability)',
                        color: '#64748b'
                    },
                    min: 70,
                    max: 100,
                    ticks: {
                        color: '#64748b'
                    },
                    grid: {
                        color: '#e2e8f0'
                    }
                }
            },
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const point = context.raw;
                            return `${point.label}: BIS ${point.x.toFixed(1)}%, TSI ${point.y.toFixed(1)}`;
                        }
                    }
                }
            }
        }
    });
}

// Export functions
function exportCSV() {
    const startDate = document.getElementById('start-date')?.value || '';
    const endDate = document.getElementById('end-date')?.value || '';
    const provider = document.getElementById('provider-filter')?.value || '';

    let url = '/api/actuarial/export-csv?';
    if (startDate) url += `start_date=${startDate}&`;
    if (endDate) url += `end_date=${endDate}&`;
    if (provider && provider !== 'all') url += `provider=${provider}`;

    window.location.href = url;
}

function exportPDF() {
    window.location.href = '/api/actuarial/export-pdf';
}

// Alert loading
async function loadAlerts() {
    try {
        const response = await fetch('/api/actuarial/alerts?unacknowledged=true');
        const alerts = await response.json();

        const banner = document.getElementById('alerts-banner');
        if (!banner) return;

        if (alerts.length > 0) {
            banner.innerHTML = `
                <div style="background: rgba(239,68,68,0.1); padding: 1rem; border-radius: 6px; margin-bottom: 1rem; border-left: 4px solid var(--danger);">
                    <strong style="color: var(--danger);">⚠️ ${alerts.length} Alert(s)</strong>
                    <div style="margin-top: 0.5rem;">
                        ${alerts.map(alert => `
                            <div style="padding: 0.5rem 0; border-top: 1px solid var(--border); color: var(--text); font-size: 0.85rem;">
                                <strong>${alert.model}</strong>: BIS dropped to ${alert.actual_value?.toFixed(1)}%
                                <button onclick="acknowledgeAlert(${alert.id})"
                                        style="margin-left: 1rem; padding: 0.25rem 0.75rem; background: var(--danger); color: #fff; border: none; border-radius: 4px; cursor: pointer; font-size: 0.75rem;">
                                    Acknowledge
                                </button>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
            banner.style.display = 'block';
        } else {
            banner.style.display = 'none';
        }
    } catch (error) {
        console.error('Error loading alerts:', error);
    }
}

async function acknowledgeAlert(alertId) {
    await fetch(`/api/actuarial/alerts/${alertId}/acknowledge`, { method: 'POST' });
    loadAlerts();
}

// Date filtering
function filterByDateRange() {
    const startDate = document.getElementById('start-date').value;
    const endDate = document.getElementById('end-date').value;

    let url = '/api/actuarial/audit-trail?';
    if (startDate) url += `start_date=${startDate}&`;
    if (endDate) url += `end_date=${endDate}`;

    fetch(url)
        .then(r => r.json())
        .then(data => {
            // Render audit trail table
            renderAuditTrail(data);
        });
}

function clearDateFilter() {
    document.getElementById('start-date').value = '';
    document.getElementById('end-date').value = '';
    filterByDateRange();
}
