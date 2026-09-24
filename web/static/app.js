// CFOE Dashboard Application

(function () {
  'use strict';

  // ============================================
  // DOM Elements
  // ============================================
  const elements = {
    status: document.getElementById('status'),
    logPanel: document.getElementById('log-panel'),
    logOutput: document.getElementById('log-output'),
    latestResult: document.getElementById('latest-result'),
    blockchainInfo: document.getElementById('blockchain-info'),
    historyBody: document.getElementById('history-body'),
    metrics: document.getElementById('metrics'),
    blockchainStatus: document.getElementById('blockchain-status'),
    dashboardShell: document.getElementById('dashboard-shell'),
    chimneyVisual: document.getElementById('chimney-visual'),
    historyViewMoreBtn: document.getElementById('history-view-more-btn'),
    riskFilter: document.getElementById('risk-filter'),
    searchInput: document.getElementById('search'),
    compareBox: document.getElementById('compare-box'),
    downloadDialog: document.getElementById('download-dialog'),
    downloadAuditSelect: document.getElementById('download-audit-select'),
    downloadFormatSelect: document.getElementById('download-format-select'),
    downloadOpenBtn: document.getElementById('download-open-btn'),
    downloadCancelBtn: document.getElementById('download-cancel-btn'),
    infoDialog: document.getElementById('info-dialog'),
    infoContent: document.getElementById('info-content'),
    infoCloseBtn: document.getElementById('info-close-btn'),
    approvalPanel: document.getElementById('approval-panel'),
    approvalList: document.getElementById('approval-list'),
    approvalDialog: document.getElementById('approval-dialog'),
    approvalContent: document.getElementById('approval-content'),
    approverName: document.getElementById('approver-name'),
    approvalNotes: document.getElementById('approval-notes'),
    approveBtn: document.getElementById('approve-btn'),
    rejectBtn: document.getElementById('reject-btn'),
    approvalCancelBtn: document.getElementById('approval-cancel-btn'),
    supplierName: document.getElementById('supplier_name'),
    emissions: document.getElementById('emissions'),
    violations: document.getElementById('violations'),
    notes: document.getElementById('notes'),
    sector: document.getElementById('sector'),
    productionVolume: document.getElementById('production_volume'),
    productionUnit: document.getElementById('production_unit'),
    registryId: document.getElementById('registry_id'),
    auditForm: document.getElementById('audit-form'),
    refreshBtn: document.getElementById('refresh-btn'),
    clearBtn: document.getElementById('clear-btn'),
    connectWalletBtn: document.getElementById('connect-wallet-btn'),
    disconnectWalletBtn: document.getElementById('disconnect-wallet-btn'),
    walletAddress: document.getElementById('wallet-address'),
    walletDialog: document.getElementById('wallet-dialog'),
    walletCloseBtn: document.getElementById('wallet-close-btn'),
    walletModalStatus: document.getElementById('wallet-modal-status'),
    walletModalAddress: document.getElementById('wallet-modal-address'),
    walletModalBalance: document.getElementById('wallet-modal-balance'),
    walletModalNetwork: document.getElementById('wallet-modal-network'),
    walletModalConnection: document.getElementById('wallet-modal-connection'),
    walletModalTokenId: document.getElementById('wallet-modal-token-id'),
    walletModalTokenBalance: document.getElementById('wallet-modal-token-balance'),
    walletModalTokenSupply: document.getElementById('wallet-modal-token-supply'),
    walletModalCreditsIssued: document.getElementById('wallet-modal-credits-issued'),
    walletModalCreditsRetired: document.getElementById('wallet-modal-credits-retired'),
    walletCopyBtn: document.getElementById('wallet-copy-btn'),
    walletConnectModalBtn: document.getElementById('wallet-connect-modal-btn'),
    runBtn: document.getElementById('run-btn'),
    // Leaderboard elements
    tabNav: document.getElementById('tab-nav'),
    tabBtns: document.querySelectorAll('.tab-btn'),
    tabContents: document.querySelectorAll('.tab-content'),
    lbPodium: document.getElementById('lb-podium'),
    lbBody: document.getElementById('lb-body'),
    lbUpdated: document.getElementById('lb-updated'),
  };


  // ============================================
  // State
  // ============================================
  const state = {
    audits: [],
    pendingApprovals: [],
    selectedForCompare: [],
    visibleAudits: [],
    logSocket: null,
    currentApprovalAuditId: null,
    splitActivated: false,
    showAllHistory: false,
    walletStatus: { connected: false, address: null },
    blockchainSnapshot: null,
    lbData: [],
    lbLastFetched: null,
    lbInterval: null,
    tokenData: {
      issued: [],
      retired: [],
      nfts: [],
    },
    // Revenue / X402 state
    revenueData: null,
    revenueInterval: null,
  };

  const DOWNLOADABLE_FORMATS = ['txt', 'pdf', 'docx'];

  // ============================================
  // Utility Functions
  // ============================================
  const setStatus = (message, isError = false) => {
    elements.status.textContent = message;
    elements.status.style.color = isError ? '#9f2f2f' : '#1f5a46';
  };

  const classToBadge = (classification) => {
    const cls = classification.toLowerCase().includes('critical')
      ? 'critical'
      : classification.toLowerCase().includes('moderate')
        ? 'moderate'
        : 'low';
    return `<span class="badge ${cls}">${classification}</span>`;
  };

  const formatDate = (isoString) => {
    const date = new Date(isoString);
    return Number.isNaN(date.getTime()) ? isoString : date.toLocaleString();
  };

  const normalizeRiskClass = (classification = '') => {
    const text = classification.toLowerCase();
    if (text.includes('critical')) return 'critical';
    if (text.includes('high')) return 'high';
    if (text.includes('moderate')) return 'moderate';
    return 'low';
  };

  const truncateAddress = (address) => {
    if (!address) return 'N/A';
    if (address.length <= 12) return address;
    return `${address.slice(0, 6)}...${address.slice(-4)}`;
  };

  const syncSplitLayoutFromSession = () => {
    const persisted = sessionStorage.getItem('cfoe_split_layout') === '1';
    if (!persisted) return;
    state.splitActivated = true;
    elements.dashboardShell.classList.add('split-active');
    elements.runBtn.classList.remove('run-btn-hidden');
    elements.runBtn.classList.add('run-btn-visible');
  };

  const activateSplitLayout = () => {
    if (state.splitActivated) return;
    state.splitActivated = true;
    sessionStorage.setItem('cfoe_split_layout', '1');
    elements.dashboardShell.classList.add('split-active');
    setTimeout(() => {
      elements.runBtn.classList.remove('run-btn-hidden');
      elements.runBtn.classList.add('run-btn-visible');
    }, 600);
  };

  const updateChimneyRisk = (classification = 'Low Risk') => {
    if (!elements.chimneyVisual) return;
    elements.chimneyVisual.dataset.risk = normalizeRiskClass(classification);
  };

  // ============================================
  // WebSocket Connection
  // ============================================
  const connectLogSocket = () => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/logs`;

    state.logSocket = new WebSocket(wsUrl);

    state.logSocket.onmessage = (event) => {
      const logMsg = JSON.parse(event.data);
      addLogMessage(logMsg);
    };

    state.logSocket.onerror = () => {
      console.warn('WebSocket connection error');
    };

    state.logSocket.onclose = () => {
      setTimeout(connectLogSocket, 2000);
    };
  };

  const addLogMessage = (logMsg) => {
    if (elements.logPanel && elements.logPanel.style.display === 'none') {
      elements.logPanel.style.display = 'block';
    }

    const logLine = document.createElement('div');
    logLine.className = `log-line log-${logMsg.type}`;
    logLine.textContent = logMsg.message;
    elements.logOutput.appendChild(logLine);
    elements.logOutput.scrollTop = elements.logOutput.scrollHeight;
  };

  const clearLogs = () => {
    elements.logOutput.innerHTML = '';
  };

  const showLogPanel = () => {
    clearLogs();
    elements.logPanel.style.display = 'block';
  };

  const hideLogPanel = () => {
    elements.logPanel.style.display = 'none';
  };

  // ============================================
  // Loading Banner Functions
  // ============================================
  const showLoading = (message = 'Processing...') => {
    const banner = document.getElementById('loading-banner');
    const text = document.getElementById('loading-text');
    if (banner && text) {
      text.textContent = message;
      banner.style.display = 'block';
    }
  };

  const hideLoading = () => {
    const banner = document.getElementById('loading-banner');
    if (banner) {
      banner.style.display = 'none';
    }
  };

  // ============================================
  // API Calls
  // ============================================
  const fetchMetrics = async () => {
    const response = await fetch('/api/metrics');
    const data = await response.json();

    const cards = [
      ['Total Audits', data.total_audits],
      ['Average Risk Score', data.avg_risk_score],
      ['Critical Rate', `${data.critical_rate}%`],
      ['Critical Count', data.classifications['Critical Risk'] ?? 0],
    ];

    elements.metrics.innerHTML = cards
      .map(([label, value]) =>
        `<article class="metric-card"><p class="metric-label">${label}</p><p class="metric-value">${value}</p></article>`
      )
      .join('');
  };

  const fetchBlockchainStatus = async () => {
    try {
      const response = await fetch('/api/blockchain/status');
      const data = await response.json();
      state.blockchainSnapshot = data;

      const statusBadge = data.connected
        ? '<span class="badge low">Connected</span>'
        : '<span class="badge moderate">Offline</span>';

      const walletBadge = data.wallet_connected
        ? '<span class="badge low">Wallet Connected</span>'
        : '<span class="badge critical">Wallet Not Connected</span>';

      if (elements.blockchainStatus) {
        elements.blockchainStatus.innerHTML = `
        <div class="blockchain-grid">
          <div class="blockchain-item">
            <span class="blockchain-label">Connection:</span>
            <span>${statusBadge}</span>
          </div>
          <div class="blockchain-item">
            <span class="blockchain-label">Wallet:</span>
            <span>${walletBadge}</span>
          </div>
          <div class="blockchain-item">
            <span class="blockchain-label">Network:</span>
            <span class="blockchain-value">${data.network}</span>
          </div>
          <div class="blockchain-item">
            <span class="blockchain-label">Address:</span>
            <span class="blockchain-value">${truncateAddress(data.address)}</span>
          </div>
          <div class="blockchain-item">
            <span class="blockchain-label">Balance:</span>
            <span class="blockchain-value">${(data.balance || 0).toFixed(6)} ALGO</span>
          </div>
          <div class="blockchain-item">
            <span class="blockchain-label">Token Balance:</span>
            <span class="blockchain-value">${(data.token_balance || 0).toFixed(1)} CCT</span>
          </div>
          <div class="blockchain-item">
            <span class="blockchain-label">On-Chain Records:</span>
            <span class="blockchain-value">${data.total_blockchain_records || 0} total</span>
          </div>
          <div class="blockchain-item">
            <span class="blockchain-label">Score Anchors:</span>
            <span class="blockchain-value">${data.score_anchors || 0}</span>
          </div>
          <div class="blockchain-item">
            <span class="blockchain-label">HITL Decisions:</span>
            <span class="blockchain-value">${data.hitl_decisions || 0}</span>
          </div>
          <div class="blockchain-item">
            <span class="blockchain-label">Report Hashes:</span>
            <span class="blockchain-value">${data.report_hashes || 0}</span>
          </div>
        </div>
      `;
      }

      if (elements.walletModalBalance) {
        elements.walletModalBalance.textContent = `${(data.balance || 0).toFixed(6)} ALGO`;
      }
      if (elements.walletModalNetwork) {
        elements.walletModalNetwork.textContent = data.network;
        elements.walletModalNetwork.className = data.connected
          ? 'badge low'
          : 'badge moderate';
      }
      if (elements.walletModalConnection) {
        elements.walletModalConnection.textContent = data.connected ? 'Connected' : 'Offline';
        elements.walletModalConnection.className = data.connected
          ? 'badge low'
          : 'badge moderate';
      }
      if (elements.walletModalTokenId) {
        elements.walletModalTokenId.textContent = data.token_id || 'Not Created';
      }
      if (elements.walletModalTokenBalance) {
        elements.walletModalTokenBalance.textContent = `${(data.token_balance || 0).toFixed(1)} CCT`;
      }
      if (elements.walletModalTokenSupply) {
        elements.walletModalTokenSupply.textContent = `${(data.token_supply || 0).toFixed(1)} CCT`;
      }
      if (elements.walletModalCreditsIssued) {
        elements.walletModalCreditsIssued.textContent = `${(data.credits_issued || 0).toFixed(1)} tons`;
      }
      if (elements.walletModalCreditsRetired) {
        elements.walletModalCreditsRetired.textContent = `${(data.credits_retired || 0).toFixed(1)} tons`;
      }
    } catch (error) {
      if (elements.blockchainStatus) {
        elements.blockchainStatus.innerHTML = '<p class="error">Failed to load blockchain status</p>';
      }
    }
  };

  const fetchHistory = async () => {
    const response = await fetch('/api/audits?limit=200');
    const data = await response.json();
    state.audits = data.items || [];
    renderHistory();
    renderCompare();

    if (state.audits.length > 0) {
      renderLatest(state.audits[0]);
    }

    await fetchPendingApprovals();
  };

  const fetchPendingApprovals = async () => {
    const response = await fetch('/api/approvals');
    const data = await response.json();
    state.pendingApprovals = data.items || [];
    renderPendingApprovals();
  };

  const fetchTrajectory = async (supplierName) => {
    try {
      const response = await fetch(`/api/trajectory/${encodeURIComponent(supplierName)}/compliance`);
      const data = await response.json();
      renderTrajectory(data);
    } catch (error) {
      console.error('Failed to fetch trajectory:', error);
    }
  };

  // ============================================
  // Rendering Functions
  // ============================================
  const refreshInputsFromAudit = (item) => {
    elements.supplierName.value = item.supplier_name ?? '';
    elements.emissions.value = item.emissions ?? '';
    elements.violations.value = item.violations ?? '';
    elements.notes.value = item.notes ?? '';
    elements.sector.value = item.sector_key ?? 'default';
    elements.productionVolume.value = item.production_volume ?? '';
    elements.productionUnit.value = item.production_unit ?? 'tonne';
    elements.registryId.value = item.registry_id ?? '';
  };

  const renderLatest = (item) => {
    const statusBadge = item.status === 'pending_approval'
      ? '<span class="badge critical">Pending Approval</span>'
      : item.approval_status === 'rejected'
        ? '<span class="badge critical">Rejected</span>'
        : '<span class="badge low">Completed</span>';

    const sectorInfo = item.sector ? `<div><strong>Sector:</strong> ${item.sector}</div>` : '';
    const intensityInfo = item.emissions_intensity
      ? `<div><strong>Emissions Intensity:</strong> ${item.emissions_intensity.toFixed(3)} tCO2eq/${item.production_unit || 'unit'}</div>`
      : '';
    const prorataInfo = item.prorata_progress
      ? `<div><strong>Pro-rata Progress:</strong> ${(item.prorata_progress * 100).toFixed(1)}% towards ${item.target_year || 2027} target</div>`
      : '';
    const registryInfo = item.registry_id ? `<div><strong>Registry ID:</strong> ${item.registry_id}</div>` : '';

    fetchTrajectory(item.supplier_name);
    updateChimneyRisk(item.classification || 'Low Risk');

    if (!elements.latestResult) {
      return;
    }

    const analysisId = `analysis-${item.audit_id}`;
    const analysisBtnId = `analysis-toggle-${item.audit_id}`;
    const reportAccessHTML = renderReportAccessUI(item);

    elements.latestResult.innerHTML = `
      <div class="latest-block">
        <div class="badges">
          ${classToBadge(item.classification)}
          <span class="badge low">Score ${item.risk_score}</span>
          <span class="badge low">${item.report_source}</span>
          ${statusBadge}
        </div>
        <div><strong>${item.supplier_name}</strong> | Emissions ${item.emissions} | Violations ${item.violations}</div>
        ${sectorInfo}
        ${intensityInfo}
        ${prorataInfo}
        ${registryInfo}
        <div><strong>Decision:</strong> ${item.policy_decision}</div>
        <div><strong>Reason:</strong> ${item.policy_reason}</div>
        <div><strong>Action:</strong> ${item.recommended_action}</div>
        ${item.approver_name ? `<div><strong>Approved by:</strong> ${item.approver_name} on ${formatDate(item.approval_timestamp)}</div>` : ''}
        ${item.approval_notes ? `<div><strong>Approval Notes:</strong> ${item.approval_notes}</div>` : ''}
        ${reportAccessHTML}
        <div class="analysis-toggle-row">
          <button id="${analysisBtnId}" type="button" class="analysis-toggle-btn">Show Analysis</button>
        </div>
        <div id="${analysisId}" class="report-wrap" hidden>
          <div class="report" id="report-content-${item.audit_id}">${item.report_text || 'No report generated.'}</div>
        </div>
        <div id="trajectory-info" style="margin-top: 1rem;"></div>
        ${item.carbon_credits ? renderCreditsHTML(item.carbon_credits) : ''}
      </div>
    `;

    const analysisEl = document.getElementById(analysisId);
    const analysisBtnEl = document.getElementById(analysisBtnId);
    if (analysisEl && analysisBtnEl) {
      analysisBtnEl.addEventListener('click', () => {
        const hidden = analysisEl.hasAttribute('hidden');
        if (hidden) {
          analysisEl.removeAttribute('hidden');
          analysisBtnEl.textContent = 'Hide Analysis';
        } else {
          analysisEl.setAttribute('hidden', '');
          analysisBtnEl.textContent = 'Show Analysis';
        }
      });
    }

    attachReportAccessListeners(item);

    if (item.blockchain) {
      const bc = item.blockchain;
      const onChainBadge = bc.on_chain
        ? '<span class="badge low">On-Chain</span>'
        : '<span class="badge moderate">Local</span>';

      if (elements.blockchainInfo) {
        elements.blockchainInfo.style.display = 'block';
        elements.blockchainInfo.innerHTML = `
        <h3>⛓️ Blockchain Verification</h3>
        <div class="blockchain-details">
          <div class="blockchain-row">
            <span class="blockchain-label">Status:</span>
            <span>${onChainBadge}</span>
          </div>
          ${bc.score_tx ? `
            <div class="blockchain-row">
              <span class="blockchain-label">Score TX:</span>
              <span class="blockchain-value mono">${bc.score_tx}</span>
            </div>
          ` : ''}
          ${bc.score_hash ? `
            <div class="blockchain-row">
              <span class="blockchain-label">Data Hash:</span>
              <span class="blockchain-value mono">${bc.score_hash.substring(0, 32)}...</span>
            </div>
          ` : ''}
          ${bc.verification_code ? `
            <div class="blockchain-row">
              <span class="blockchain-label">Verify Code:</span>
              <span class="blockchain-value mono highlight">${bc.verification_code}</span>
            </div>
          ` : ''}
          ${bc.report_tx ? `
            <div class="blockchain-row">
              <span class="blockchain-label">Report TX:</span>
              <span class="blockchain-value mono">${bc.report_tx}</span>
            </div>
          ` : ''}
          ${bc.hitl_tx ? `
            <div class="blockchain-row">
              <span class="blockchain-label">HITL TX:</span>
              <span class="blockchain-value mono">${bc.hitl_tx}</span>
            </div>
          ` : ''}
        </div>
      `;
      }
    } else {
      if (elements.blockchainInfo) {
        elements.blockchainInfo.style.display = 'none';
      }
    }
  };

  const renderHistory = () => {
    const filter = elements.riskFilter.value;
    const searchQuery = elements.searchInput.value.trim().toLowerCase();

    const filteredAudits = state.audits.filter((audit) => {
      const riskMatch = filter === 'ALL' || audit.classification === filter;
      const searchMatch = !searchQuery || audit.supplier_name.toLowerCase().includes(searchQuery);
      return riskMatch && searchMatch;
    });

    state.visibleAudits = filteredAudits;
    const displayedAudits = state.showAllHistory ? filteredAudits : filteredAudits.slice(0, 5);

    elements.historyBody.innerHTML = displayedAudits
      .map((item) => {
        const isChecked = state.selectedForCompare.includes(item.audit_id) ? 'checked' : '';
        return `
          <tr data-audit-id="${item.audit_id}">
            <td><input type="checkbox" data-audit-id="${item.audit_id}" ${isChecked} /></td>
            <td>${item.supplier_name}</td>
            <td>${classToBadge(item.classification)}</td>
            <td>${item.risk_score}</td>
            <td>${item.policy_decision}</td>
            <td><button type="button" class="row-info-btn" data-audit-id="${item.audit_id}">Info</button></td>
            <td>${formatDate(item.timestamp)}</td>
          </tr>
        `;
      })
      .join('');

    if (filteredAudits.length > 5) {
      elements.historyViewMoreBtn.style.display = 'inline-block';
      elements.historyViewMoreBtn.textContent = state.showAllHistory ? 'Show less' : 'View more';
    } else {
      elements.historyViewMoreBtn.style.display = 'none';
      state.showAllHistory = false;
    }

    attachHistoryListeners();
  };

  const attachHistoryListeners = () => {
    elements.historyBody.querySelectorAll('input[type="checkbox"]').forEach((checkbox) => {
      checkbox.addEventListener('change', handleCheckboxChange);
    });

    elements.historyBody.querySelectorAll('.row-info-btn').forEach((button) => {
      button.addEventListener('click', (event) => {
        event.stopPropagation();
        const id = event.currentTarget.dataset.auditId;
        const item = state.audits.find((a) => a.audit_id === id);
        if (item) {
          openInfoDialog(item);
        }
      });
    });

    elements.historyBody.querySelectorAll('tr[data-audit-id]').forEach((row) => {
      row.addEventListener('click', () => {
        const id = row.dataset.auditId;
        const item = state.audits.find((a) => a.audit_id === id);
        if (item) {
          renderLatest(item);
          refreshInputsFromAudit(item);
          setStatus(`Showing details for ${item.supplier_name}.`);
        }
      });
    });
  };

  const handleCheckboxChange = (event) => {
    event.stopPropagation();
    const id = event.target.dataset.auditId;

    if (event.target.checked) {
      if (!state.selectedForCompare.includes(id)) {
        state.selectedForCompare.push(id);
      }
    } else {
      state.selectedForCompare = state.selectedForCompare.filter((x) => x !== id);
    }

    if (state.selectedForCompare.length > 2) {
      state.selectedForCompare = state.selectedForCompare.slice(state.selectedForCompare.length - 2);
    }

    renderHistory();
    renderCompare();
  };

  const renderCompare = () => {
    const selectedAudits = state.audits.filter((a) => state.selectedForCompare.includes(a.audit_id));

    if (selectedAudits.length !== 2) {
      elements.compareBox.textContent = 'No pair selected.';
      return;
    }

    const [auditA, auditB] = selectedAudits;
    const scoreDelta = (auditB.risk_score - auditA.risk_score).toFixed(2);
    const emissionsDelta = (auditB.emissions - auditA.emissions).toFixed(2);
    const violationsDelta = auditB.violations - auditA.violations;

    const getDeltaClass = (value) =>
      value > 0 ? 'delta-worse' : value < 0 ? 'delta-better' : 'delta-neutral';
    const getDeltaSymbol = (value) => (value > 0 ? '▲' : value < 0 ? '▼' : '=');

    elements.compareBox.innerHTML = `
      <div class="compare-header">
        <h3>Detailed Comparison</h3>
        <p class="compare-timestamp">First: ${formatDate(auditA.timestamp)} | Second: ${formatDate(auditB.timestamp)}</p>
      </div>
      
      <div class="compare-grid">
        ${renderCompareCard(auditA, 'First Selection')}
        ${renderCompareCard(auditB, 'Second Selection')}
      </div>
      
      <div class="compare-delta">
        <h4>Delta Analysis (Second - First)</h4>
        <div class="delta-grid">
          <div class="delta-item ${getDeltaClass(scoreDelta)}">
            <span class="delta-symbol">${getDeltaSymbol(scoreDelta)}</span>
            <span class="delta-label">Risk Score:</span>
            <span class="delta-value">${scoreDelta > 0 ? '+' : ''}${scoreDelta}</span>
          </div>
          <div class="delta-item ${getDeltaClass(emissionsDelta)}">
            <span class="delta-symbol">${getDeltaSymbol(emissionsDelta)}</span>
            <span class="delta-label">Emissions:</span>
            <span class="delta-value">${emissionsDelta > 0 ? '+' : ''}${emissionsDelta} tons</span>
          </div>
          <div class="delta-item ${getDeltaClass(violationsDelta)}">
            <span class="delta-symbol">${getDeltaSymbol(violationsDelta)}</span>
            <span class="delta-label">Violations:</span>
            <span class="delta-value">${violationsDelta > 0 ? '+' : ''}${violationsDelta}</span>
          </div>
        </div>
      </div>
    `;
  };

  const renderCompareCard = (audit, label) => `
    <article class="compare-card">
      <div class="compare-card-header">
        <h4>${audit.supplier_name}</h4>
        <span class="compare-label">${label}</span>
      </div>
      <div class="compare-details">
        <div class="detail-row">
          <span class="detail-label">Risk Classification:</span>
          <span>${classToBadge(audit.classification)}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Risk Score:</span>
          <span class="detail-value">${audit.risk_score}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">CO2 Emissions:</span>
          <span class="detail-value">${audit.emissions} tons</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Violations:</span>
          <span class="detail-value">${audit.violations}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Policy Decision:</span>
          <span class="detail-value">${audit.policy_decision}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Human Approval:</span>
          <span class="detail-value">${audit.human_approval_required ? 'Required' : 'Not Required'}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Recommended Action:</span>
          <span class="detail-value">${audit.recommended_action}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Policy Reason:</span>
          <span class="detail-value detail-reason">${audit.policy_reason}</span>
        </div>
      </div>
    </article>
  `;

  const renderTrajectory = (data) => {
    const trajectoryEl = document.getElementById('trajectory-info');
    if (!trajectoryEl) return;

    if (data.audit_count < 2) {
      trajectoryEl.innerHTML = `
        <div class="trajectory-panel">
          <h4>📊 Multi-Year Trajectory</h4>
          <p class="trajectory-message">${data.message || 'Insufficient historical data for trajectory analysis'}</p>
        </div>
      `;
      return;
    }

    const trendIcon = data.trend === 'improving' ? '📈' : data.trend === 'deteriorating' ? '📉' : '➡️';
    const onTrackBadge = data.on_track === true
      ? '<span class="badge low">✅ On Track</span>'
      : data.on_track === false
        ? '<span class="badge critical">⚠️ Behind Schedule</span>'
        : '<span class="badge moderate">⏳ Monitoring</span>';

    const auditHistory = data.audits.slice(0, 5).map((audit) => `
      <div class="trajectory-audit">
        <span>${audit.timestamp}</span>
        <span>${classToBadge(audit.classification)}</span>
        <span>Score: ${audit.risk_score}</span>
      </div>
    `).join('');

    trajectoryEl.innerHTML = `
      <div class="trajectory-panel">
        <div class="trajectory-header">
          <h4>${trendIcon} Multi-Year Compliance Trajectory</h4>
          ${onTrackBadge}
        </div>
        <div class="trajectory-stats">
          <div class="trajectory-stat">
            <span class="stat-label">Total Audits:</span>
            <span class="stat-value">${data.audit_count}</span>
          </div>
          <div class="trajectory-stat">
            <span class="stat-label">Trend:</span>
            <span class="stat-value">${data.trend_label}</span>
          </div>
          <div class="trajectory-stat">
            <span class="stat-label">Latest Score:</span>
            <span class="stat-value">${data.latest_score}</span>
          </div>
          <div class="trajectory-stat">
            <span class="stat-label">Score Change:</span>
            <span class="stat-value ${data.score_change < 0 ? 'positive' : 'negative'}">${data.score_change > 0 ? '+' : ''}${data.score_change}</span>
          </div>
          ${data.on_track !== null ? `
            <div class="trajectory-stat">
              <span class="stat-label">Years Remaining:</span>
              <span class="stat-value">${data.years_remaining}</span>
            </div>
            <div class="trajectory-stat">
              <span class="stat-label">Required Rate:</span>
              <span class="stat-value">${data.required_rate.toFixed(3)}/year</span>
            </div>
            <div class="trajectory-stat">
              <span class="stat-label">Current Rate:</span>
              <span class="stat-value">${data.improvement_rate.toFixed(3)}/year</span>
            </div>
          ` : ''}
        </div>
        <div class="trajectory-history">
          <h5>Recent Audit History</h5>
          ${auditHistory}
        </div>
      </div>
    `;
  };

  const renderPendingApprovals = () => {
    if (state.pendingApprovals.length === 0) {
      elements.approvalPanel.style.display = 'none';
      return;
    }

    elements.approvalPanel.style.display = 'block';

    elements.approvalList.innerHTML = state.pendingApprovals.map((item) => `
      <article class="approval-card">
        <div class="approval-header">
          <h3>${item.supplier_name}</h3>
          ${classToBadge(item.classification)}
        </div>
        <div class="approval-details">
          <div class="approval-row">
            <span class="approval-label">Risk Score:</span>
            <span class="approval-value">${item.risk_score}</span>
          </div>
          <div class="approval-row">
            <span class="approval-label">Emissions:</span>
            <span class="approval-value">${item.emissions} tons</span>
          </div>
          <div class="approval-row">
            <span class="approval-label">Violations:</span>
            <span class="approval-value">${item.violations}</span>
          </div>
          <div class="approval-row">
            <span class="approval-label">Policy Decision:</span>
            <span class="approval-value">${item.policy_decision}</span>
          </div>
          <div class="approval-row">
            <span class="approval-label">Submitted:</span>
            <span class="approval-value">${formatDate(item.timestamp)}</span>
          </div>
        </div>
        <div class="approval-actions">
          <button type="button" class="review-btn" data-audit-id="${item.audit_id}">Review & Decide</button>
        </div>
      </article>
    `).join('');

    elements.approvalList.querySelectorAll('.review-btn').forEach((button) => {
      button.addEventListener('click', (event) => {
        const id = event.currentTarget.dataset.auditId;
        const item = state.pendingApprovals.find((a) => a.audit_id === id);
        if (item) {
          openApprovalDialog(item);
        }
      });
    });
  };

  // ============================================
  // Dialog Functions
  // ============================================
  const refreshDownloadFormatOptions = () => {
    const selectedAuditId = elements.downloadAuditSelect.value;
    const selectedAudit = state.audits.find((a) => a.audit_id === selectedAuditId);
    const links = selectedAudit?.download_links || {};

    const availableFormats = DOWNLOADABLE_FORMATS.filter((fmt) => links[fmt]);
    elements.downloadFormatSelect.innerHTML = availableFormats
      .map((fmt) => `<option value="${fmt}">${fmt.toUpperCase()}</option>`)
      .join('');
  };

  const openDownloadDialog = (auditId = null) => {
    const source = auditId
      ? state.audits.filter((a) => a.audit_id === auditId)
      : (state.visibleAudits.length ? state.visibleAudits : state.audits);

    if (!source.length) {
      setStatus('No audits available to download.', true);
      return;
    }

    elements.downloadAuditSelect.innerHTML = source
      .map((a) => `<option value="${a.audit_id}">${a.supplier_name} | ${a.audit_id}</option>`)
      .join('');

    refreshDownloadFormatOptions();
    elements.downloadAuditSelect.disabled = Boolean(auditId);
    elements.downloadDialog.showModal();
  };

  const openSelectedDownload = () => {
    const selectedAuditId = elements.downloadAuditSelect.value;
    const selectedFormat = elements.downloadFormatSelect.value;
    const selectedAudit = state.audits.find((a) => a.audit_id === selectedAuditId);
    const href = selectedAudit?.download_links?.[selectedFormat];

    if (!href) {
      setStatus('Selected format is not available for this audit.', true);
      return;
    }

    const link = document.createElement('a');
    link.href = href;
    link.setAttribute('download', '');
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    elements.downloadDialog.close();
    setStatus(`Download started: ${selectedFormat.toUpperCase()} for ${selectedAudit.supplier_name}.`);
  };

  const openInfoDialog = (item) => {
    const downloadAction = `<button type="button" id="info-download-btn">Download Files</button>`;

    let blockchainSection = '';
    if (item.blockchain) {
      const bc = item.blockchain;
      blockchainSection = `
        <hr/>
        <h4>⛓️ Blockchain Verification</h4>
        <p><strong>Status:</strong> ${bc.on_chain ? 'On-Chain' : 'Local Only'}</p>
        ${bc.score_tx ? `<p><strong>Score TX:</strong> <code>${bc.score_tx}</code></p>` : ''}
        ${bc.score_hash ? `<p><strong>Data Hash:</strong> <code>${bc.score_hash.substring(0, 40)}...</code></p>` : ''}
        ${bc.verification_code ? `<p><strong>Verification Code:</strong> <code class="highlight">${bc.verification_code}</code></p>` : ''}
        ${bc.report_tx ? `<p><strong>Report TX:</strong> <code>${bc.report_tx}</code></p>` : ''}
        ${bc.report_hash ? `<p><strong>Report Hash:</strong> <code>${bc.report_hash.substring(0, 40)}...</code></p>` : ''}
        ${bc.hitl_tx ? `<p><strong>HITL Decision TX:</strong> <code>${bc.hitl_tx}</code></p>` : ''}
      `;
    }

    elements.infoContent.innerHTML = `
      <p><strong>Job ID:</strong> ${item.job_id || '-'}</p>
      <p><strong>Audit ID:</strong> ${item.audit_id}</p>
      <p><strong>Timestamp:</strong> ${formatDate(item.timestamp)}</p>
      <p><strong>Supplier:</strong> ${item.supplier_name}</p>
      <p><strong>Emissions:</strong> ${item.emissions}</p>
      <p><strong>Violations:</strong> ${item.violations}</p>
      <p><strong>Risk:</strong> ${item.risk_score} (${item.classification})</p>
      <p><strong>Policy Decision:</strong> ${item.policy_decision}</p>
      <p><strong>Human Approval Required:</strong> ${item.human_approval_required}</p>
      <p><strong>Policy Reason:</strong> ${item.policy_reason}</p>
      <p><strong>Recommended Action:</strong> ${item.recommended_action}</p>
      <p><strong>Report Source:</strong> ${item.report_source}</p>
      ${blockchainSection}
      ${downloadAction}
      <div class="info-report"><strong>Executive Report</strong>
${item.report_text || 'No report generated.'}</div>
    `;

    const infoDownloadBtn = document.getElementById('info-download-btn');
    if (infoDownloadBtn) {
      infoDownloadBtn.addEventListener('click', () => {
        elements.infoDialog.close();
        openDownloadDialog(item.audit_id);
      });
    }

    elements.infoDialog.showModal();
  };

  const openApprovalDialog = (item) => {
    state.currentApprovalAuditId = item.audit_id;

    elements.approvalContent.innerHTML = `
      <p><strong>Supplier:</strong> ${item.supplier_name}</p>
      <p><strong>Risk Score:</strong> ${item.risk_score} (${item.classification})</p>
      <p><strong>Emissions:</strong> ${item.emissions} tons CO2</p>
      <p><strong>Violations:</strong> ${item.violations}</p>
      <p><strong>Policy Decision:</strong> ${item.policy_decision}</p>
      <p><strong>Policy Reason:</strong> ${item.policy_reason}</p>
      <p><strong>Recommended Action:</strong> ${item.recommended_action}</p>
      <div class="approval-report"><strong>Executive Report Preview</strong><br/>${item.report_text.substring(0, 500)}...</div>
    `;

    elements.approverName.value = '';
    elements.approvalNotes.value = '';
    elements.approvalDialog.showModal();
  };

  // ============================================
  // Form Handlers
  // ============================================
  const handleApproval = async (decision) => {
    const approverName = elements.approverName.value.trim();
    const approvalNotes = elements.approvalNotes.value.trim();

    if (!approverName) {
      setStatus('Please enter your name', true);
      return;
    }

    const endpoint = decision === 'approve'
      ? `/api/approvals/${state.currentApprovalAuditId}/approve`
      : `/api/approvals/${state.currentApprovalAuditId}/reject`;

    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          audit_id: state.currentApprovalAuditId,
          decision: decision,
          approver_name: approverName,
          approval_notes: approvalNotes,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Approval failed');
      }

      const result = await response.json();
      elements.approvalDialog.close();
      setStatus(`Audit ${decision}d successfully by ${approverName}`);

      await fetchMetrics();
      await fetchHistory();
    } catch (error) {
      setStatus(error.message, true);
    }
  };

  const submitAudit = async (event) => {
    event.preventDefault();

    const payload = {
      supplier_name: elements.supplierName.value.trim(),
      emissions: Number(elements.emissions.value),
      violations: Number(elements.violations.value),
      notes: elements.notes.value.trim(),
      sector: elements.sector.value,
      production_unit: elements.productionUnit.value,
      registry_id: elements.registryId.value.trim(),
      baseline_year: 2023,
      target_year: 2027,
    };

    const productionVolume = elements.productionVolume.value;
    if (productionVolume) {
      payload.production_volume = Number(productionVolume);
    }

    setStatus('Running audit...');
    showLogPanel();
    addLogMessage({ type: 'info', message: 'Audit started. Waiting for progress updates...' });

    try {
      // Internal UI calls bypass the X402 payment gate via shared secret
      const response = await fetch('/api/audit', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Internal-Secret': 'cfoe-internal-bypass-secret',
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Audit failed');
      }

      const result = await response.json();
      setStatus(`Audit complete for ${result.supplier_name}.`);
      renderLatest(result);
      await fetchMetrics();
      await fetchBlockchainStatus();
      await fetchHistory();
    } catch (error) {
      setStatus(error.message, true);
      addLogMessage({ type: 'error', message: `Error: ${error.message}` });
    }
  };

  const clearHistory = async () => {
    if (!window.confirm('Delete all saved audits?')) return;

    await fetch('/api/audits', { method: 'DELETE' });
    state.selectedForCompare = [];
    await fetchMetrics();
    await fetchHistory();
    if (elements.latestResult) {
      elements.latestResult.textContent = 'No audit executed yet.';
    }
    setStatus('Audit history cleared.');
  };

  const validateRegistryId = async () => {
    const registryId = elements.registryId.value.trim();
    const validationEl = document.getElementById('registry-validation');

    if (!registryId) {
      validationEl.innerHTML = '';
      return;
    }

    try {
      const response = await fetch(`/api/registry/validate/${encodeURIComponent(registryId)}`);
      const data = await response.json();

      if (data.valid) {
        validationEl.innerHTML = `<span class="validation-success">✓ Valid: ${data.entity.name} (${data.entity.sector})</span>`;
      } else {
        validationEl.innerHTML = `<span class="validation-error">✗ ${data.error}</span>`;
      }
    } catch (error) {
      validationEl.innerHTML = `<span class="validation-error">✗ Validation failed</span>`;
    }
  };

  // ============================================
  // X402 Report Access Functions
  // ============================================
  const renderReportAccessUI = (item) => {
    if (!item.report_encrypted) return '';

    const isPaid = item.report_paid || false;
    const lockIcon = isPaid ? '🔓' : '🔒';
    const statusText = isPaid ? 'Report Unlocked' : 'Report Locked';
    const statusClass = isPaid ? 'report-unlocked' : 'report-locked';

    if (isPaid) {
      const txHash = item.payment_tx_id || '';
      return `
        <div class="x402-report-access ${statusClass}">
          <div class="x402-status">
            <span class="x402-icon">${lockIcon}</span>
            <span class="x402-text">${statusText}</span>
            <span class="x402-price-paid">✓ 0.02 ALGO Paid</span>
          </div>
          ${txHash ? `
            <div class="x402-tx-display">
              <span class="x402-tx-title">⚡ On-Chain TX Hash:</span>
              <a href="https://lora.algokit.io/testnet/transaction/${txHash}" target="_blank" rel="noopener" class="mono x402-hash-link" title="View Transaction on Algorand Testnet Explorer">
                ${txHash}
              </a>
              <button type="button" class="x402-copy-tx-btn" data-hash="${txHash}">📋 Copy</button>
            </div>
          ` : ''}
        </div>
      `;
    }

    return `
      <div class="x402-report-access ${statusClass}" id="x402-box-${item.audit_id}">
        <div class="x402-status">
          <span class="x402-icon">${lockIcon}</span>
          <span class="x402-text">${statusText}</span>
          <span class="x402-price">0.02 ALGO</span>
        </div>
        <button type="button" class="x402-unlock-btn" id="unlock-btn-${item.audit_id}" data-audit-id="${item.audit_id}">
          💳 Buy Report Access (0.02 ALGO)
        </button>
        <p class="x402-hint" id="unlock-hint-${item.audit_id}">Instant 1-Click Purchase &bull; Broadcasts real on-chain transaction &bull; Unlocks executive analysis</p>
      </div>
    `;
  };

  const attachReportAccessListeners = (item) => {
    const unlockBtn = document.querySelector(`.x402-unlock-btn[data-audit-id="${item.audit_id}"]`);
    if (unlockBtn) {
      unlockBtn.addEventListener('click', () => handleReportUnlock(item.audit_id));
    }

    const copyTxBtn = document.querySelector(`.x402-copy-tx-btn[data-hash]`);
    if (copyTxBtn) {
      copyTxBtn.addEventListener('click', async () => {
        try {
          await navigator.clipboard.writeText(copyTxBtn.dataset.hash);
          copyTxBtn.textContent = '✓ Copied!';
          setTimeout(() => { if (copyTxBtn) copyTxBtn.textContent = '📋 Copy'; }, 2000);
        } catch (e) {
          setStatus('TX Hash copied to clipboard');
        }
      });
    }
  };

  const handleReportUnlock = async (auditId) => {
    const btn = document.getElementById(`unlock-btn-${auditId}`) || document.querySelector(`.x402-unlock-btn[data-audit-id="${auditId}"]`);
    const hint = document.getElementById(`unlock-hint-${auditId}`);

    if (btn) {
      btn.disabled = true;
      btn.innerHTML = `⏳ Sending 0.02 ALGO on Algorand Testnet...`;
      btn.style.opacity = '0.85';
      btn.style.cursor = 'wait';
    }
    if (hint) {
      hint.textContent = 'Broadcasting transaction and confirming on Algorand blockchain...';
      hint.style.color = '#f5b550';
    }

    showLoading('Broadcasting 0.02 ALGO payment on Algorand Testnet...');
    setStatus('Sending payment on Algorand blockchain...');

    try {
      const response = await fetch(`/api/report/${auditId}/sponsor-pay`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || 'Payment failed');
      }

      const txId = data.tx_id || '';
      setStatus(`✓ Payment confirmed on-chain! TX: ${txId.slice(0, 16)}...`);

      // Update state
      const audit = state.audits.find(a => a.audit_id === auditId);
      if (audit) {
        audit.report_paid = true;
        audit.report_encrypted = true;
        audit.payment_tx_id = txId;
        if (data.report_text) {
          audit.report_text = data.report_text;
        }
      }

      // Update current DOM view
      const reportContent = document.getElementById(`report-content-${auditId}`);
      if (reportContent && data.report_text) {
        reportContent.textContent = data.report_text;
      }
      const reportWrap = document.getElementById(`analysis-${auditId}`);
      if (reportWrap) {
        reportWrap.hidden = false;
      }
      const toggleBtn = document.getElementById(`analysis-toggle-${auditId}`);
      if (toggleBtn) {
        toggleBtn.textContent = 'Hide Analysis';
      }

      // Re-render latest view so unlocked status and TX hash display immediately
      const updated = state.audits.find(a => a.audit_id === auditId);
      if (updated) {
        renderLatest(updated);
      }

      // Refresh history in background
      await fetchHistory();
      hideLoading();
    } catch (err) {
      hideLoading();
      setStatus(`Payment failed: ${err.message}`, true);
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = `💳 Buy Report Access (0.02 ALGO)`;
        btn.style.opacity = '1';
        btn.style.cursor = 'pointer';
      }
      if (hint) {
        hint.textContent = `Error: ${err.message}. Click to retry.`;
        hint.style.color = '#ff7b7b';
      }
    }
  };


  // ============================================
  // Wallet Functions
  // ============================================
  const updateWalletStatus = async () => {
    try {
      const response = await fetch('/api/wallet/status');
      const data = await response.json();
      state.walletStatus = data;

      if (data.connected && data.address) {
        const shortAddr = truncateAddress(data.address);
        
        // Update header button
        elements.walletAddress.innerHTML = `<span class="wallet-connected">● ${shortAddr}</span>`;
        if (elements.connectWalletBtn) {
          elements.connectWalletBtn.classList.add('wallet-connected-btn');
        }
        
        // Update modal
        if (elements.walletModalStatus) {
          elements.walletModalStatus.innerHTML = '<span class="wallet-connected">Connected</span>';
        }
        if (elements.walletModalAddress) {
          elements.walletModalAddress.textContent = data.address;
        }
        if (elements.disconnectWalletBtn) {
          elements.disconnectWalletBtn.style.display = 'inline-block';
        }
        if (elements.walletConnectModalBtn) {
          elements.walletConnectModalBtn.textContent = 'Connected';
          elements.walletConnectModalBtn.disabled = true;
        }
        
        // Fetch token summary for wallet modal
        try {
          const tokenRes = await fetch('/api/tokens/summary');
          if (tokenRes.ok) {
            const tokenData = await tokenRes.json();
            if (elements.walletModalTokenId) {
              elements.walletModalTokenId.textContent = tokenData.asset_id || 'Not Created';
            }
            if (elements.walletModalTokenSupply) {
              elements.walletModalTokenSupply.textContent = `${(tokenData.total_supply || 0).toFixed(1)} CCT`;
            }
            if (elements.walletModalCreditsIssued) {
              elements.walletModalCreditsIssued.textContent = `${(tokenData.total_issued || 0).toFixed(1)} tons`;
            }
            if (elements.walletModalCreditsRetired) {
              elements.walletModalCreditsRetired.textContent = `${(tokenData.total_retired || 0).toFixed(1)} tons`;
            }
            
            // Fetch user balance
            const balanceRes = await fetch(`/api/tokens/balance/${data.address}`);
            if (balanceRes.ok) {
              const balanceData = await balanceRes.json();
              if (elements.walletModalTokenBalance) {
                elements.walletModalTokenBalance.textContent = `${(balanceData.balance?.tokens || 0).toFixed(1)} CCT`;
              }
            }
          }
        } catch (err) {
          console.error('Failed to fetch token data for wallet modal:', err);
        }
      } else {
        // Update header button
        elements.walletAddress.textContent = 'Connect Defly Wallet';
        if (elements.connectWalletBtn) {
          elements.connectWalletBtn.classList.remove('wallet-connected-btn');
        }
        
        // Update modal
        if (elements.walletModalStatus) {
          elements.walletModalStatus.textContent = 'Disconnected';
        }
        if (elements.walletModalAddress) {
          elements.walletModalAddress.textContent = 'N/A';
        }
        if (elements.disconnectWalletBtn) {
          elements.disconnectWalletBtn.style.display = 'none';
        }
        if (elements.walletConnectModalBtn) {
          elements.walletConnectModalBtn.textContent = 'Connect Defly Wallet';
          elements.walletConnectModalBtn.disabled = false;
        }
      }
    } catch (error) {
      console.error('Failed to fetch wallet status:', error);
    }
  };

  const connectDeflyWallet = async () => {
    try {
      if (!window.walletManager) {
        setStatus('Wallet manager not loaded yet. Please refresh the page.', true);
        return;
      }

      setStatus('Connecting to Defly Wallet...');

      if (!window.walletManager.wallet) {
        const initialized = await window.walletManager.initialize();
        if (initialized) {
          setStatus('Wallet reconnected from previous session');
          await updateWalletStatus();
          await fetchBlockchainStatus();
          await fetchTokenSummary();
          return;
        }
      }

      const result = await window.walletManager.connect();

      if (result.success) {
        const mode = result.manual ? ' (manual)' : '';
        setStatus(`Wallet connected${mode}: ${window.walletManager.getShortAddress()}`);
        await updateWalletStatus();
        await fetchBlockchainStatus();
        await fetchTokenSummary();
      } else {
        setStatus(`Connection failed: ${result.error}`, true);
      }
    } catch (error) {
      setStatus(`Connection error: ${error.message}`, true);
    }
  };

  const disconnectWallet = async () => {
    try {
      if (!window.walletManager) {
        setStatus('Wallet manager not loaded', true);
        return;
      }

      setStatus('Disconnecting wallet...');
      await window.walletManager.disconnect();
      setStatus('Wallet disconnected');
      await updateWalletStatus();
      await fetchBlockchainStatus();
    } catch (error) {
      setStatus(`Disconnect error: ${error.message}`, true);
    }
  };

  const refreshData = async () => {
    await fetchMetrics();
    await fetchBlockchainStatus();
    await fetchHistory();
    setStatus('Data refreshed.');
  };

  // ============================================
  // Event Listeners
  // ============================================
  const attachEventListeners = () => {
    elements.auditForm.addEventListener('submit', submitAudit);
    elements.auditForm.querySelectorAll('input, textarea, select').forEach((field) => {
      field.addEventListener('focus', activateSplitLayout, { once: false });
      field.addEventListener('click', activateSplitLayout, { once: false });
    });
    elements.riskFilter.addEventListener('change', renderHistory);
    elements.searchInput.addEventListener('input', () => {
      state.showAllHistory = false;
      renderHistory();
    });
    elements.historyViewMoreBtn.addEventListener('click', () => {
      state.showAllHistory = !state.showAllHistory;
      renderHistory();
    });
    elements.downloadAuditSelect.addEventListener('change', refreshDownloadFormatOptions);
    elements.downloadOpenBtn.addEventListener('click', openSelectedDownload);
    elements.downloadCancelBtn.addEventListener('click', () => elements.downloadDialog.close());
    elements.infoCloseBtn.addEventListener('click', () => elements.infoDialog.close());
    elements.approveBtn.addEventListener('click', () => handleApproval('approve'));
    elements.rejectBtn.addEventListener('click', () => handleApproval('reject'));
    elements.approvalCancelBtn.addEventListener('click', () => elements.approvalDialog.close());
    elements.refreshBtn.addEventListener('click', refreshData);
    elements.clearBtn.addEventListener('click', clearHistory);

    if (elements.connectWalletBtn) {
      elements.connectWalletBtn.addEventListener('click', () => elements.walletDialog.showModal());
    }
    if (elements.walletConnectModalBtn) {
      elements.walletConnectModalBtn.addEventListener('click', connectDeflyWallet);
    }
    if (elements.walletCloseBtn) {
      elements.walletCloseBtn.addEventListener('click', () => elements.walletDialog.close());
    }
    if (elements.walletDialog) {
      elements.walletDialog.addEventListener('click', (event) => {
        if (event.target === elements.walletDialog) {
          elements.walletDialog.close();
        }
      });
    }
    if (elements.walletCopyBtn) {
      elements.walletCopyBtn.addEventListener('click', async () => {
        const address = state.walletStatus.address;
        if (!address) return;
        try {
          await navigator.clipboard.writeText(address);
          setStatus('Wallet address copied.');
        } catch {
          setStatus('Failed to copy wallet address.', true);
        }
      });
    }
    if (elements.disconnectWalletBtn) {
      elements.disconnectWalletBtn.addEventListener('click', disconnectWallet);
    }
    
    // Token management event listeners
    const optinForm = document.getElementById('optin-form');
    if (optinForm) {
      optinForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const assetId = parseInt(document.getElementById('optin-asset-id').value);
        
        showLoading('Saving token ID...');
        
        await fetch('/api/tokens/set-asset-id', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ asset_id: assetId }),
        });
        
        showLoading('Checking opt-in status...');
        
        try {
          const res = await fetch(`/api/tokens/balance/${state.walletStatus.address}`);
          if (res.ok) {
            const data = await res.json();
            const optedIn = data.balance?.opted_in;
            setStatus(`Token ID ${assetId} saved. Opted-in: ${optedIn ? 'Yes' : 'No'}`);
          } else {
            setStatus(`Token ID ${assetId} saved to token_state.json`);
          }
        } catch {
          setStatus(`Token ID ${assetId} saved to token_state.json`);
        }
        
        await fetchTokenSummary();
        await fetchBlockchainStatus();
        hideLoading();
      });
    }
    
    const createTokenForm = document.getElementById('create-token-form');
    if (createTokenForm) {
      createTokenForm.addEventListener('submit', handleCreateToken);
    }
    
    const useMyAddressBtn = document.getElementById('use-my-address-btn');
    if (useMyAddressBtn) {
      useMyAddressBtn.addEventListener('click', () => {
        const recipientInput = document.getElementById('issue-recipient');
        if (state.walletStatus.address) {
          recipientInput.value = state.walletStatus.address;
        } else {
          setStatus('Please connect wallet first', true);
        }
      });
    }
    
    const issueCreditsForm = document.getElementById('issue-credits-form');
    if (issueCreditsForm) {
      issueCreditsForm.addEventListener('submit', handleIssueCredits);
    }
    
    const retireCreditsForm = document.getElementById('retire-credits-form');
    if (retireCreditsForm) {
      retireCreditsForm.addEventListener('submit', handleRetireCredits);
    }
    
    const createNFTForm = document.getElementById('create-nft-form');
    if (createNFTForm) {
      createNFTForm.addEventListener('submit', handleCreateNFT);
    }
    
    // Token history tabs
    document.querySelectorAll('.token-history-tab').forEach(btn => {
      btn.addEventListener('click', (e) => switchTokenHistoryTab(e.target.dataset.historyTab));
    });

    // Check balance form
    const checkBalanceForm = document.getElementById('check-balance-form');
    if (checkBalanceForm) {
      checkBalanceForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const address = document.getElementById('check-balance-address').value.trim();
        if (!address) return;
        
        try {
          const res = await fetch(`/api/tokens/balance/${address}`);
          if (!res.ok) throw new Error('Failed to fetch balance');
          const data = await res.json();
          const bal = data.balance || {};
          
          document.getElementById('check-balance-tokens').textContent = `${(bal.tokens || 0).toFixed(1)} CCT`;
          document.getElementById('check-balance-credits').textContent = `${(bal.carbon_credits || 0).toFixed(0)} tons CO2eq`;
          document.getElementById('check-balance-result').style.display = 'block';
        } catch (err) {
          setStatus(`Balance check failed: ${err.message}`, true);
        }
      });
    }
  };

  // ============================================
  // Token Management Functions
  // ============================================
  const fetchTokenSummary = async () => {
    try {
      const res = await fetch('/api/tokens/summary');
      if (res.ok) {
        const data = await res.json();
        
        // Update overview
        const tokenId = data.asset_id || null;
        document.getElementById('token-overview-id').textContent = tokenId || 'Not Created';
        document.getElementById('token-overview-issued').textContent = `${(data.total_issued || 0).toFixed(1)} tons`;
        document.getElementById('token-overview-retired').textContent = `${(data.total_retired || 0).toFixed(1)} tons`;
        
        // Show opt-in button if token exists and wallet connected
        const optinBtn = document.getElementById('optin-token-btn');
        if (optinBtn && tokenId && state.walletStatus.connected) {
          // Check if user needs to opt-in
          const balanceRes = await fetch(`/api/tokens/balance/${state.walletStatus.address}`);
          if (balanceRes.ok) {
            const balanceData = await balanceRes.json();
            // Show button only if user hasn't opted in yet
            if (!balanceData.balance.opted_in) {
              optinBtn.style.display = 'block';
              optinBtn.onclick = () => handleOptIn(tokenId);
            } else {
              // User already opted in, hide button
              optinBtn.style.display = 'none';
            }
          }
        } else if (optinBtn) {
          optinBtn.style.display = 'none';
        }
        
        // Update balance if wallet connected
        if (state.walletStatus.connected && state.walletStatus.address) {
          const balanceRes = await fetch(`/api/tokens/balance/${state.walletStatus.address}`);
          if (balanceRes.ok) {
            const balanceData = await balanceRes.json();
            const tokens = balanceData.balance?.tokens || 0;
            const credits = balanceData.balance?.carbon_credits || 0;
            document.getElementById('token-overview-balance').textContent = `${tokens.toFixed(1)} CCT`;
            document.getElementById('token-overview-credits').textContent = `${credits.toFixed(0)} tons CO2eq`;
          }
        }
        
        // Store transaction history
        state.tokenData.issued = data.issued_credits || [];
        state.tokenData.retired = data.retired_credits || [];
        state.tokenData.nfts = data.audit_nfts || [];
        
        renderTokenHistory();
      }
    } catch (err) {
      console.error('Failed to fetch token summary', err);
    }
  };

  const renderTokenHistory = () => {
    // Render issued credits
    const issuedBody = document.getElementById('token-issued-body');
    if (state.tokenData.issued.length === 0) {
      issuedBody.innerHTML = '<tr><td colspan="7" class="lb-empty">No credits issued yet</td></tr>';
    } else {
      issuedBody.innerHTML = state.tokenData.issued.map(item => `
        <tr>
          <td>${truncateAddress(item.recipient || 'N/A')}</td>
          <td>${(item.carbon_credits || 0).toFixed(1)}</td>
          <td>${(item.tokens_issued || 0).toFixed(1)}</td>
          <td>${item.reason || 'N/A'}</td>
          <td>${item.audit_id || 'N/A'}</td>
          <td><code>${(item.tx_id || 'N/A').substring(0, 16)}...</code></td>
          <td>${formatDate(item.timestamp)}</td>
        </tr>
      `).join('');
    }
    
    // Render received credits (filter by current wallet address)
    const receivedBody = document.getElementById('token-received-body');
    if (!state.walletStatus.address) {
      receivedBody.innerHTML = '<tr><td colspan="7" class="lb-empty">Connect wallet to see received credits</td></tr>';
    } else {
      const receivedCredits = state.tokenData.issued.filter(item => 
        item.recipient && item.recipient.toLowerCase() === state.walletStatus.address.toLowerCase()
      );
      
      if (receivedCredits.length === 0) {
        receivedBody.innerHTML = '<tr><td colspan="7" class="lb-empty">No credits received yet</td></tr>';
      } else {
        receivedBody.innerHTML = receivedCredits.map(item => `
          <tr>
            <td>${truncateAddress(item.issuer_address || 'System')}</td>
            <td>${(item.carbon_credits || 0).toFixed(1)}</td>
            <td>${(item.tokens_issued || 0).toFixed(1)}</td>
            <td>${item.reason || 'N/A'}</td>
            <td>${item.audit_id || 'N/A'}</td>
            <td><code>${(item.tx_id || 'N/A').substring(0, 16)}...</code></td>
            <td>${formatDate(item.timestamp)}</td>
          </tr>
        `).join('');
      }
    }
    
    // Render retired credits
    const retiredBody = document.getElementById('token-retired-body');
    if (state.tokenData.retired.length === 0) {
      retiredBody.innerHTML = '<tr><td colspan="6" class="lb-empty">No credits retired yet</td></tr>';
    } else {
      retiredBody.innerHTML = state.tokenData.retired.map(item => `
        <tr>
          <td>${(item.carbon_credits || 0).toFixed(1)}</td>
          <td>${(item.tokens_retired || 0).toFixed(1)}</td>
          <td>${item.reason || 'N/A'}</td>
          <td>${item.beneficiary || 'N/A'}</td>
          <td><code>${(item.tx_id || 'N/A').substring(0, 16)}...</code></td>
          <td>${formatDate(item.timestamp)}</td>
        </tr>
      `).join('');
    }
    
    // Render NFTs
    const nftsBody = document.getElementById('token-nfts-body');
    if (state.tokenData.nfts.length === 0) {
      nftsBody.innerHTML = '<tr><td colspan="7" class="lb-empty">No NFTs created yet</td></tr>';
    } else {
      nftsBody.innerHTML = state.tokenData.nfts.map(item => `
        <tr>
          <td><code>${item.asset_id || 'N/A'}</code></td>
          <td>${item.supplier_name || 'N/A'}</td>
          <td>${item.audit_id || 'N/A'}</td>
          <td>${(item.risk_score || 0).toFixed(2)}</td>
          <td>${classToBadge(item.classification || 'N/A')}</td>
          <td><code>${(item.tx_id || 'N/A').substring(0, 16)}...</code></td>
          <td>${formatDate(item.timestamp)}</td>
        </tr>
      `).join('');
    }
  };

  const handleOptIn = async (assetId) => {
    if (!state.walletStatus.connected) {
      setStatus('Please connect wallet first', true);
      return;
    }
    
    try {
      showLoading('Opting in to receive tokens...');
      setStatus('Opting in to receive carbon credit tokens...');
      const res = await fetch('/api/tokens/optin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ asset_id: assetId }),
      });
      
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || 'Opt-in failed');
      }
      
      const result = await res.json();
      setStatus('Successfully opted-in! You can now receive tokens.');
      await fetchTokenSummary();
      hideLoading();
    } catch (error) {
      setStatus(error.message, true);
      hideLoading();
    }
  };

  const handleCreateToken = async (e) => {
    e.preventDefault();
    
    if (!state.walletStatus.connected) {
      setStatus('Please connect wallet first', true);
      return;
    }
    
    const payload = {
      total_credits: parseInt(document.getElementById('token-total-supply').value),
      unit_name: document.getElementById('token-symbol').value,
      asset_name: document.getElementById('token-name').value,
    };
    
    try {
      showLoading('Creating carbon credit token...');
      setStatus('Creating carbon credit token...');
      const res = await fetch('/api/tokens/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || 'Token creation failed');
      }
      
      const result = await res.json();
      setStatus(`Token created successfully! Asset ID: ${result.asset_id}`);
      await fetchTokenSummary();
      await fetchBlockchainStatus();
      hideLoading();
    } catch (error) {
      setStatus(error.message, true);
      hideLoading();
    }
  };

  const handleIssueCredits = async (e) => {
    e.preventDefault();
    
    if (!state.walletStatus.connected) {
      setStatus('Please connect wallet first', true);
      return;
    }
    
    const payload = {
      recipient_address: document.getElementById('issue-recipient').value.trim(),
      amount: parseFloat(document.getElementById('issue-amount').value),
      reason: document.getElementById('issue-reason').value.trim(),
      audit_id: document.getElementById('issue-audit-id').value.trim() || null,
    };
    
    try {
      showLoading('Issuing carbon credits...');
      setStatus('Issuing carbon credits...');
      const res = await fetch('/api/tokens/issue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || 'Credit issuance failed');
      }
      
      const result = await res.json();
      setStatus(`Credits issued successfully! ${result.amount} tons CO2eq`);
      e.target.reset();
      // Wait for blockchain confirmation before refreshing
      await new Promise(resolve => setTimeout(resolve, 2000));
      await fetchTokenSummary();
      await fetchBlockchainStatus();
      hideLoading();
    } catch (error) {
      setStatus(error.message, true);
      hideLoading();
    }
  };

  const handleRetireCredits = async (e) => {
    e.preventDefault();
    
    if (!state.walletStatus.connected) {
      setStatus('Please connect wallet first', true);
      return;
    }
    
    const payload = {
      amount: parseFloat(document.getElementById('retire-amount').value),
      reason: document.getElementById('retire-reason').value.trim(),
      beneficiary: document.getElementById('retire-beneficiary').value.trim(),
    };
    
    try {
      showLoading('Retiring carbon credits...');
      setStatus('Retiring carbon credits...');
      const res = await fetch('/api/tokens/retire', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || 'Credit retirement failed');
      }
      
      const result = await res.json();
      setStatus(`Credits retired successfully! ${result.amount} tons CO2eq`);
      e.target.reset();
      // Wait for blockchain confirmation before refreshing
      await new Promise(resolve => setTimeout(resolve, 2000));
      await fetchTokenSummary();
      await fetchBlockchainStatus();
      hideLoading();
    } catch (error) {
      setStatus(error.message, true);
      hideLoading();
    }
  };

  const handleCreateNFT = async (e) => {
    e.preventDefault();
    
    if (!state.walletStatus.connected) {
      setStatus('Please connect wallet first', true);
      return;
    }
    
    const payload = {
      supplier_name: document.getElementById('nft-supplier').value.trim(),
      audit_id: document.getElementById('nft-audit-id').value.trim(),
      risk_score: parseFloat(document.getElementById('nft-risk-score').value),
      classification: document.getElementById('nft-classification').value,
      emissions: parseFloat(document.getElementById('nft-emissions').value),
      metadata_url: '',
    };
    
    try {
      showLoading('Creating audit certificate NFT...');
      setStatus('Creating audit certificate NFT...');
      const res = await fetch('/api/tokens/nft/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || 'NFT creation failed');
      }
      
      const result = await res.json();
      setStatus(`NFT created successfully! Asset ID: ${result.asset_id}`);
      e.target.reset();
      await fetchTokenSummary();
      hideLoading();
    } catch (error) {
      setStatus(error.message, true);
      hideLoading();
    }
  };

  const switchTokenHistoryTab = (tabName) => {
    document.querySelectorAll('.token-history-tab').forEach(btn => {
      if (btn.dataset.historyTab === tabName) btn.classList.add('active');
      else btn.classList.remove('active');
    });
    
    document.querySelectorAll('.token-history-content').forEach(content => {
      if (content.id === `token-history-${tabName}`) content.classList.add('active');
      else content.classList.remove('active');
    });
  };

  // ============================================
  // Leaderboard Functions
  // ============================================
  const badgeToIcon = (badgeName) => {
    switch (badgeName) {
      case 'Green Champion': return '🌿';
      case 'Eco Performer': return '🌱';
      case 'In Progress': return '🔄';
      case 'Consistency Streak': return '🔥';
      case 'Improver': return '📈';
      default: return '🏅';
    }
  };

  const renderCreditsHTML = (credits) => {
    if (!credits) return '';

    // First audit ever: previous total was 0 and this is the first execution
    // (A strict check: if previous_total is 0 and we earned something or even 0 on the very first run).
    // Let's assume if previous_total === 0 and the API returned credits object, we can show welcome message.
    let welcomeHtml = '';
    if (credits.previous_total === 0) {
      welcomeHtml = `
        <div class="credit-welcome">
          <strong>👋 Welcome to the Carbon Credit Program!</strong>
          <p>Earn credits and exclusive badges by maintaining low-risk ESG policies and consistently improving.</p>
        </div>
      `;
    }

    if (credits.total_credits === 0) {
      return `
        ${welcomeHtml}
        <div class="credit-card neutral">
          <div><strong>No credits earned this audit</strong> </div>
          <p>Reduce emissions below 0.60 to start earning rewards.</p>
          <div class="credit-running">Running Total: ${credits.new_total} <small>pts</small></div>
        </div>
      `;
    }

    const badgesHtml = (credits.badges_earned || [])
      .map(b => `<span class="lb-badge-pill" title="${b}">${badgeToIcon(b)} ${b}</span>`)
      .join('');

    return `
      ${welcomeHtml}
      <div class="credit-card">
        <h3>💳 Credits Earned This Audit</h3>
        <div class="credit-earned-row">
          <div class="credit-large">+${credits.total_credits}</div>
          <div class="credit-badges">${badgesHtml}</div>
        </div>
        <div class="credit-breakdown">
          ${credits.streak_bonus > 0 ? `<div class="credit-bonus highlight">🔥 Streak Bonus: +${credits.streak_bonus} pts</div>` : ''}
          ${credits.improvement_bonus > 0 ? `<div class="credit-bonus highlight">📈 Improvement Bonus: +${credits.improvement_bonus} pts</div>` : ''}
        </div>
        <div class="credit-running">
          Running Total: <strong>${credits.new_total}</strong> <small>pts</small>
        </div>
      </div>
    `;
  };

  const scoreToClass = (score) => {
    if (score == null) return 'low';
    if (score <= 0.20 || String(score).includes('ow')) return 'low'; // Handle both string and float
    if (score <= 0.60 || String(score).includes('oderate')) return 'moderate';
    return 'critical';
  };

  const getTrendIcon = (supplier) => {
    if (supplier.total_audits < 2) return '<span class="lb-trend-neutral">=</span>';
    
    // In actual app, we'd compare the last two chronological audits.
    // Here we approximate with latest vs best (or if we had last two, we'd use them).
    // Let's assume if (latest_esg > best_esg), trend is Down (Bad).
    // This is a proxy since /api/leaderboard doesn't send the full history array for perf.
    if (supplier.latest_esg_score === supplier.best_esg_score) {
      return '<span class="lb-trend-up">↑</span>'; // At their best
    }
    return '<span class="lb-trend-down">↓</span>';
  };

  const renderLeaderboard = () => {
    if (!state.lbData || state.lbData.length === 0) {
      elements.lbPodium.innerHTML = '<div class="lb-empty">No supplier credits awarded yet. Run an audit to generate scores!</div>';
      elements.lbBody.innerHTML = '<tr><td colspan="8" class="lb-empty">No data available</td></tr>';
      return;
    }

    // 1. Render Podium (Top 3)
    const top3 = state.lbData.slice(0, 3);
    const podiumRanks = [];

    // Order: 2nd, 1st, 3rd for visual flex align-items: flex-end
    if (top3[1]) podiumRanks.push({ ...top3[1], rank: 2 });
    if (top3[0]) podiumRanks.push({ ...top3[0], rank: 1 });
    if (top3[2]) podiumRanks.push({ ...top3[2], rank: 3 });

    elements.lbPodium.innerHTML = podiumRanks.map(s => {
      const highestBadge = s.badges.length > 0 ? badgeToIcon(s.badges[0]) : '🏅';
      return `
        <div class="lb-podium-block" data-rank="${s.rank}">
          <div class="lb-podium-rank">#${s.rank}</div>
          <div class="lb-podium-badge">${highestBadge}</div>
          <div class="lb-podium-name" title="${s.supplier_name}">${s.supplier_name}</div>
          <div class="lb-podium-credits">${s.total_credits} pts</div>
          <button type="button" class="lb-create-nft-btn" data-supplier="${s.supplier_name}" data-score="${s.latest_esg_score}" data-classification="${s.latest_classification || 'Low Risk'}" title="Create NFT for ${s.supplier_name}">🎖️ Create NFT</button>
        </div>
      `;
    }).join('');

    // 2. Render Table (All)
    elements.lbBody.innerHTML = state.lbData.map((s, idx) => {
      const rank = idx + 1;
      const isTop = rank === 1 ? 'class="lb-top-row"' : '';
      const badgeHTML = s.badges.map(b => `<span class="lb-badge-pill" title="${b}">${badgeToIcon(b)} ${b}</span>`).join('');
      const scoreCls = scoreToClass(s.latest_esg_score);
      
      return `
        <tr ${isTop}>
          <td class="lb-rank-cell">#${rank}</td>
          <td><strong>${s.supplier_name}</strong></td>
          <td class="lb-credits-cell">${s.total_credits}</td>
          <td>${badgeHTML || '-'}</td>
          <td><span class="badge ${scoreCls}">${s.latest_esg_score != null ? s.latest_esg_score : 'N/A'}</span></td>
          <td>${s.current_streak > 0 ? `🔥 ${s.current_streak}` : '-'}</td>
          <td>${s.total_audits}</td>
          <td>${getTrendIcon(s)}</td>
        </tr>
      `;
    }).join('');

    updateLeaderboardTime();
    
    // Attach event listeners to Create NFT buttons
    document.querySelectorAll('.lb-create-nft-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const supplierName = e.currentTarget.dataset.supplier;
        const score = parseFloat(e.currentTarget.dataset.score);
        const classification = e.currentTarget.dataset.classification;
        
        // Find the latest audit for this supplier
        const supplierAudit = state.audits.find(a => a.supplier_name === supplierName);
        
        // Switch to tokens tab
        switchTab('tokens');
        
        // Pre-fill NFT form
        setTimeout(() => {
          document.getElementById('nft-supplier').value = supplierName;
          document.getElementById('nft-risk-score').value = score || (supplierAudit?.risk_score || 0);
          document.getElementById('nft-classification').value = classification || (supplierAudit?.classification || 'Low Risk');
          document.getElementById('nft-emissions').value = supplierAudit?.emissions || 0;
          document.getElementById('nft-audit-id').value = supplierAudit?.audit_id || `AUD-${supplierName.substring(0,6).toUpperCase()}`;
          
          // Scroll to NFT form
          document.getElementById('create-nft-form')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
          setStatus(`NFT form pre-filled for ${supplierName}`);
        }, 100);
      });
    });
  };

  const updateLeaderboardTime = () => {
    if (!state.lbLastFetched) return;
    const diff = Math.floor((Date.now() - state.lbLastFetched) / 1000);
    elements.lbUpdated.textContent = `Last updated ${diff} seconds ago`;
  };

  const fetchLeaderboard = async () => {
    try {
      const res = await fetch('/api/leaderboard');
      if (res.ok) {
        const data = await res.json();
        state.lbData = data.items || [];
        state.lbLastFetched = Date.now();
        renderLeaderboard();
      }
    } catch (err) {
      console.error('Failed to fetch leaderboard', err);
    }
  };

  // ============================================
  // Revenue Dashboard (Part 5)
  // ============================================

  const fetchRevenue = async () => {
    try {
      const res = await fetch('/api/revenue');
      if (!res.ok) return;
      const data = await res.json();
      state.revenueData = data;
      renderRevenue(data);
    } catch (err) {
      console.warn('Revenue fetch failed:', err);
    }
  };

  const renderRevenue = (data) => {
    // KPI cards
    const kpiEarned = document.getElementById('rev-total-earned');
    const kpiAudits = document.getElementById('rev-audits-paid');
    const kpiReports = document.getElementById('rev-reports-sold');
    const kpiCount = document.getElementById('rev-payment-count');

    if (kpiEarned) kpiEarned.textContent = (data.total_algo_earned || 0).toFixed(6) + ' ALGO';
    if (kpiAudits) kpiAudits.textContent = data.total_audits_paid || 0;
    if (kpiReports) kpiReports.textContent = data.total_reports_sold || 0;
    if (kpiCount) kpiCount.textContent = data.payment_count || 0;

    // Agent wallet balances
    const AGENT_MAP = {
      monitor_agent:   'monitor',
      reporting_agent: 'reporting',
      policy_agent:    'policy',
    };
    const balances = data.agent_balances || {};
    for (const [agentKey, shortKey] of Object.entries(AGENT_MAP)) {
      const info = balances[agentKey] || {};
      const addrEl  = document.getElementById(`rwc-${shortKey}-addr`);
      const balEl   = document.getElementById(`rwc-${shortKey}-bal`);
      const card    = addrEl?.closest('.revenue-wallet-card');
      if (addrEl) {
        const addr = info.address || 'Not initialized';
        addrEl.textContent = addr.length > 20 ? addr.slice(0, 10) + '...' + addr.slice(-6) : addr;
        addrEl.title = addr;
      }
      if (balEl) {
        const bal = info.balance_algo;
        balEl.textContent = bal != null ? bal.toFixed(6) + ' ALGO' : 'N/A';
        if (card) card.classList.remove('skeleton');
      }
    }

    // Earnings by agent table
    const earningsBody = document.getElementById('rev-earnings-body');
    if (earningsBody) {
      const earnings = data.earnings_by_agent || {};
      const total = data.total_algo_earned || 0;
      const entries = Object.entries(earnings);
      if (entries.length === 0) {
        earningsBody.innerHTML = '<tr><td colspan="3" class="lb-empty">No earnings yet</td></tr>';
      } else {
        earningsBody.innerHTML = entries
          .sort((a, b) => b[1] - a[1])
          .map(([agent, amt]) => {
            const pct = total > 0 ? ((amt / total) * 100).toFixed(1) : '0';
            const bar = `<div style="height:6px;border-radius:3px;background:linear-gradient(90deg,#00ff88,#00c4ff);width:${pct}%;min-width:4px"></div>`;
            return `<tr><td>${agent}</td><td>${amt.toFixed(6)} ALGO</td><td style="min-width:120px">${bar} ${pct}%</td></tr>`;
          })
          .join('');
      }
    }

    // Recent X402 payments table
    const txBody = document.getElementById('rev-tx-body');
    if (txBody) {
      const payments = data.recent_payments || [];
      if (payments.length === 0) {
        txBody.innerHTML = '<tr><td colspan="7" class="lb-empty">No X402 payments yet</td></tr>';
      } else {
        txBody.innerHTML = payments.map(p => {
          const ts = p.timestamp ? new Date(p.timestamp).toLocaleString() : '—';
          const dirBadge = p.direction === 'incoming'
            ? '<span class="badge low">↓ IN</span>'
            : '<span class="badge moderate">↑ OUT</span>';
          const statusBadge = p.status === 'confirmed'
            ? '<span class="badge low">✓</span>'
            : p.status === 'pending'
              ? '<span class="badge moderate">⏳</span>'
              : '<span class="badge critical">✗</span>';
          const txLink = p.tx_id
            ? `<a href="https://lora.algokit.io/testnet/transaction/${p.tx_id}" target="_blank" rel="noopener" class="mono" title="${p.tx_id}">${p.tx_id.slice(0, 12)}...</a>`
            : '—';
          return `<tr><td>${ts}</td><td>${p.agent || '—'}</td><td>${dirBadge}</td><td>${p.service || '—'}</td><td>${(p.amount_algo || 0).toFixed(4)}</td><td>${statusBadge}</td><td>${txLink}</td></tr>`;
        }).join('');
      }
    }
  };

  const switchTab = (tabId) => {
    // Nav
    if (elements.tabBtns) {
      elements.tabBtns.forEach(btn => {
        if (btn.dataset.tab === tabId) btn.classList.add('active');
        else btn.classList.remove('active');
      });
    }

    // Content
    if (elements.tabContents) {
      elements.tabContents.forEach(content => {
        if (content.id === `tab-${tabId}`) content.classList.add('active');
        else content.classList.remove('active');
      });
    }

    // Hook behaviors
    if (tabId === 'leaderboard') {
      fetchLeaderboard();
      if (!state.lbInterval) {
        state.lbInterval = setInterval(() => {
          fetchLeaderboard();
        }, 30000); // 30s auto-refresh

        // Update time every second visually
        setInterval(updateLeaderboardTime, 1000);
      }
    } else if (tabId === 'tokens') {
      fetchTokenSummary();
    } else if (tabId === 'revenue') {
      fetchRevenue();
      if (!state.revenueInterval) {
        state.revenueInterval = setInterval(fetchRevenue, 30000);
      }
    } else {
      if (state.lbInterval) {
        clearInterval(state.lbInterval);
        state.lbInterval = null;
      }
      if (state.revenueInterval) {
        clearInterval(state.revenueInterval);
        state.revenueInterval = null;
      }
    }
  };

  // ============================================
  // Initialization
  // ============================================
  const initialize = async () => {
    syncSplitLayoutFromSession();
    updateChimneyRisk('Low Risk');
    
    // Capture simulator params from localStorage (set by simulator dashboard)
    const simRaw = localStorage.getItem('cfoe_sim_prefill');
    const simParams = simRaw ? JSON.parse(simRaw) : null;
    if (simParams) localStorage.removeItem('cfoe_sim_prefill');

    let retries = 0;
    while (!window.walletManager && retries < 50) {
      await new Promise((resolve) => setTimeout(resolve, 100));
      retries++;
    }

    connectLogSocket();

    if (window.walletManager) {
      await window.walletManager.initialize();
    }

    await fetchMetrics();
    await fetchBlockchainStatus();
    await fetchHistory();
    await updateWalletStatus();

    // Apply simulator pre-fill after all data loads (so it isn't overwritten)
    if (simParams) {
      // Force split layout and run button visible regardless of session state
      state.splitActivated = false;
      activateSplitLayout();
      elements.supplierName.value = simParams.supplier_name;
      elements.emissions.value = simParams.emissions;
      elements.violations.value = simParams.violations;
      elements.sector.value = simParams.sector;
      elements.notes.value = simParams.notes;
      setStatus('Form pre-filled from simulator — review and click Run Audit.');
      setTimeout(() => elements.supplierName.scrollIntoView({ behavior: 'smooth', block: 'center' }), 700);
    } else {
      setStatus('Dashboard ready.');
    }
  };

  attachEventListeners();
    elements.tabBtns?.forEach(btn => {
      btn.addEventListener('click', (e) => switchTab(e.target.dataset.tab));
    });

    initialize();

  window.validateRegistryId = validateRegistryId;
})();