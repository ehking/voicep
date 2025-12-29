const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const selectFileBtn = document.getElementById('select-file');
const jobsListEl = document.getElementById('jobs-list');
const jobsEmptyEl = document.getElementById('jobs-empty');
const toast = document.getElementById('toast');
const resultText = document.getElementById('result-text');
const toggleClean = document.getElementById('toggle-clean');
const toggleRaw = document.getElementById('toggle-raw');
const copyBtn = document.getElementById('copy-btn');
const downloadBtn = document.getElementById('download-btn');
const refreshHistoryBtn = document.getElementById('refresh-history');
const selectedJobLabel = document.getElementById('selected-job-label');
const resultStatus = document.getElementById('result-status');

const jobs = new Map();
let selectedJobId = null;
let showClean = true;
let pollInterval = null;
let resultsCache = new Map();

const statusMap = {
  queued: 'در صف',
  processing: 'در حال پردازش',
  done: 'انجام شد',
  error: 'خطا'
};

function showToast(message, type = 'info') {
  toast.textContent = message;
  toast.classList.remove('opacity-0', 'pointer-events-none');
  toast.classList.remove('bg-green-600', 'bg-red-600', 'bg-gray-800');
  toast.classList.add(type === 'error' ? 'bg-red-600' : type === 'success' ? 'bg-green-600' : 'bg-gray-800');
  setTimeout(() => {
    toast.classList.add('opacity-0', 'pointer-events-none');
  }, 3000);
}

function humanStatus(job) {
  return statusMap[job.status] || job.status;
}

function renderJobs() {
  const items = Array.from(jobs.values()).sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));
  jobsListEl.innerHTML = '';
  if (!items.length) {
    jobsEmptyEl.classList.remove('hidden');
    return;
  }
  jobsEmptyEl.classList.add('hidden');
  items.forEach(job => {
    const wrapper = document.createElement('div');
    wrapper.className = 'border rounded p-3 flex flex-col gap-2 bg-gray-50';
    const header = document.createElement('div');
    header.className = 'flex items-center justify-between gap-2';
    const title = document.createElement('div');
    title.innerHTML = `<div class="font-semibold">${job.original_filename}</div><div class="text-xs text-gray-500">${new Date(job.created_at).toLocaleString('fa-IR')}</div>`;
    const statusBadge = document.createElement('span');
    statusBadge.className = 'text-xs px-2 py-1 rounded ' + (job.status === 'done' ? 'bg-green-100 text-green-700' : job.status === 'error' ? 'bg-red-100 text-red-700' : 'bg-yellow-100 text-yellow-700');
    statusBadge.textContent = humanStatus(job);
    header.appendChild(title);
    header.appendChild(statusBadge);

    const progressWrap = document.createElement('div');
    progressWrap.className = 'w-full bg-gray-200 rounded-full h-2';
    const progressBar = document.createElement('div');
    progressBar.className = 'bg-indigo-600 h-2 rounded-full';
    progressBar.style.width = `${job.progress || 0}%`;
    progressWrap.appendChild(progressBar);

    const actions = document.createElement('div');
    actions.className = 'flex items-center justify-between text-xs text-gray-600';
    const progressLabel = document.createElement('span');
    progressLabel.textContent = `${job.progress || 0}%`;
    const viewBtn = document.createElement('button');
    viewBtn.className = 'px-3 py-1 bg-white border rounded hover:bg-gray-100';
    viewBtn.textContent = 'نمایش';
    viewBtn.addEventListener('click', () => selectJob(job.id));
    actions.appendChild(progressLabel);
    actions.appendChild(viewBtn);

    wrapper.appendChild(header);
    wrapper.appendChild(progressWrap);
    wrapper.appendChild(actions);
    jobsListEl.appendChild(wrapper);
  });
}

function updateResultView() {
  const result = resultsCache.get(selectedJobId) || { raw_text: '', cleaned_text: '' };
  resultText.value = showClean ? (result.cleaned_text || '') : (result.raw_text || '');
  toggleClean.classList.toggle('bg-indigo-600', showClean);
  toggleClean.classList.toggle('text-white', showClean);
  toggleClean.classList.toggle('bg-gray-200', !showClean);
  toggleClean.classList.toggle('text-gray-800', !showClean);
  toggleRaw.classList.toggle('bg-indigo-600', !showClean);
  toggleRaw.classList.toggle('text-white', !showClean);
  toggleRaw.classList.toggle('bg-gray-200', showClean);
  toggleRaw.classList.toggle('text-gray-800', showClean);
}

async function uploadFile(file) {
  const formData = new FormData();
  formData.append('file', file);
  try {
    const res = await fetch('/api/upload', { method: 'POST', body: formData });
    const data = await res.json();
    if (!data.ok) {
      throw new Error(data.error?.message || 'خطا در آپلود');
    }
    jobs.set(data.job.id, data.job);
    renderJobs();
    showToast('فایل دریافت شد و در صف قرار گرفت', 'success');
    startPolling();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function handleFiles(fileList) {
  if (!fileList?.length) return;
  Array.from(fileList).forEach(file => uploadFile(file));
}

function startPolling() {
  if (pollInterval) return;
  pollInterval = setInterval(checkActiveJobs, 1500);
}

async function checkActiveJobs() {
  const activeJobs = Array.from(jobs.values()).filter(j => ['queued', 'processing'].includes(j.status));
  if (!activeJobs.length) {
    clearInterval(pollInterval);
    pollInterval = null;
    return;
  }
  await Promise.all(activeJobs.map(async (job) => {
    try {
      const res = await fetch(`/api/jobs/${job.id}`);
      const data = await res.json();
      if (!data.ok) throw new Error(data.error?.message || 'خطا در وضعیت');
      jobs.set(job.id, data.job);
      if (selectedJobId === job.id) {
        selectedJobLabel.textContent = `فایل: ${data.job.original_filename}`;
        resultStatus.textContent = `وضعیت: ${humanStatus(data.job)}`;
      }
      if (data.job.status === 'done') {
        await loadResult(job.id);
      } else if (data.job.status === 'error') {
        showToast(data.job.error_message || 'خطا در پردازش', 'error');
      }
    } catch (err) {
      console.error(err);
    }
  }));
  renderJobs();
}

async function selectJob(jobId) {
  const job = jobs.get(jobId);
  if (!job) return;
  selectedJobId = jobId;
  selectedJobLabel.textContent = `فایل: ${job.original_filename}`;
  resultStatus.textContent = `وضعیت: ${humanStatus(job)}`;
  if (job.status === 'done') {
    await loadResult(jobId);
  } else {
    resultText.value = '';
    startPolling();
  }
  updateResultView();
}

async function loadResult(jobId) {
  try {
    const res = await fetch(`/api/jobs/${jobId}/result`);
    const data = await res.json();
    if (!data.ok) throw new Error(data.error?.message || 'نتیجه آماده نیست');
    resultsCache.set(jobId, data.result);
    updateResultView();
    resultStatus.textContent = `وضعیت: ${humanStatus(jobs.get(jobId) || { status: 'done' })}`;
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function loadHistory() {
  try {
    const res = await fetch('/api/history?limit=10');
    const data = await res.json();
    if (!data.ok) throw new Error(data.error?.message || 'خطا در تاریخچه');
    data.jobs.forEach(job => jobs.set(job.id, job));
    renderJobs();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

selectFileBtn.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', (e) => handleFiles(e.target.files));

['dragenter', 'dragover'].forEach(evt => {
  dropZone.addEventListener(evt, (e) => {
    e.preventDefault();
    e.stopPropagation();
    dropZone.classList.add('border-indigo-400', 'bg-indigo-50');
  });
});
['dragleave', 'drop'].forEach(evt => {
  dropZone.addEventListener(evt, (e) => {
    e.preventDefault();
    e.stopPropagation();
    dropZone.classList.remove('border-indigo-400', 'bg-indigo-50');
  });
});
dropZone.addEventListener('drop', (e) => {
  const dt = e.dataTransfer;
  if (dt?.files?.length) {
    handleFiles(dt.files);
  }
});

toggleClean.addEventListener('click', () => {
  showClean = true;
  updateResultView();
});

toggleRaw.addEventListener('click', () => {
  showClean = false;
  updateResultView();
});

copyBtn.addEventListener('click', async () => {
  if (!resultText.value) return;
  await navigator.clipboard.writeText(resultText.value);
  showToast('کپی شد', 'success');
});

downloadBtn.addEventListener('click', async () => {
  if (!selectedJobId) return;
  const res = await fetch(`/api/jobs/${selectedJobId}/download`);
  if (!res.ok) {
    showToast('فایل آماده نیست', 'error');
    return;
  }
  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `result_${selectedJobId}.txt`;
  a.click();
  window.URL.revokeObjectURL(url);
});

refreshHistoryBtn.addEventListener('click', loadHistory);

dropZone.addEventListener('click', () => fileInput.click());

loadHistory();
startPolling();
